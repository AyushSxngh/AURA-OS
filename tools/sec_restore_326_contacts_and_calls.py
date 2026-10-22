#!/usr/bin/env python3
"""
sec_restore_326_contacts_and_calls.py
Bulk restore 326 authentic Indian contacts and 31,972 realistic call logs
onto Android emulator via high-performance Android runtime BulkDataImporter DEX.
"""

import os
import sys
import re
import csv
import random
import datetime
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = "/Users/ayush/Desktop/AURA_Exported/Download/indian_contacts_326_with_call_counts.csv"
TMP_DIR = "/tmp"
DEX_LOCAL = os.path.join(TMP_DIR, "classes.dex")
CONTACTS_TSV = os.path.join(TMP_DIR, "contacts_326.tsv")
CALLS_TSV = os.path.join(TMP_DIR, "call_logs.tsv")

def extract_10_digits(raw: str) -> str:
    digits = re.sub(r'\D', '', str(raw))
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith('1') and len(digits) == 11:
        digits = digits[1:]
    elif len(digits) > 10:
        digits = digits[-10:]
    return digits

def format_indian_display(digits10: str) -> str:
    return f"+91 {digits10[:5]} {digits10[5:]}"

def format_indian_e164(digits10: str) -> str:
    return f"+91{digits10}"

