#!/usr/bin/env python3
"""
Samsung Electronics Co., Ltd. — Galaxy S24 Ultra Lending App History Seeder
Populates authentic, multi-day usage history for:
  1. com.android.providers.telephony (Transactional SMS, salary credits, loan EMIs, utility bills, UPI)
  2. com.android.settings (Foreground user interactions, display, battery, network, storage)
Specifically tailored to satisfy risk, credit scoring, and anti-fraud engines in lending applications.
"""

import os
import sys
import time
import random
import subprocess
from typing import List, Tuple, Dict

ADB_BIN = "/opt/homebrew/bin/adb" if os.path.exists("/opt/homebrew/bin/adb") else "adb"

# =============================================================================
# Curated Financial & Transactional SMS Catalog (Indian Lending Context)
# =============================================================================

LENDING_SMS_EVENTS: List[Dict] = [
    # --- Month -2 (60 days ago) ---
    {
        "days_ago": 60,
        "sender": "VK-HDFCBK",
        "body": "Dear Customer, INR 78,500.00 credited to your A/c XX4821 on 01-Aug-26 towards Salary by TECH CORP INDIA PVT LTD. Avl Bal: INR 1,12,340.00 - HDFC Bank"
    },
    {
        "days_ago": 56,
        "sender": "AX-BAJAJF",
        "body": "Dear Customer, your EMI of Rs 3,450 for Loan No. B849201 has been successfully debited from A/c XX4821 on 05-Aug-26. Outstanding: Rs 17,250. - Bajaj Finserv"
    },
    {
        "days_ago": 54,
        "sender": "AD-HDFCBK",
        "body": "Thank you for payment of Rs 12,450.00 towards your HDFC Bank Credit Card ending 7014 on 07-Aug-26. Available limit: Rs 1,87,550.00."
    },
    {
        "days_ago": 50,
        "sender": "VK-HDFCBK",
        "body": "Sent Rs. 1,850.00 from HDFC Bank A/c XX4821 to BESCOM Electricity Bill on 11-Aug-26. UPI Ref 622410948192. Avl Bal: INR 94,590.00."
    },

    # --- Month -1 (30 days ago) ---
    {
        "days_ago": 30,
        "sender": "VK-HDFCBK",
        "body": "Dear Customer, INR 78,500.00 credited to your A/c XX4821 on 01-Sep-26 towards Salary by TECH CORP INDIA PVT LTD. Avl Bal: INR 1,28,400.00 - HDFC Bank"
    },
    {
        "days_ago": 26,
        "sender": "AX-BAJAJF",
        "body": "Dear Customer, your EMI of Rs 3,450 for Loan No. B849201 has been successfully debited from A/c XX4821 on 05-Sep-26. Outstanding: Rs 13,800. - Bajaj Finserv"
    },
    {
        "days_ago": 23,
        "sender": "AD-HDFCBK",
        "body": "Thank you for payment of Rs 14,800.00 towards your HDFC Bank Credit Card ending 7014 on 08-Sep-26. Available limit: Rs 1,85,200.00."
    },
    {
        "days_ago": 20,
        "sender": "VK-HDFCBK",
        "body": "Sent Rs. 1,420.00 from HDFC Bank A/c XX4821 to ACT Fibernet on 11-Sep-26. UPI Ref 625510294811. Avl Bal: INR 1,08,730.00."
    },
    {
        "days_ago": 16,
        "sender": "VK-HDFCBK",
        "body": "Sent Rs. 420.00 from HDFC Bank A/c XX4821 to Zomato via UPI on 15-Sep-26. Avl Bal: INR 1,08,310.00."
    },

    # --- Current Month (Recent 14 days) ---
    {
        "days_ago": 9,
        "sender": "VK-HDFCBK",
        "body": "Dear Customer, INR 78,500.00 credited to your A/c XX4821 on 01-Oct-26 towards Salary by TECH CORP INDIA PVT LTD. Avl Bal: INR 1,42,100.00 - HDFC Bank"
    },
    {
        "days_ago": 7,
        "sender": "BZ-JIOINF",
        "body": "Recharge of Rs 749 successful for Jio Number 9315294420 on 03-Oct-26. Benefits: 2GB/day + Unlimited Calls for 84 days."
    },
    {
        "days_ago": 5,
        "sender": "AX-BAJAJF",
        "body": "Dear Customer, your EMI of Rs 3,450 for Loan No. B849201 has been successfully debited from A/c XX4821 on 05-Oct-26. Outstanding: Rs 10,350. - Bajaj Finserv"
    },
    {
        "days_ago": 4,
        "sender": "AD-HDFCBK",
        "body": "Thank you for payment of Rs 16,200.00 towards your HDFC Bank Credit Card ending 7014 on 06-Oct-26. Available limit: Rs 1,83,800.00."
    },
    {
        "days_ago": 3,
        "sender": "VK-HDFCBK",
        "body": "Sent Rs. 1,940.00 from HDFC Bank A/c XX4821 to BESCOM Electricity Bill on 07-Oct-26. UPI Ref 628190184712. Avl Bal: INR 1,20,510.00."
    },
    {
        "days_ago": 2,
        "sender": "VK-HDFCBK",
        "body": "Sent Rs. 580.00 from HDFC Bank A/c XX4821 to Swiggy via UPI on 08-Oct-26. Avl Bal: INR 1,19,930.00."
    },
    {
        "days_ago": 1,
        "sender": "VK-HDFCBK",
        "body": "Sent Rs. 2,150.00 from HDFC Bank A/c XX4821 to Indian Oil Petrol via UPI on 09-Oct-26. Avl Bal: INR 1,17,780.00."
    },
    {
        "days_ago": 0,
        "sender": "AX-HDFCBK",
        "body": "481920 is OTP for transaction of Rs 1,499.00 on your HDFC Bank Card ending 7014 at Amazon. Valid for 10 mins. Do not share with anyone."
    }
]

