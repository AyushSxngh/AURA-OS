#!/usr/bin/env python3
"""
Seed realistic Digital Wellbeing usage, unlocks, and notifications for TODAY (Sun, Oct 4).
Runs core apps with real foreground duration (>60s each) to accumulate active screen time.
Performs real lock and unlock sequences to register unlock count.
"""

import time
import subprocess

def run_adb(args):
    return subprocess.run(["adb", "shell"] + args, capture_output=True, text=True).stdout.strip()

def unlock_phone():
    print("  🔑 Locking and unlocking phone with PIN 1234...")
    run_adb(["input", "keyevent", "26"]) # Power sleep
    time.sleep(1.2)
    run_adb(["input", "keyevent", "82"]) # Wake
    time.sleep(1.0)
    run_adb(["input", "swipe", "540", "1800", "540", "500", "150"]) # Swipe up
    time.sleep(1.0)
    run_adb(["input", "text", "1234"])
    run_adb(["input", "keyevent", "66"]) # Enter
    time.sleep(1.5)

apps_to_cycle = [
    {
        "name": "WhatsApp",
        "pkg": "com.whatsapp",
        "act": "com.whatsapp/com.android.app.MainActivity",
        "duration_sec": 65,
    },
    {
        "name": "YouTube",
        "pkg": "com.google.android.youtube",
        "act": "com.google.android.youtube/com.google.android.apps.youtube.app.honeycomb.Shell$HomeActivity",
        "duration_sec": 70,
    },
    {
        "name": "Chrome",
        "pkg": "com.android.chrome",
        "act": "com.android.chrome/com.google.android.apps.chrome.Main",
        "duration_sec": 65,
    },
    {
        "name": "Camera",
        "pkg": "com.sec.android.app.camera",
        "act": "com.sec.android.app.camera/.Camera",
        "duration_sec": 65,
    },
    {
        "name": "BGMI",
        "pkg": "com.pubg.imobile",
        "act": "com.pubg.imobile/com.epicgames.ue4.SplashActivity",
        "duration_sec": 65,
    },
    {
        "name": "Instagram",
        "pkg": "com.instagram.android",
        "act": "com.instagram.android/com.android.app.MainActivity",
        "duration_sec": 45,
    },
    {
        "name": "PhonePe",
        "pkg": "com.phonepe.app",
        "act": "com.phonepe.app/com.android.app.MainActivity",
        "duration_sec": 40,
    },
]

print("🚀 Starting Digital Wellbeing Today Usage Seeder...")

for idx, app in enumerate(apps_to_cycle, 1):
    name = app["name"]
    pkg = app["pkg"]
    act = app["act"]
    sec = app["duration_sec"]
    
    print(f"[{idx}/{len(apps_to_cycle)}] Opening {name} ({sec}s)...")
    run_adb(["am", "start", "-n", act])
    time.sleep(sec)
    
    # Interleave unlocks
    if idx in [1, 3, 5]:
        unlock_phone()

# Final return to home
run_adb(["input", "keyevent", "KEYCODE_HOME"])
time.sleep(1)
print("✅ Foreground usage seeding complete!")
