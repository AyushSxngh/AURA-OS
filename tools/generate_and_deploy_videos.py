#!/usr/bin/env python3
"""
generate_and_deploy_videos.py
Generates a realistic suite of video recordings and audio files
tailored for a Samsung Galaxy S24 Ultra, pushes them to Android,
and indexes them into Android MediaStore.
"""

import os
import random
import subprocess
import time
from datetime import datetime, timedelta

LOCAL_BASE = "/tmp/fake_media"
FFMPEG = "/opt/homebrew/bin/ffmpeg"

def ensure_dirs():
    os.makedirs(f"{LOCAL_BASE}/DCIM/Camera", exist_ok=True)
    os.makedirs(f"{LOCAL_BASE}/DCIM/Screen_recordings", exist_ok=True)
    os.makedirs(f"{LOCAL_BASE}/Pictures/WhatsApp", exist_ok=True)
    os.makedirs(f"{LOCAL_BASE}/Recordings", exist_ok=True)

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip(), res.stderr.strip(), res.returncode

def generate_video(out_path, width, height, duration_sec, creation_dt, video_type="camera"):
    dt_iso = creation_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Visual effects per type
    if video_type == "camera":
        # Realistic camera panning / color waves
        freq = random.choice([220, 330, 440])
        # Use mandelbrot or testsrc or color filters with movement
        filters = f"color=c=0x{random.randint(0x20,0x80):02x}{random.randint(0x40,0xa0):02x}{random.randint(0x60,0xd0):02x}:s={width}x{height}:d={duration_sec},drawgrid=w=120:h=120:t=2:c=white@0.1"
    elif video_type == "screen":
        # Screen recording mockup
        filters = f"color=c=0x1a1a24:s={width}x{height}:d={duration_sec},drawbox=x=60:y=200:w={width-120}:h=600:color=0x2563eb@0.8:t=fill"
    else: # whatsapp
        filters = f"color=c=0x{random.randint(0x30,0x90):02x}{random.randint(0x20,0x70):02x}{random.randint(0x10,0x50):02x}:s={width}x{height}:d={duration_sec}"
        
    cmd = (
        f"{FFMPEG} -y -f lavfi -i \"{filters}\" "
        f"-f lavfi -i \"sine=frequency={random.randint(180, 400)}:duration={duration_sec}\" "
        f"-c:v libx264 -preset ultrafast -pix_fmt yuv420p -b:v 1500k "
        f"-c:a aac -b:a 128k "
        f"-metadata creation_time=\"{dt_iso}\" "
        f"-metadata artist=\"Samsung SM-S928B\" "
        f"\"{out_path}\""
    )
    run_cmd(cmd)
    
    # Update local filesystem timestamp
    mtime = creation_dt.timestamp()
    os.utime(out_path, (mtime, mtime))

def generate_audio(out_path, duration_sec, creation_dt, title="Voice note"):
    dt_iso = creation_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    freq = random.randint(200, 500)
    cmd = (
        f"{FFMPEG} -y -f lavfi -i \"sine=frequency={freq}:duration={duration_sec}\" "
        f"-c:a aac -b:a 128k "
        f"-metadata title=\"{title}\" "
        f"-metadata creation_time=\"{dt_iso}\" "
        f"-metadata artist=\"Samsung Voice Recorder\" "
        f"\"{out_path}\""
    )
    run_cmd(cmd)
    mtime = creation_dt.timestamp()
    os.utime(out_path, (mtime, mtime))