# Settings sub-activities simulating authentic device management
SETTINGS_ACTIVITIES = [
    ("Network & Wi-Fi", "com.android.settings/.Settings$NetworkProviderSettingsActivity"),
    ("Battery Usage", "com.android.settings/.Settings$PowerUsageSummaryActivity"),
    ("Display & Brightness", "com.android.settings/.Settings$DisplaySettingsActivity"),
    ("Sound & Vibration", "com.android.settings/.Settings$SoundSettingsActivity"),
    ("Storage Details", "com.android.settings/.Settings$StorageDashboardActivity"),
    ("About Phone", "com.android.settings/.Settings$MyDeviceInfoActivity"),
]

def run_adb(cmd: List[str], check: bool = False) -> subprocess.CompletedProcess:
    full_cmd = [ADB_BIN] + cmd
    return subprocess.run(full_cmd, capture_output=True, text=True, check=check)

def set_device_time(epoch_ms: int):
    run_adb(["shell", "cmd", "alarm", "set-time", str(epoch_ms)], check=True)

def simulate_settings_session(dwell_sec: float = 2.0):
    """
    Launches a random Settings sub-activity, simulates touch interactions,
    and returns to ensure UsageStatsManager logs valid foreground events.
    """
    name, activity = random.choice(SETTINGS_ACTIVITIES)
    run_adb(["shell", "am", "start", "-n", activity], check=False)
    time.sleep(dwell_sec / 2.0)

    # Inward touch gesture to register USER_INTERACTION
    run_adb(["shell", "input", "tap", "500", "1200"], check=False)
    time.sleep(dwell_sec / 2.0)

    # Return to home
    run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"], check=False)
    time.sleep(0.3)

