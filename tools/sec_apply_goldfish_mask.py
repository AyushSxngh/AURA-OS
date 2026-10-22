#!/usr/bin/env python3
"""
sec_apply_goldfish_mask.py
Audit and deploy Goldfish & QEMU driver filesystem masking.
Reports visibility of kernel drivers, character devices, and proc signatures.
"""

import os
import sys
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHELL_SCRIPT = os.path.join(SCRIPT_DIR, "sec_mask_goldfish_drivers.sh")

SIGNATURES = [
    {"type": "dev", "path": "/dev/qemu_pipe", "desc": "Legacy QEMU guest pipe"},
    {"type": "dev", "path": "/dev/socket/qemud", "desc": "QEMU multiplexer domain socket"},
    {"type": "dev", "path": "/dev/goldfish_pipe_dprctd", "desc": "Deprecated Goldfish pipe"},
    {"type": "dev", "path": "/dev/goldfish_sync", "desc": "Goldfish sync driver node"},
    {"type": "dev", "path": "/dev/goldfish_address_space", "desc": "Goldfish memory mapping node"},
    {"type": "sys", "path": "/sys/bus/platform/drivers/goldfish_pipe", "desc": "Goldfish pipe platform driver"},
    {"type": "sys", "path": "/sys/bus/platform/drivers/goldfish-battery", "desc": "Goldfish battery platform driver"},
    {"type": "sys", "path": "/sys/bus/platform/drivers/goldfish_sync", "desc": "Goldfish sync platform driver"},
    {"type": "proc", "path": "/proc/interrupts", "desc": "Goldfish IRQ lines in interrupts table"},
    {"type": "bin", "path": "/system/bin/qemu-props", "desc": "QEMU property daemon binary"}
]

def adb_shell(cmd):
    full_cmd = ["adb", "shell", cmd]
    res = subprocess.run(full_cmd, capture_output=True, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def audit_filesystem():
    print(f"{'Target Path':<42} | {'Description':<32} | {'Status':<12}")
    print("-" * 92)
    detected = 0
    for sig in SIGNATURES:
        path = sig["path"]
        stype = sig["type"]
        desc = sig["desc"]

        if stype == "proc":
            out, _, _ = adb_shell(f"grep -i 'goldfish' {path} 2>/dev/null")
            status = "🚨 DETECTED" if out else "✅ CLEAN"
            if out: detected += 1
        else:
            out, _, rc = adb_shell(f"test -e {path} && echo EXISTS || echo NONE")
            if out == "EXISTS":
                # Check permissions
                perms, _, _ = adb_shell(f"ls -ld {path} 2>/dev/null")
                if "---" in perms[:4]:
                    status = "🛡️ MASKED (000)"
                else:
                    status = "🚨 DETECTED"
                    detected += 1
            else:
                status = "✅ CLEAN (Absent)"

        print(f"{path:<42} | {desc:<32} | {status}")
    print("-" * 92)
    print(f"Summary: {detected} visible Goldfish/QEMU signatures detected.\n")
    return detected

def deploy_mask():
    print("Pushing sec_mask_goldfish_drivers.sh to device...")
    subprocess.run(["adb", "push", SHELL_SCRIPT, "/data/local/tmp/sec_mask_goldfish_drivers.sh"], check=True)
    subprocess.run(["adb", "shell", "chmod", "755", "/data/local/tmp/sec_mask_goldfish_drivers.sh"], check=True)

    print("Executing masking script on device...")
    # Attempt execution directly or with su if available
    out, err, rc = adb_shell("sh /data/local/tmp/sec_mask_goldfish_drivers.sh")
    print("Execution output:")
    if out: print(out)
    if err: print("Stderr:", err)

    # If Magisk is present, install to /data/adb/service.d/
    out_magisk, _, _ = adb_shell("test -d /data/adb/service.d && echo YES || echo NO")
    if out_magisk == "YES":
        print("Detected Magisk environment! Installing persistence script to /data/adb/service.d/...")
        adb_shell("cp /data/local/tmp/sec_mask_goldfish_drivers.sh /data/adb/service.d/00_sec_mask_goldfish.sh")
        adb_shell("chmod 755 /data/adb/service.d/00_sec_mask_goldfish.sh")
        print("Installed to /data/adb/service.d/00_sec_mask_goldfish.sh (runs at every boot).")

def main():
    print("=== GOLDFISH & QEMU DRIVER FILESYSTEM AUDIT (BEFORE) ===")
    audit_filesystem()

    deploy_mask()

    print("\n=== GOLDFISH & QEMU DRIVER FILESYSTEM AUDIT (AFTER) ===")
    audit_filesystem()

if __name__ == "__main__":
    main()