def generate_data():
    print(f"Reading contacts from {CSV_FILE}...")
    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        contacts = list(csv.DictReader(f))

    print(f"Loaded {len(contacts)} contacts.")
    total_calls = sum(int(c.get("Call Count", 0)) for c in contacts)
    print(f"Total call logs to generate: {total_calls}")

    # 1. Write Contacts TSV
    with open(CONTACTS_TSV, "w", encoding="utf-8") as f:
        for c in contacts:
            name = c["Name"].strip()
            d10 = extract_10_digits(c["Phone"])
            disp = format_indian_display(d10)
            e164 = format_indian_e164(d10)
            f.write(f"{name}\t{disp}\t{e164}\n")
    print(f"Written contacts to {CONTACTS_TSV}")

    # 2. Generate Call Logs
    random.seed(42)
    CLOSE_NAMES = {
        'Mummy ❤️', 'Papa ❤️', 'Bhai 😎', 'Didi ❤️', 'Bestie ❤️',
        'BigBro 💪', 'Chotu 😂', 'College Bestie ❤️'
    }

    # Setup contact copy with mutable counts
    contact_pool = []
    for c in contacts:
        d10 = extract_10_digits(c["Phone"])
        contact_pool.append({
            "name": c["Name"].strip(),
            "phone_disp": format_indian_display(d10),
            "phone_e164": format_indian_e164(d10),
            "count": int(c.get("Call Count", 0))
        })

    # Day 0: Today (2026-10-09)
    # Put realistic calls throughout today before 7:00 PM
    today = datetime.date(2026, 10, 9)
    day_0_calls = []

    def add_today_call(name, hour, minute, second, duration, ctype, is_new=0):
        target = next((cp for cp in contact_pool if cp["name"] == name), None)
        if target and target["count"] > 0:
            target["count"] -= 1
            dt = datetime.datetime.combine(today, datetime.time(hour, minute, second))
            day_0_calls.append({
                "name": target["name"],
                "phone_e164": target["phone_e164"],
                "phone_disp": target["phone_disp"],
                "dt": dt,
                "duration": duration,
                "type": ctype,
                "new": is_new
            })

    add_today_call('Mummy ❤️', 10, 15, 20, 215, 1) # incoming
    add_today_call('Papa ❤️', 11, 42, 10, 95, 2)  # outgoing
    add_today_call('Bhai 😎', 13, 14, 45, 180, 2)  # outgoing
    add_today_call('Bestie ❤️', 15, 30, 0, 480, 1) # incoming
    add_today_call('Chotu 😂', 17, 10, 15, 55, 1)  # incoming
    add_today_call('Didi ❤️', 18, 25, 40, 0, 3, 1)  # missed (new)
    add_today_call('Mummy ❤️', 18, 48, 12, 320, 2) # outgoing

    # Remaining calls across historical days (1029 days ~ 2.8 years)
    NUM_HIST_DAYS = 1029
    hist_total = sum(cp["count"] for cp in contact_pool)
    print(f"Historical calls remaining: {hist_total} across {NUM_HIST_DAYS} days")

    quotas = [max(18, min(46, int(random.gauss(31.06, 5.0)))) for _ in range(NUM_HIST_DAYS)]
    diff = sum(quotas) - hist_total
    while diff != 0:
        idx = random.randint(0, NUM_HIST_DAYS - 1)
        if diff > 0 and quotas[idx] > 20:
            quotas[idx] -= 1
            diff -= 1
        elif diff < 0 and quotas[idx] < 44:
            quotas[idx] += 1
            diff += 1

    calls_by_day = [[] for _ in range(NUM_HIST_DAYS)]
    day_counts = [0] * NUM_HIST_DAYS

    sorted_pool = sorted(contact_pool, key=lambda x: x["count"], reverse=True)

    for cp in sorted_pool:
        cnt = cp["count"]
        name = cp["name"]
        e164 = cp["phone_e164"]
        disp = cp["phone_disp"]
        remaining = cnt
        while remaining > 0:
            if remaining >= NUM_HIST_DAYS:
                for d in range(NUM_HIST_DAYS):
                    calls_by_day[d].append((name, e164, disp))
                    day_counts[d] += 1
                remaining -= NUM_HIST_DAYS
            else:
                candidate_days = list(range(NUM_HIST_DAYS))
                candidate_days.sort(key=lambda d: (day_counts[d] / quotas[d]) + random.random() * 0.18)
                chosen_days = candidate_days[:remaining]
                for d in chosen_days:
                    calls_by_day[d].append((name, e164, disp))
                    day_counts[d] += 1
                remaining = 0

    all_calls = list(day_0_calls)
    base_date = datetime.date(2026, 10, 8) # Day 1 is yesterday

    for d in range(NUM_HIST_DAYS):
        cur_date = base_date - datetime.timedelta(days=d)
        day_contacts = calls_by_day[d]
        random.shuffle(day_contacts)
        K = len(day_contacts)
        if K == 0:
            continue

        start_offset = 8 * 3600 # 8:00 AM
        day_span = int(15.5 * 3600) # up to 11:30 PM (55800s)

        points = sorted(random.sample(range(0, day_span - 300), K))

        for i in range(K):
            name, e164, disp = day_contacts[i]
            start_sec = start_offset + points[i]
            if i < K - 1:
                next_start = start_offset + points[i+1]
                max_dur = min(next_start - start_sec - 30, 2400)
            else:
                max_dur = 2400

            is_close = name in CLOSE_NAMES

            r_type = random.random()
            if r_type < 0.44:
                ctype = 1 # incoming
            elif r_type < 0.86:
                ctype = 2 # outgoing
            elif r_type < 0.97:
                ctype = 3 # missed
            else:
                ctype = 5 # rejected

            if ctype in (3, 5) or max_dur < 10:
                duration = 0
                if max_dur < 10:
                    ctype = 3
            else:
                if is_close:
                    r_dur = random.random()
                    if r_dur < 0.20:
                        dur = random.randint(25, 90)
                    elif r_dur < 0.70:
                        dur = random.randint(120, 600)
                    else:
                        dur = random.randint(600, 2100)
                else:
                    r_dur = random.random()
                    if r_dur < 0.65:
                        dur = random.randint(15, 120)
                    elif r_dur < 0.92:
                        dur = random.randint(120, 360)
                    else:
                        dur = random.randint(360, 900)
                duration = max(5, min(dur, max_dur))

            call_dt = datetime.datetime.combine(cur_date, datetime.time()) + datetime.timedelta(seconds=start_sec)
            all_calls.append({
                "name": name,
                "phone_e164": e164,
                "phone_disp": disp,
                "dt": call_dt,
                "duration": duration,
                "type": ctype,
                "new": 0
            })

    # Sort descending by date
    all_calls.sort(key=lambda x: x["dt"], reverse=True)
    print(f"Total call records generated: {len(all_calls)}")

    # Write to TSV: number \t name \t date (epoch ms) \t duration \t type \t isNew \t formatted_number
    with open(CALLS_TSV, "w", encoding="utf-8") as f:
        for c in all_calls:
            epoch_ms = int(c["dt"].timestamp() * 1000)
            f.write(f"{c['phone_e164']}\t{c['name']}\t{epoch_ms}\t{c['duration']}\t{c['type']}\t{c['new']}\t{c['phone_disp']}\n")

    print(f"Written call logs to {CALLS_TSV} (size: {os.path.getsize(CALLS_TSV)} bytes)")