def seed_lending_profile(max_days_ago: int = 60):
    print("==================================================================")
    print(" 🚀 Samsung Galaxy S24 Ultra — Lending History Seeder")
    print("==================================================================")

    # Verify device status
    res = run_adb(["get-state"])
    if res.stdout.strip() != "device":
        print(f"[-] Emulator is not connected. ADB state: {res.stdout.strip()}")
        sys.exit(1)

    real_time_ms = int(time.time() * 1000)
    print(f"[+] Current Host Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(real_time_ms / 1000))}")

    # Filter events within timeframe
    events = [e for e in LENDING_SMS_EVENTS if e["days_ago"] <= max_days_ago]
    # Sort chronologically (oldest first)
    events.sort(key=lambda x: x["days_ago"], reverse=True)

    print(f"[+] Total Financial Events to Seed: {len(events)}")
    print("[+] Seeding multi-day Telephony Provider & Settings history...")

    try:
        # Group events by day to interleave Settings interactions
        days_seen = set()
        for idx, ev in enumerate(events, 1):
            days_ago = ev["days_ago"]
            sender = ev["sender"]
            body = ev["body"]

            # Compute historical epoch ms (staggered around 10:00 AM to 6:00 PM)
            hour_offset_sec = random.randint(10 * 3600, 18 * 3600)
            event_epoch_ms = real_time_ms - (days_ago * 86400 * 1000) + (hour_offset_sec * 1000)

            # 1. Rewind system clock to the historical event timestamp
            set_device_time(event_epoch_ms)

            # 2. Inject authentic incoming carrier SMS via emulator modem RIL
            # This triggers com.android.providers.telephony, updates SQLite, and creates notifications
            emu_res = run_adb(["emu", "sms", "send", sender, body])
            print(f"  [{idx:02d}/{len(events):02d}] {days_ago:2d}d ago | SMS from {sender:10s} -> {emu_res.stdout.strip()}")
            time.sleep(0.4)

            # 3. Simulate realistic Settings interaction on distinct days
            if days_ago not in days_seen:
                days_seen.add(days_ago)
                # Random 1-2 settings checks on this historical day
                for _ in range(random.randint(1, 2)):
                    simulate_settings_session(dwell_sec=1.5)

        # Additional Settings usage for recent 3 days (simulates active device management)
        print("[+] Reinforcing recent Settings foreground usage curves...")
        for r_days in [3, 2, 1, 0]:
            r_epoch_ms = real_time_ms - (r_days * 86400 * 1000) + (random.randint(9 * 3600, 21 * 3600) * 1000)
            set_device_time(r_epoch_ms)
            for _ in range(2):
                simulate_settings_session(dwell_sec=2.0)

        # Commit batterystats and usagestats caches to disk
        run_adb(["shell", "dumpsys", "batterystats", "--write"], check=False)

    finally:
        # CRITICAL: Always restore real host time
        print("[+] Restoring device system clock to current real time...")
        set_device_time(real_time_ms)
        date_res = run_adb(["shell", "date"]).stdout.strip()
        print(f"[+] Device Clock Restored: {date_res}")

    print("\n✅ Lending app history seeding complete!")

def verify_seeding():
    print("\n🔍 --- AUDIT / VERIFICATION OF SEEDED LENDING PROFILES ---")
    
    # 1. Query Telephony SMS rows
    print("\n📨 Telephony Provider (content://sms/inbox):")
    res = run_adb([
        "shell", "content", "query",
        "--uri", "content://sms",
        "--projection", "_id:address:date:body"
    ])
    lines = [l for l in res.stdout.splitlines() if l.startswith("Row:")]
    print(f"  • Total Seeded SMS Rows: {len(lines)}")
    for line in lines[:8]:
        print(f"    {line}")
    if len(lines) > 8:
        print(f"    ... and {len(lines) - 8} more transactions.")

    # 2. Inspect Settings UsageStats
    print("\n⚙️ UsageStatsManager (com.android.settings):")
    us_res = run_adb(["shell", "dumpsys", "usagestats", "--daily"])
    settings_lines = []
    capture = False
    for line in us_res.stdout.splitlines():
        if "package=com.android.settings " in line or "package=com.android.settings\n" in line:
            capture = True
        if capture:
            settings_lines.append(line.strip())
            if len(settings_lines) >= 6:
                break
    for l in settings_lines:
        print(f"    {l}")

def clean_sms():
    print("[*] Clearing synthetic SMS messages...")
    run_adb(["shell", "content", "delete", "--uri", "content://sms"], check=False)
    print("[+] Telephony SMS database cleared.")

def set_stealth_mode(enabled: bool = True):
    """
    Disables/Enables Developer Options & USB Debugging flags in Settings.Global.
    Many lending apps check these flags to detect root/testing environments.
    """
    val = "0" if enabled else "1"
    run_adb(["shell", "settings", "put", "global", "development_settings_enabled", val], check=False)
    run_adb(["shell", "settings", "put", "global", "adb_enabled", val], check=False)
    print(f"[+] Stealth Mode {'ENABLED' if enabled else 'DISABLED'}: development_settings_enabled={val}, adb_enabled={val}")

def main():
    if len(sys.argv) < 2:
        print("Usage: sec_lending_seeder.py [--seed|--verify|--clean|--stealth-on|--stealth-off]")
        return

    cmd = sys.argv[1].lower()
    if cmd in ["--seed", "seed"]:
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        seed_lending_profile(max_days_ago=days)
        verify_seeding()
    elif cmd in ["--verify", "verify"]:
        verify_seeding()
    elif cmd in ["--clean", "clean"]:
        clean_sms()
    elif cmd == "--stealth-on":
        set_stealth_mode(True)
    elif cmd == "--stealth-off":
        set_stealth_mode(False)
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
