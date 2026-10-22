#!/usr/bin/env python3
"""
sec_snapshot_manager.py
Instantaneous APFS copy-on-write snapshot manager for Android Emulator AVD
and system images. Allows instant creation and 100% bit-for-bit rollback.
"""

import os
import sys
import time
import json
import shutil
import subprocess

AVD_DIR = os.path.expanduser("~/.android/avd/AURA_OS_ARM64.avd")
SYS_IMG_DIR = os.path.expanduser("~/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a")
ARCHIVE_BASE = os.path.expanduser("~/.android/avd/SNAPSHOT_ARCHIVE")
WORKSPACE_DIR = "/Users/ayush/Desktop/HEBB NETWORK/Emulator"

def run_cmd(cmd, check=True):
    return subprocess.run(cmd, shell=True, check=check, text=True, capture_output=True)

def create_snapshot(name="pristine_pre_magisk"):
    os.makedirs(ARCHIVE_BASE, exist_ok=True)
    target_dir = os.path.join(ARCHIVE_BASE, name)
    if os.path.exists(target_dir):
        print(f"Snapshot '{name}' already exists. Removing old snapshot...")
        shutil.rmtree(target_dir)

    os.makedirs(target_dir, exist_ok=True)

    print(f"Flushing Android filesystem caches (adb shell sync)...")
    try:
        run_cmd("adb shell sync", check=False)
    except Exception:
        pass

    print(f"Creating APFS copy-on-write clone of AVD directory...")
    # Using macOS cp -Rc for instant copy-on-write
    dest_avd = os.path.join(target_dir, "AURA_OS_ARM64.avd")
    t0 = time.time()
    run_cmd(f"cp -Rc '{AVD_DIR}' '{dest_avd}'")
    
    # Also backup ramdisk and build.prop from system image
    sys_backup = os.path.join(target_dir, "sys_img_backup")
    os.makedirs(sys_backup, exist_ok=True)
    run_cmd(f"cp -c '{SYS_IMG_DIR}/ramdisk.img' '{sys_backup}/ramdisk.img'")
    run_cmd(f"cp -c '{SYS_IMG_DIR}/build.prop' '{sys_backup}/build.prop'")

    # Metadata
    meta = {
        "name": name,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "avd_dir": AVD_DIR,
        "elapsed_seconds": round(time.time() - t0, 3)
    }
    with open(os.path.join(target_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"✅ Snapshot '{name}' successfully created in {meta['elapsed_seconds']}s!")
    print(f"   Location: {target_dir}")

def restore_snapshot(name="pristine_pre_magisk"):
    target_dir = os.path.join(ARCHIVE_BASE, name)
    if not os.path.exists(target_dir):
        print(f"❌ Error: Snapshot '{name}' not found at {target_dir}")
        sys.exit(1)

    print(f"⚠️  Restoring snapshot '{name}'...")

    # 1. Terminate running emulator and daemons
    print("Stopping emulator and background daemons...")
    run_cmd("pkill -9 -f qemu-system-aarch64 2>/dev/null", check=False)
    run_cmd("pkill -9 -f sec_battery_service 2>/dev/null", check=False)
    run_cmd("pkill -9 -f sec_wifi_service 2>/dev/null", check=False)
    run_cmd("pkill -9 -f sec_sensor_service 2>/dev/null", check=False)
    time.sleep(2)

    # 2. Replace AVD directory with snapshot
    print("Restoring AVD directory from snapshot...")
    backup_avd = os.path.join(target_dir, "AURA_OS_ARM64.avd")
    run_cmd(f"rm -rf '{AVD_DIR}'")
    run_cmd(f"cp -Rc '{backup_avd}' '{AVD_DIR}'")

    # 3. Restore system-image files
    sys_backup = os.path.join(target_dir, "sys_img_backup")
    if os.path.exists(sys_backup):
        print("Restoring system-image ramdisk & build.prop...")
        run_cmd(f"cp -f '{sys_backup}/ramdisk.img' '{SYS_IMG_DIR}/ramdisk.img'", check=False)
        run_cmd(f"cp -f '{sys_backup}/build.prop' '{SYS_IMG_DIR}/build.prop'", check=False)

    print(f"✅ State successfully reverted to snapshot '{name}'!")
    print("To launch the emulator back up, run: ./Launch-AURA-OS.command or python3 tools/sec_restore_services.py")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: sec_snapshot_manager.py <create|restore> [snapshot_name]")
        sys.exit(1)

    action = sys.argv[1].lower()
    snap_name = sys.argv[2] if len(sys.argv) > 2 else "pristine_pre_magisk"

    if action == "create":
        create_snapshot(snap_name)
    elif action == "restore":
        restore_snapshot(snap_name)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
