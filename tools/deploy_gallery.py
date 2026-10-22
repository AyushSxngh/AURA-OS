#!/usr/bin/env python3
"""
deploy_gallery.py
Pushes the generated gallery to the Android device, fixes filesystem timestamps,
and indexes every file into Android MediaStore.
"""

import os
import subprocess
import time
from datetime import datetime

LOCAL_BASE = "/tmp/fake_gallery"

def run_adb(cmd):
    full_cmd = f"adb {cmd}"
    res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def main():
    print("1. Cleaning loose screenshots from /sdcard root...")
    out, _, _ = run_adb("shell 'rm -f /sdcard/*.png /sdcard/*.xml'")
    
    print("2. Ensuring destination directories on device...")
    run_adb("shell 'mkdir -p /sdcard/DCIM/Camera /sdcard/DCIM/Screenshots /sdcard/Pictures/WhatsApp'")
    
    # Push DCIM/Camera
    print("3. Pushing DCIM/Camera photos...")
    run_adb(f"push {LOCAL_BASE}/DCIM/Camera/. /sdcard/DCIM/Camera/")
    
    # Push DCIM/Screenshots
    print("4. Pushing DCIM/Screenshots...")
    run_adb(f"push {LOCAL_BASE}/DCIM/Screenshots/. /sdcard/DCIM/Screenshots/")
    
    # Push Pictures/WhatsApp
    print("5. Pushing Pictures/WhatsApp...")
    run_adb(f"push {LOCAL_BASE}/Pictures/WhatsApp/. /sdcard/Pictures/WhatsApp/")
    
    print("6. Setting filesystem timestamps & scanning into MediaStore...")
    # List all local files to get their mtimes
    scan_commands = []
    for root, dirs, files in os.walk(LOCAL_BASE):
        rel_dir = os.path.relpath(root, LOCAL_BASE)
        dest_dir = f"/storage/emulated/0/{rel_dir}" if rel_dir != "." else "/storage/emulated/0"
        for f in files:
            if not f.endswith(".jpg"): continue
            local_path = os.path.join(root, f)
            dest_path = f"{dest_dir}/{f}"
            mtime = os.path.getmtime(local_path)
            dt = datetime.fromtimestamp(mtime)
            # touch format: [[CC]YY]MMDDhhmm[.ss]
            touch_time = dt.strftime("%Y%m%d%H%M.%S")
            scan_commands.append((dest_path, touch_time))
            
    # Batch touch and scan
    print(f"Total media files to register: {len(scan_commands)}")
    shell_batch = []
    for dest_path, touch_time in scan_commands:
        shell_batch.append(f"touch -t {touch_time} '{dest_path}'")
        shell_batch.append(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d 'file://{dest_path}' >/dev/null")
        
    # Write to a temporary shell script and run it on device for high speed
    script_content = "#!/system/bin/sh\n" + "\n".join(shell_batch) + "\n"
    with open("/tmp/scan_script.sh", "w") as f:
        f.write(script_content)
        
    run_adb("push /tmp/scan_script.sh /data/local/tmp/scan_script.sh")
    run_adb("shell 'chmod 755 /data/local/tmp/scan_script.sh && sh /data/local/tmp/scan_script.sh && rm /data/local/tmp/scan_script.sh'")
    
    print("7. Verifying MediaStore contents...")
    time.sleep(2)
    out, _, _ = run_adb("shell 'content query --uri content://media/external/images/media | wc -l'")
    print(f"Total indexed images in MediaStore: {out}")
    
    out_camera, _, _ = run_adb("shell 'ls -1 /sdcard/DCIM/Camera | wc -l'")
    print(f"Files in /sdcard/DCIM/Camera: {out_camera}")
    
    out_ss, _, _ = run_adb("shell 'ls -1 /sdcard/DCIM/Screenshots | wc -l'")
    print(f"Files in /sdcard/DCIM/Screenshots: {out_ss}")
    
    out_wa, _, _ = run_adb("shell 'ls -1 /sdcard/Pictures/WhatsApp | wc -l'")
    print(f"Files in /sdcard/Pictures/WhatsApp: {out_wa}")

if __name__ == "__main__":
    main()
