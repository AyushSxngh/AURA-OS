#!/usr/bin/env python3
"""
Samsung Electronics Co., Ltd. — Galaxy S24 Ultra Hardware Wi-Fi Service
Daemon for live Wi-Fi synchronization:
1. Monitors macOS physical Wi-Fi connection (SSID, BSSID, Gateway IP, Subnet, DNS).
2. Dynamically synchronizes Android 16 Wi-Fi stack:
   - Automatically adapts when MacBook moves to another network (Home, Office, Hotspot).
   - Patches virtual AP and libslirp with real BSSID, SSID, Gateway IP, Subnet Mask, and Phone IP.
   - Eliminates dead 10.0.2.2 gateway and 10.0.2.16 IP.
   - Maintains genuine Samsung Wi-Fi behavior.
"""

import os
import sys
import time
import json
import subprocess
import signal
import re
import ipaddress
import shutil

STATE_FILE = "/tmp/sec_wifi_state.json"
PID_FILE = "/tmp/sec_wifi_service.pid"
LOG_FILE = "/tmp/sec_wifi_service.log"
HOSTAPD_CONF = "/Users/ayush/Library/Android/sdk/emulator/lib/hostapd.conf"
NETSIMD_DIR = "/Users/ayush/Library/Android/sdk/emulator"
NETSIMD_ORIG = os.path.join(NETSIMD_DIR, "netsimd.orig")
NETSIMD_BIN = os.path.join(NETSIMD_DIR, "netsimd.bin")
NETSIMD_WRAPPER = os.path.join(NETSIMD_DIR, "netsimd")

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] [sec_wifi_service] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def run_cmd(cmd, timeout=5):
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except Exception:
        return ""

def run_adb(cmd, timeout=5):
    return run_cmd(f"adb {cmd}", timeout=timeout)

def get_mac_network_state():
    """
    Extracts real-time physical Wi-Fi connection info from macOS DynamicStore & ARP.
    No sudo required.
    """
    state = {
        "interface": "en0",
        "gateway": None,
        "bssid": None,
        "mac_ip": None,
        "subnet_mask": None,
        "vnet": None,
        "prefix": None,
        "net_cidr": None,
        "phone_ip": None,
        "dns": [],
        "ssid": None
    }

    # 1. Query scutil DynamicStore
    scutil_script = """
show State:/Network/Global/IPv4
quit
"""
    ipv4_out = run_cmd(f"printf '{scutil_script}' | scutil")
    service_id = None
    for line in ipv4_out.splitlines():
        if "PrimaryService :" in line:
            service_id = line.split(":", 1)[1].strip()
        elif "Router :" in line:
            state["gateway"] = line.split(":", 1)[1].strip()

    if service_id:
        srv_script = f"""
show State:/Network/Service/{service_id}/IPv4
show State:/Network/Service/{service_id}/DNS
quit
"""
        srv_out = run_cmd(f"printf '{srv_script}' | scutil")
        m_bssid = re.search(r"ARPResolvedHardwareAddress\s*:\s*([0-9a-fA-F:]+)", srv_out)
        if m_bssid:
            raw_bssid = m_bssid.group(1).strip().split(":")
            state["bssid"] = ":".join(f"{int(x, 16):02x}" for x in raw_bssid)

        m_ip = re.search(r"Addresses\s*:\s*<array>\s*\{\s*0\s*:\s*(\d+\.\d+\.\d+\.\d+)", srv_out)
        if m_ip:
            state["mac_ip"] = m_ip.group(1).strip()

        m_mask = re.search(r"SubnetMasks\s*:\s*<array>\s*\{\s*0\s*:\s*(255\.\d+\.\d+\.\d+)", srv_out)
        if m_mask:
            state["subnet_mask"] = m_mask.group(1).strip()

        if "ServerAddresses" in srv_out:
            dns_part = srv_out[srv_out.find("ServerAddresses"):]
            m_dns = re.findall(r"\d+\s*:\s*(\d+\.\d+\.\d+\.\d+)", dns_part)
            state["dns"] = m_dns

    # 2. Fallback for Router BSSID via ARP if DynamicStore didn't provide it
    if state["gateway"] and not state["bssid"]:
        arp_out = run_cmd(f"arp -n {state['gateway']}")
        m = re.search(r"at\s+([0-9a-fA-F:]+)\s+on", arp_out)
        if m:
            raw_mac = m.group(1).split(":")
            padded = ":".join(f"{int(x, 16):02x}" for x in raw_mac)
            state["bssid"] = padded

    # 3. Detect SSID
    pref_out = run_cmd("networksetup -listpreferredwirelessnetworks en0")
    candidate_ssids = [l.strip() for l in pref_out.splitlines() if l.strip() and "Preferred networks" not in l]

    if candidate_ssids:
        state["ssid"] = candidate_ssids[0]

    if not state["ssid"] and os.path.exists(HOSTAPD_CONF):
        try:
            with open(HOSTAPD_CONF, "r") as f:
                for line in f:
                    if line.startswith("ssid=") and not state["ssid"]:
                        cand = line.split("=", 1)[1].strip()
                        if cand and cand != "AndroidWifi":
                            state["ssid"] = cand
        except Exception:
            pass

    if not state["ssid"]:
        state["ssid"] = "Airtel_adar_7069"

    # 4. Compute Subnet CIDR and Phone IP
    if state["mac_ip"] and state["subnet_mask"]:
        try:
            iface = ipaddress.IPv4Interface(f"{state['mac_ip']}/{state['subnet_mask']}")
            state["vnet"] = str(iface.network.network_address)
            state["prefix"] = iface.network.prefixlen
            state["net_cidr"] = f"{state['vnet']}/{state['prefix']}"

            # Mirror host MacBook IP directly inside guest interface
            state["phone_ip"] = state["mac_ip"]
        except Exception as e:
            log(f"Error calculating IP CIDR: {e}")

    if not state["dns"]:
        state["dns"] = ["192.168.1.1", "8.8.8.8"]

    return state

