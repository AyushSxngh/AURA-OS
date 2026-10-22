#!/usr/bin/env python3
"""
Samsung Electronics Co., Ltd. — Galaxy S24 Ultra Hardware Location Service
Daemon ensuring the Android guest GPS continuously matches the host's public IP
and physical geolocation in real time.

Features:
1. Real-time host public IP geolocation discovery (ipinfo.io / ip-api.com).
2. Continuous GNSS stream: feeds fresh NMEA/GPS fixes via 'geo fix' every 3 seconds.
3. Realistic satellite noise: ±0.000005 deg micro-jitter + realistic altitude fluctuation
   so location timestamps never go stale in Android LocationManager / FusedLocationProvider.
4. Full CLI control: status, sync, set coordinates, daemon, start/stop.
"""

import os
import sys
import time
import json
import random
import urllib.request
import subprocess
import signal

STATE_FILE = "/tmp/sec_location_state.json"
PID_FILE = "/tmp/sec_location_service.pid"
LOG_FILE = "/tmp/sec_location_service.log"
ADB_BIN = "/opt/homebrew/bin/adb" if os.path.exists("/opt/homebrew/bin/adb") else "adb"

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] [sec_location_service] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def fetch_ip_location() -> dict:
    """Fetch geographic coordinates corresponding to current public IP."""
    # Try ipinfo.io first (accurate city and postal resolution)
    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if "loc" in data:
                lat, lon = data["loc"].split(",")
                return {
                    "ip": data.get("ip", ""),
                    "city": data.get("city", "Ghaziabad"),
                    "region": data.get("region", "Uttar Pradesh"),
                    "country": data.get("country", "IN"),
                    "lat": float(lat),
                    "lon": float(lon),
                    "postal": data.get("postal", "201009"),
                    "source": "ipinfo.io"
                }
    except Exception as e:
        log(f"ipinfo.io lookup failed: {e}")

    # Fallback to ip-api.com
    try:
        req = urllib.request.Request("http://ip-api.com/json", headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                return {
                    "ip": data.get("query", ""),
                    "city": data.get("city", "Ghaziabad"),
                    "region": data.get("regionName", "Uttar Pradesh"),
                    "country": data.get("countryCode", "IN"),
                    "lat": float(data.get("lat", 28.6654)),
                    "lon": float(data.get("lon", 77.4391)),
                    "postal": data.get("zip", ""),
                    "source": "ip-api.com"
                }
    except Exception as e:
        log(f"ip-api.com lookup failed: {e}")

    # Fallback to default physical location (Omega II / Ansal Golf Links 1, Greater Noida)
    return {
        "ip": "122.161.53.189",
        "city": "Omega II, Greater Noida",
        "region": "Uttar Pradesh",
        "country": "IN",
        "lat": 28.4570,
        "lon": 77.5058,
        "postal": "201308",
        "source": "manual_override"
    }

def load_or_init_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if "lat" in data and "lon" in data:
                    return data
        except Exception:
            pass
    state = fetch_ip_location()
    save_state(state)
    return state

def save_state(state: dict):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"Failed to save state: {e}")

def send_geo_fix(lon: float, lat: float, alt: float = 210.0, satellites: int = 12):
    """Send NMEA/GPS fix to Android Emulator via ADB emulator console."""
    cmd = [ADB_BIN, "-s", "emulator-5554", "emu", "geo", "fix", f"{lon:.6f}", f"{lat:.6f}", f"{alt:.1f}", str(satellites)]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        return res.returncode == 0
    except Exception:
        return False

