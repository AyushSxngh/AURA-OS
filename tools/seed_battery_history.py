#!/usr/bin/env python3
"""
AURA OS — Historical Battery Usage & App Breakdown Seeder
Populates Settings -> Battery -> Battery Usage with realistic Samsung S24 Ultra data:
1. Simulates past charging to 100% full
2. Simulates unplugging and stepped discharge down to current level
3. Runs background and foreground tasks across key consumer apps (Chrome, YouTube, Camera, WhatsApp, System UI, Host)
4. Attributes realistic mAh and percentage power usage
5. Flushes batterystats and informs BatteryUsageBroadcastReceiver
"""

import os
import sys
import time
import subprocess

def run_adb(cmd):
    try:
        res = subprocess.run(f"adb {cmd}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def seed_history(target_level=42):
    print("⏳ Seeding realistic Samsung Galaxy S24 Ultra battery usage history...")

    # 1. Reset old stats to ensure clean historical attribution
    print("  1. Clearing old battery stats...")
    run_adb("shell dumpsys batterystats --reset")
    run_adb("shell dumpsys battery reset")

    # 2. Simulate device was fully charged to 100%
    print("  2. Simulating full 100% charge cycle...")
    run_adb("shell dumpsys battery set status 5")  # Full
    run_adb("shell dumpsys battery set ac 1")
    run_adb("shell dumpsys battery set level 100")
    run_adb("shell dumpsys battery set voltage 4350")
    run_adb("shell dumpsys battery set temp 335")
    run_adb("shell dumpsys battery set counter 5000000")
    run_adb("shell dumpsys batterystats --history-create-events 30")
    run_adb("shell am broadcast -a com.android.settings.battery.action.ACTION_BATTERY_PLUGGING -n com.android.settings/.fuelgauge.batteryusage.BatteryUsageBroadcastReceiver")
    time.sleep(1)

    # 3. Simulate unplugging
    print("  3. Simulating unplugging charger...")
    run_adb("shell dumpsys battery unplug")
    run_adb("shell dumpsys battery set status 3")  # Discharging
    run_adb("shell dumpsys battery set ac 0")
    run_adb("shell dumpsys battery set temp 305")
    run_adb("shell am broadcast -a com.android.settings.battery.action.ACTION_BATTERY_UNPLUGGING -n com.android.settings/.fuelgauge.batteryusage.BatteryUsageBroadcastReceiver")
    time.sleep(1)

    # 4. Step down levels while executing real app workloads
    # Apps to attribute:
    # - Chrome (browser)
    # - Camera (photo / video)
    # - YouTube (media)
    # - Host app (Sentinel)
    # - Settings
    steps = [
        (92, 4220, 4600000, "com.android.chrome"),
        (81, 4140, 4050000, "com.google.android.youtube"),
        (68, 4050, 3400000, "com.android.camera2"),
        (55, 3960, 2750000, "com.sentinel.host"),
        (target_level, 3880, int(target_level * 50000), "com.android.settings")
    ]

    for lvl, v_mv, counter, pkg in steps:
        print(f"  ⚡ Discharge step -> {lvl}% ({v_mv}mV, {counter // 1000}mAh) attributing {pkg}...")
        run_adb(f"shell dumpsys battery set level {lvl}")
        run_adb(f"shell dumpsys battery set voltage {v_mv}")
        run_adb(f"shell dumpsys battery set counter {counter}")
        
        # Briefly launch app to generate CPU cycles and process time
        run_adb(f"shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1")
        time.sleep(1.5)
        
        # Tap screen center to register active user screen-on touch interaction
        run_adb("shell input tap 720 1560")
        
        # Notify battery level step
        run_adb("shell am broadcast -a android.intent.action.BATTERY_LEVEL_CHANGED -n com.android.settings/.fuelgauge.batteryusage.BatteryUsageBroadcastReceiver")
        run_adb("shell dumpsys batterystats --history-create-events 10")

    # 5. Bring Settings to foreground to show result
    print("  5. Committing stats & opening Battery Usage summary...")
    run_adb("shell dumpsys batterystats --write")
    run_adb("shell am start -a android.intent.action.POWER_USAGE_SUMMARY")
    time.sleep(2)

    print("✅ Battery history successfully seeded!")

if __name__ == "__main__":
    lvl = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    seed_history(lvl)