def sync_hostapd_conf(ssid, bssid):
    """
    Updates hostapd.conf with genuine router BSSID and SSID.
    """
    if not os.path.exists(HOSTAPD_CONF):
        return False

    changed = False
    try:
        with open(HOSTAPD_CONF, "r") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            if line.startswith("ssid="):
                new_line = f"ssid={ssid}\n"
                if line != new_line:
                    changed = True
                new_lines.append(new_line)
            elif line.startswith("bssid="):
                new_line = f"bssid={bssid}\n"
                if line != new_line:
                    changed = True
                new_lines.append(new_line)
            else:
                new_lines.append(line)

        if changed:
            with open(HOSTAPD_CONF, "w") as f:
                f.writelines(new_lines)
            log(f"Updated hostapd.conf: SSID='{ssid}', BSSID='{bssid}'")
            return True
    except Exception as e:
        log(f"Error updating hostapd.conf: {e}")
    return False

def patch_netsimd_binary(state):
    """
    Patches netsimd binary to embed genuine BSSID and network SlirpConfig.
    """
    if not os.path.exists(NETSIMD_ORIG):
        if os.path.exists(NETSIMD_WRAPPER) and not os.path.islink(NETSIMD_WRAPPER):
            # check if NETSIMD_WRAPPER is a binary
            with open(NETSIMD_WRAPPER, "rb") as f:
                header = f.read(4)
            if header in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
                shutil.copyfile(NETSIMD_WRAPPER, NETSIMD_ORIG)
                log(f"Backed up original netsimd to {NETSIMD_ORIG}")

    if not os.path.exists(NETSIMD_ORIG):
        log("Cannot patch netsimd: netsimd.orig not found")
        return False

    bssid_str = state.get("bssid")
    vnet_str = state.get("vnet")
    mask_str = state.get("subnet_mask")
    gw_str = state.get("gateway")
    phone_ip_str = state.get("phone_ip")
    dns_str = state.get("dns", ["8.8.8.8"])[0]

    if not (bssid_str and vnet_str and mask_str and gw_str and phone_ip_str and dns_str):
        log("Missing parameters for netsimd binary patch")
        return False

    # Copy orig to bin
    shutil.copyfile(NETSIMD_ORIG, NETSIMD_BIN)
    os.chmod(NETSIMD_BIN, 0o755)

    with open(NETSIMD_BIN, "r+b") as f:
        data = f.read()

        # 1. Patch BSSID (17 bytes: e.g. "00:13:10:85:fe:01" -> "74:4d:28:43:0c:17")
        idx_bssid = data.find(b"00:13:10:85:fe:01")
        if idx_bssid != -1:
            f.seek(idx_bssid)
            f.write(bssid_str.encode("utf-8")[:17])
            log(f"Patched netsimd BSSID at offset {hex(idx_bssid)} to {bssid_str}")
        else:
            log("Warning: default BSSID string not found in netsimd")

        # 2. Patch SlirpConfig 20-byte struct
        # Pattern: [10, 0, 2, 0,  255, 255, 255, 0,  10, 0, 2, 2,  10, 0, 2, 16,  10, 0, 2, 3]
        idx_struct = data.find(b"\x0a\x00\x02\x02")
        if idx_struct != -1 and data[idx_struct - 8:idx_struct] == b"\x0a\x00\x02\x00\xff\xff\xff\x00":
            vnet_b = bytes(int(x) for x in vnet_str.split("."))
            mask_b = bytes(int(x) for x in mask_str.split("."))
            gw_b = bytes(int(x) for x in gw_str.split("."))
            phone_b = bytes(int(x) for x in phone_ip_str.split("."))
            dns_b = bytes(int(x) for x in dns_str.split("."))

            new_struct = vnet_b + mask_b + gw_b + phone_b + dns_b
            f.seek(idx_struct - 8)
            f.write(new_struct)
            log(f"Patched netsimd SlirpConfig at offset {hex(idx_struct - 8)}: vnet={vnet_str}, mask={mask_str}, gw={gw_str}, phone_ip={phone_ip_str}, dns={dns_str}")
        else:
            log("Warning: SlirpConfig struct not found in netsimd")

        # 3. Erase AndroidWifi from netsimd hostapd template
        idx_wifi = data.find(b"AndroidWifi")
        if idx_wifi != -1:
            f.seek(idx_wifi)
            f.write(b"Galaxy_WiFi")
            log(f"Patched netsimd default SSID at offset {hex(idx_wifi)}: AndroidWifi -> Galaxy_WiFi")

    # Resign binary
    res = subprocess.run(["codesign", "-s", "-", "--force", NETSIMD_BIN], capture_output=True, text=True)
    if res.returncode == 0:
        log("Successfully ad-hoc codesigned netsimd.bin")
        return True
    else:
        log(f"Codesign failed for netsimd.bin: {res.stderr}")
        return False