def main():
    ensure_dirs()
    print("1. Generating camera videos...")
    base_dt = datetime(2026, 5, 20, 14, 0, 0)
    current_dt = base_dt
    
    # 15 Camera videos
    for i in range(15):
        current_dt += timedelta(days=random.randint(7, 12), hours=random.randint(1, 6), minutes=random.randint(1, 40))
        if current_dt > datetime(2026, 10, 10, 22, 0, 0):
            current_dt = datetime(2026, 10, 10, 15, 0, 0)
        dur = random.randint(4, 15)
        # S24 Ultra records 1920x1080 FHD or 3840x2160 4K
        w, h = 1920, 1080
        fname = f"{current_dt.strftime('%Y%m%d_%H%M%S')}.mp4"
        fpath = f"{LOCAL_BASE}/DCIM/Camera/{fname}"
        generate_video(fpath, w, h, dur, current_dt, "camera")
        
    print("Generated 15 camera videos.")
    
    # 8 WhatsApp videos
    print("2. Generating WhatsApp videos...")
    wa_dt = datetime(2026, 6, 1, 11, 0, 0)
    for i in range(8):
        wa_dt += timedelta(days=random.randint(12, 18), hours=random.randint(1, 5))
        if wa_dt > datetime(2026, 10, 10, 20, 0, 0):
            wa_dt = datetime(2026, 10, 10, 12, 0, 0)
        dur = random.randint(5, 12)
        fname = f"VID-{wa_dt.strftime('%Y%m%d')}-WA{i+1:04d}.mp4"
        fpath = f"{LOCAL_BASE}/Pictures/WhatsApp/{fname}"
        generate_video(fpath, 1280, 720, dur, wa_dt, "whatsapp")
        
    print("Generated 8 WhatsApp videos.")
    
    # 3 Screen recordings
    print("3. Generating Screen recordings...")
    sr_dt = datetime(2026, 7, 5, 16, 30, 0)
    for i in range(3):
        sr_dt += timedelta(days=random.randint(20, 35))
        dur = random.randint(6, 14)
        fname = f"Screen_Recording_{sr_dt.strftime('%Y%m%d_%H%M%S')}.mp4"
        fpath = f"{LOCAL_BASE}/DCIM/Screen_recordings/{fname}"
        generate_video(fpath, 1080, 2340, dur, sr_dt, "screen")
        
    print("Generated 3 Screen recordings.")
    
    # 10 Audio voice recordings
    print("4. Generating voice recordings...")
    rec_dt = datetime(2026, 5, 25, 10, 0, 0)
    for i in range(10):
        rec_dt += timedelta(days=random.randint(10, 15))
        if rec_dt > datetime(2026, 10, 10, 18, 0, 0):
            rec_dt = datetime(2026, 10, 10, 10, 0, 0)
        dur = random.randint(15, 60)
        fname = f"Voice_{rec_dt.strftime('%Y%m%d_%H%M%S')}.m4a"
        fpath = f"{LOCAL_BASE}/Recordings/{fname}"
        generate_audio(fpath, dur, rec_dt, f"Recording {i+1}")
        
    print("Generated 10 Voice recordings.")
    
    # Deploy to device
    print("5. Deploying to Android device...")
    run_cmd("adb shell 'mkdir -p /sdcard/DCIM/Camera /sdcard/DCIM/Screen_recordings /sdcard/Pictures/WhatsApp /sdcard/Recordings'")
    run_cmd(f"adb push {LOCAL_BASE}/DCIM/Camera/. /sdcard/DCIM/Camera/")
    run_cmd(f"adb push {LOCAL_BASE}/DCIM/Screen_recordings/. /sdcard/DCIM/Screen_recordings/")
    run_cmd(f"adb push {LOCAL_BASE}/Pictures/WhatsApp/. /sdcard/Pictures/WhatsApp/")
    run_cmd(f"adb push {LOCAL_BASE}/Recordings/. /sdcard/Recordings/")
    
    # Build touch & media scan script
    print("6. Scanning into MediaStore...")
    scan_lines = []
    for root, dirs, files in os.walk(LOCAL_BASE):
        rel_dir = os.path.relpath(root, LOCAL_BASE)
        dest_dir = f"/storage/emulated/0/{rel_dir}" if rel_dir != "." else "/storage/emulated/0"
        for f in files:
            local_path = os.path.join(root, f)
            dest_path = f"{dest_dir}/{f}"
            mtime = os.path.getmtime(local_path)
            dt = datetime.fromtimestamp(mtime)
            touch_time = dt.strftime("%Y%m%d%H%M.%S")
            scan_lines.append(f"touch -t {touch_time} '{dest_path}'")
            scan_lines.append(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d 'file://{dest_path}' >/dev/null")
            
    with open("/tmp/scan_vid.sh", "w") as f:
        f.write("#!/system/bin/sh\n" + "\n".join(scan_lines) + "\n")
        
    run_cmd("adb push /tmp/scan_vid.sh /data/local/tmp/scan_vid.sh")
    run_cmd("adb shell 'chmod 755 /data/local/tmp/scan_vid.sh && sh /data/local/tmp/scan_vid.sh && rm /data/local/tmp/scan_vid.sh'")
    
    time.sleep(2)
    print("7. MediaStore verification:")
    out_v, _, _ = run_cmd("adb shell 'content query --uri content://media/external/video/media | wc -l'")
    print(f"Total indexed videos: {out_v}")
    out_a, _, _ = run_cmd("adb shell 'content query --uri content://media/external/audio/media | wc -l'")
    print(f"Total indexed audio files: {out_a}")

if __name__ == "__main__":
    main()