def compile_dex():
    java_src = "/tmp/BulkDataImporter.java"
    print("Compiling BulkDataImporter.java...")
    subprocess.check_call([
        "/opt/homebrew/opt/openjdk@17/bin/javac",
        "-cp", "/Users/ayush/Library/Android/sdk/platforms/android-34/android.jar",
        java_src
    ])
    subprocess.check_call([
        "/Users/ayush/Library/Android/sdk/build-tools/34.0.0/d8",
        "--output", TMP_DIR,
        "/tmp/BulkDataImporter.class"
    ])
    print(f"Compiled DEX created at {DEX_LOCAL}")

def run_import():
    adb = ["adb"]
    print("Purging existing contacts...")
    subprocess.check_call(adb + ["shell", "content delete --uri 'content://com.android.contacts/raw_contacts?caller_is_syncadapter=true'"])
    print("Purging existing call logs...")
    subprocess.check_call(adb + ["shell", "content delete --uri content://call_log/calls"])

    print("Pushing DEX and TSVs to device...")
    subprocess.check_call(adb + ["push", DEX_LOCAL, "/data/local/tmp/bulk_importer.dex"])
    subprocess.check_call(adb + ["push", CONTACTS_TSV, "/data/local/tmp/contacts_326.tsv"])
    subprocess.check_call(adb + ["push", CALLS_TSV, "/data/local/tmp/call_logs.tsv"])

    print("Importing 326 contacts...")
    subprocess.check_call(adb + [
        "shell", "CLASSPATH=/data/local/tmp/bulk_importer.dex",
        "app_process", "/data/local/tmp", "BulkDataImporter", "contacts", "/data/local/tmp/contacts_326.tsv"
    ])

    print("Importing 31,972 call logs...")
    subprocess.check_call(adb + [
        "shell", "CLASSPATH=/data/local/tmp/bulk_importer.dex",
        "app_process", "/data/local/tmp", "BulkDataImporter", "calls", "/data/local/tmp/call_logs.tsv"
    ])

    print("Cleaning up on-device temp files...")
    subprocess.check_call(adb + ["shell", "rm -f /data/local/tmp/bulk_importer.dex /data/local/tmp/contacts_326.tsv /data/local/tmp/call_logs.tsv"])

    # Verification
    out_c = subprocess.check_output(adb + ["shell", "content query --uri content://com.android.contacts/contacts"]).decode("utf-8", errors="ignore")
    out_call = subprocess.check_output(adb + ["shell", "content query --uri content://call_log/calls"]).decode("utf-8", errors="ignore")

    contact_count = len([l for l in out_c.splitlines() if l.startswith("Row:")])
    call_count = len([l for l in out_call.splitlines() if l.startswith("Row:")])

    print(f"VERIFICATION RESULTS:")
    print(f"  Contacts in Android: {contact_count}")
    print(f"  Call logs in Android: {call_count}")

def main():
    compile_dex()
    generate_data()
    run_import()

if __name__ == "__main__":
    main()