def sync_android_network(state):
    """
    Applies live Wi-Fi configuration into Android 16.
    """
    dev_state = run_cmd("adb get-state")
    if dev_state != "device":
        return

    ssid = state.get("ssid")
    bssid = state.get("bssid")
    gateway = state.get("gateway")
    phone_ip = state.get("phone_ip")
    prefix = state.get("prefix", 24)

    if not ssid or not gateway:
        return

    # Update Android Routing Table to real gateway
    run_adb(f"shell \"ip route replace default via {gateway} dev wlan0 table 1016 2>/dev/null\"")
    run_adb(f"shell \"ip route replace default via {gateway} dev wlan0 2>/dev/null\"")

    if phone_ip:
        run_adb(f"shell \"ip addr add {phone_ip}/{prefix} dev wlan0 2>/dev/null || ip addr replace {phone_ip}/{prefix} dev wlan0 2>/dev/null\"")

    # Ensure no shell suggestions exist (prevents 'Connected via Shell' subtitle)
    run_adb("shell cmd wifi remove-all-suggestions >/dev/null 2>&1")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def daemon_loop():
    log(f"Samsung Electronics Wi-Fi Service started (PID {os.getpid()})")
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    while True:
        try:
            mac_state = get_mac_network_state()
            last_state = load_state()

            gateway_changed = mac_state.get("gateway") != last_state.get("gateway")
            bssid_changed = mac_state.get("bssid") != last_state.get("bssid")
            ssid_changed = mac_state.get("ssid") != last_state.get("ssid")
            mask_changed = mac_state.get("subnet_mask") != last_state.get("subnet_mask")

            if gateway_changed or bssid_changed or ssid_changed or mask_changed or not last_state:
                log(f"Active Network: SSID='{mac_state.get('ssid')}', Gateway={mac_state.get('gateway')}, BSSID={mac_state.get('bssid')}, Mask={mac_state.get('subnet_mask')}, CIDR={mac_state.get('net_cidr')}, PhoneIP={mac_state.get('phone_ip')}")
                if mac_state.get("ssid") and mac_state.get("bssid"):
                    sync_hostapd_conf(mac_state["ssid"], mac_state["bssid"])
                patch_netsimd_binary(mac_state)
                sync_android_network(mac_state)
                save_state(mac_state)
            else:
                sync_android_network(mac_state)

            time.sleep(10)
        except Exception as e:
            log(f"Error in daemon: {e}")
            time.sleep(10)

def stop_daemon():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"🛑 Stopped daemon (PID {pid})")
        except Exception:
            pass
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

def main():
    if len(sys.argv) < 2:
        print("Usage: sec_wifi_service.py [start|stop|status|sync]")
        return

    cmd = sys.argv[1].lower()

    if cmd == "daemon":
        daemon_loop()
    elif cmd == "start":
        stop_daemon()
        script = os.path.abspath(__file__)
        proc = subprocess.Popen([sys.executable, "-u", script, "daemon"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print(f"🚀 Started Samsung Wi-Fi Service in background (PID {proc.pid})")
    elif cmd == "stop":
        stop_daemon()
    elif cmd == "status":
        state = load_state()
        if not state:
            state = get_mac_network_state()
        print("📡 Samsung Galaxy S24 Ultra Wi-Fi Status:")
        print(f"   SSID: {state.get('ssid', 'N/A')}")
        print(f"   Router BSSID: {state.get('bssid', 'N/A')}")
        print(f"   Default Gateway: {state.get('gateway', 'N/A')}")
        print(f"   Mac IP: {state.get('mac_ip', 'N/A')}")
        print(f"   Phone IP: {state.get('phone_ip', 'N/A')}")
        print(f"   Subnet Mask: {state.get('subnet_mask', 'N/A')}")
        print(f"   Network CIDR: {state.get('net_cidr', 'N/A')}")
        print(f"   DNS Servers: {', '.join(state.get('dns', []))}")
    elif cmd == "sync":
        state = get_mac_network_state()
        print("🔄 Performing one-shot sync...")
        sync_hostapd_conf(state.get("ssid"), state.get("bssid"))
        patch_netsimd_binary(state)
        sync_android_network(state)
        save_state(state)
        print(f"✅ Synchronized with {state.get('ssid')} (Gateway: {state.get('gateway')}, BSSID: {state.get('bssid')}, Phone IP: {state.get('phone_ip')})")
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