def ensure_guest_location_enabled():
    """Ensure Location Services and High Accuracy mode are active in Android."""
    try:
        subprocess.run([ADB_BIN, "-s", "emulator-5554", "shell", "cmd", "location", "set-location-enabled", "true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        subprocess.run([ADB_BIN, "-s", "emulator-5554", "shell", "settings", "put", "secure", "location_mode", "3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        pass

def run_daemon():
    log("Starting Galaxy S24 Ultra Location Daemon...")
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    state = load_or_init_state()
    base_lat = state["lat"]
    base_lon = state["lon"]
    city = state.get("city", "Ghaziabad")
    log(f"Locked onto target location: {city} (Lat: {base_lat:.6f}, Lon: {base_lon:.6f}) from {state.get('source')}")

    ensure_guest_location_enabled()
    last_ip_check = time.time()

    def handle_term(signum, frame):
        log("Received termination signal. Exiting.")
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_term)
    signal.signal(signal.SIGINT, handle_term)

    while True:
        try:
            # Check for state file updates (e.g. manual override)
            is_manual = False
            if os.path.exists(STATE_FILE):
                try:
                    with open(STATE_FILE, "r") as f:
                        cur = json.load(f)
                        base_lat = cur.get("lat", base_lat)
                        base_lon = cur.get("lon", base_lon)
                        is_manual = cur.get("source") == "manual_override"
                except Exception:
                    pass

            # Periodically re-verify public IP location only if not manually overridden
            if not is_manual and time.time() - last_ip_check > 1800:
                fresh = fetch_ip_location()
                if abs(fresh["lat"] - base_lat) > 0.05 or abs(fresh["lon"] - base_lon) > 0.05:
                    log(f"IP location moved to: {fresh['city']} ({fresh['lat']}, {fresh['lon']})")
                    base_lat = fresh["lat"]
                    base_lon = fresh["lon"]
                    save_state(fresh)
                last_ip_check = time.time()

            # Apply natural GNSS jitter (±0.000003 deg = ~0.3m, realistic satellite drift)
            jitter_lat = base_lat + random.uniform(-0.000003, 0.000003)
            jitter_lon = base_lon + random.uniform(-0.000003, 0.000003)
            alt = 210.0 + random.uniform(-0.4, 0.4)
            sats = random.randint(11, 14)

            send_geo_fix(jitter_lon, jitter_lat, alt, sats)

        except Exception as e:
            log(f"Loop error: {e}")

        time.sleep(3.0)

def main():
    if len(sys.argv) < 2 or sys.argv[1] == "status":
        state = load_or_init_state()
        print("=== Samsung Galaxy S24 Ultra Location Status ===")
        print(f"City:        {state.get('city')}, {state.get('region')}, {state.get('country')}")
        print(f"Public IP:   {state.get('ip')}")
        print(f"Coordinates: Lat {state.get('lat')}, Lon {state.get('lon')}")
        print(f"Postal Code: {state.get('postal')}")
        print(f"Source:      {state.get('source')}")
        pid = None
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE) as f:
                    pid = int(f.read().strip())
            except Exception:
                pass
        running = False
        if pid:
            try:
                os.kill(pid, 0)
                running = True
            except OSError:
                pass
        print(f"Daemon PID:  {pid if running else 'Stopped'}")

    elif sys.argv[1] == "daemon":
        run_daemon()

    elif sys.argv[1] == "sync":
        print("🌐 Refreshing location from current public IP...")
        state = fetch_ip_location()
        save_state(state)
        print(f"✅ Synced to: {state['city']} ({state['lat']}, {state['lon']})")
        send_geo_fix(state['lon'], state['lat'])
        print("📍 Geo fix applied to emulator.")

    elif sys.argv[1] == "set":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--lat", type=float, required=True)
        parser.add_argument("--lon", type=float, required=True)
        parser.add_argument("--city", type=str, default="Custom Location")
        args = parser.parse_args(sys.argv[2:])
        state = {
            "city": args.city,
            "region": "Custom",
            "country": "IN",
            "lat": args.lat,
            "lon": args.lon,
            "source": "manual_override"
        }
        save_state(state)
        send_geo_fix(args.lon, args.lat)
        print(f"✅ Location overridden to: {args.city} ({args.lat}, {args.lon})")

    elif sys.argv[1] == "start":
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                print(f"Daemon already running with PID {pid}")
                return
            except OSError:
                pass
        subprocess.Popen([sys.executable, __file__, "daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        print("Daemon started.")

    elif sys.argv[1] == "stop":
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE) as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"Killed daemon PID {pid}")
            except Exception as e:
                print(f"Error stopping daemon: {e}")
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
        else:
            print("Daemon not running.")

if __name__ == "__main__":
    main()
