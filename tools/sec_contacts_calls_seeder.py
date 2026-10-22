#!/usr/bin/env python3
"""
Samsung Electronics Co., Ltd. — Galaxy S24 Ultra Contacts & Call Logs Precision Seeder
Dynamically links contacts using real SQLite row IDs and populates 30 days of call logs.
"""

import os
import sys
import re
import time
import random
import subprocess
from datetime import datetime, timedelta

ADB_BIN = "/opt/homebrew/bin/adb" if os.path.exists("/opt/homebrew/bin/adb") else "adb"

def run_adb(cmd: str) -> str:
    res = subprocess.run(f"{ADB_BIN} {cmd}", shell=True, capture_output=True, text=True)
    return res.stdout.strip()

CONTACTS_CATALOG = [
    # Family
    {"name": "Mom", "phone": "+919811234567", "type": 2, "starred": 1, "email": "renu.sharma@gmail.com"},
    {"name": "Papa", "phone": "+919811345678", "type": 2, "starred": 1, "email": "rk.sharma@gmail.com"},
    {"name": "Rohit Bhai", "phone": "+919871122334", "type": 2, "starred": 1, "email": "rohit.sharma88@gmail.com"},
    {"name": "Priya Didi", "phone": "+919810455667", "type": 2, "starred": 0, "email": "priya.verma@yahoo.com"},
    {"name": "Home", "phone": "+911126894420", "type": 1, "starred": 0, "email": ""},

    # Close Friends
    {"name": "Rahul Verma", "phone": "+919818877665", "type": 2, "starred": 1, "email": "rahul.v92@gmail.com"},
    {"name": "Amit Sharma", "phone": "+919910023451", "type": 2, "starred": 0, "email": "amit.sharma@outlook.com"},
    {"name": "Neha Kapoor", "phone": "+919899134120", "type": 2, "starred": 0, "email": "neha.k@gmail.com"},
    {"name": "Vikram Malhotra", "phone": "+919711298451", "type": 2, "starred": 0, "email": "vikram.m@techcorp.in"},
    {"name": "Pooja Singhania", "phone": "+919811567123", "type": 2, "starred": 0, "email": "pooja.s@gmail.com"},
    {"name": "Ananya Sen", "phone": "+919830122345", "type": 2, "starred": 0, "email": "ananya.sen@gmail.com"},
    {"name": "Deepak Mehra", "phone": "+919818054321", "type": 2, "starred": 0, "email": "deepak.mehra@gmail.com"},
    {"name": "Saurabh Joshi", "phone": "+919717788990", "type": 2, "starred": 0, "email": "saurabh.j@gmail.com"},
    {"name": "Kunal Batra", "phone": "+919958812345", "type": 2, "starred": 0, "email": "kunal.b@gmail.com"},
    {"name": "Tanya Sethi", "phone": "+919810144556", "type": 2, "starred": 0, "email": "tanya.sethi@gmail.com"},

    # Professional & Work
    {"name": "Vivek HDFC RM", "phone": "+919920184821", "type": 3, "starred": 0, "email": "vivek.n@hdfcbank.com"},
    {"name": "Dr. Rajesh Kapoor", "phone": "+919811099887", "type": 3, "starred": 0, "email": "dr.kapoor.clinic@gmail.com"},
    {"name": "Arvind Manager", "phone": "+919810011223", "type": 3, "starred": 1, "email": "arvind.kumar@techcorp.in"},
    {"name": "Tech Corp Office", "phone": "+911244567890", "type": 3, "starred": 0, "email": "reception@techcorp.in"},
    {"name": "CA Gupta", "phone": "+919811477889", "type": 3, "starred": 0, "email": "ca.guptaassociates@gmail.com"},

    # Local Services
    {"name": "Swiggy Delivery", "phone": "+919876501234", "type": 7, "starred": 0, "email": ""},
    {"name": "Zomato Partner", "phone": "+919876509876", "type": 7, "starred": 0, "email": ""},
    {"name": "Urban Company Service", "phone": "+919911288441", "type": 7, "starred": 0, "email": ""},
    {"name": "Ramesh Car Wash", "phone": "+919818233445", "type": 7, "starred": 0, "email": ""},
    {"name": "Bisleri Water Supply", "phone": "+919810911224", "type": 7, "starred": 0, "email": ""}
]

call_templates = [
    # (days_ago, hour, minute, contact_index, call_type, duration_seconds)
    (0, 17, 30, 0, 1, 312),   # Mom, Incoming today 5:30 PM (5 mins)
    (0, 14, 15, 5, 2, 145),   # Rahul Verma, Outgoing today 2:15 PM (2 mins)
    (0, 11, 40, 17, 1, 240),  # Arvind Manager, Incoming today 11:40 AM (4 mins)
    (0, 9, 20, 20, 1, 45),    # Swiggy Delivery, Incoming today 9:20 AM
    (1, 21, 10, 1, 2, 420),   # Papa, Outgoing yesterday 9:10 PM (7 mins)
    (1, 19, 45, 0, 1, 180),   # Mom, Incoming yesterday 7:45 PM
    (1, 16, 20, 6, 2, 95),    # Amit Sharma, Outgoing yesterday 4:20 PM
    (1, 13, 5, 15, 1, 210),   # Vivek HDFC RM, Incoming yesterday 1:05 PM
    (1, 10, 15, 2, 3, 0),     # Rohit Bhai, Missed yesterday 10:15 AM
    (2, 20, 30, 2, 2, 510),   # Rohit Bhai, Outgoing 2 days ago (8.5 mins)
    (2, 18, 0, 5, 1, 330),    # Rahul Verma, Incoming 2 days ago
    (2, 15, 45, 17, 2, 185),  # Arvind Manager, Outgoing 2 days ago
    (2, 12, 10, 21, 1, 38),   # Zomato Partner, Incoming 2 days ago
    (3, 21, 0, 0, 2, 260),    # Mom, Outgoing 3 days ago
    (3, 17, 20, 7, 1, 140),   # Neha Kapoor, Incoming 3 days ago
    (3, 14, 30, 8, 2, 85),    # Vikram Malhotra, Outgoing 3 days ago
    (3, 11, 15, 16, 1, 190),  # Dr. Rajesh Kapoor, Incoming 3 days ago
    (4, 20, 15, 1, 1, 340),   # Papa, Incoming 4 days ago
    (4, 16, 50, 5, 2, 220),   # Rahul Verma, Outgoing 4 days ago
    (4, 13, 40, 22, 1, 55),   # Urban Company, Incoming 4 days ago
    (4, 10, 0, 17, 1, 310),  # Arvind Manager, Incoming 4 days ago
    (5, 22, 10, 0, 1, 195),   # Mom, Incoming 5 days ago
    (5, 18, 30, 2, 2, 410),   # Rohit Bhai, Outgoing 5 days ago
    (5, 15, 5, 10, 3, 0),     # Ananya Sen, Missed 5 days ago
    (5, 15, 15, 10, 2, 280),  # Ananya Sen, Outgoing callback 5 days ago
    (6, 19, 40, 6, 1, 115),   # Amit Sharma, Incoming 6 days ago
    (6, 14, 20, 18, 2, 60),   # Tech Corp Office, Outgoing 6 days ago
    (7, 21, 15, 1, 2, 380),   # Papa, Outgoing 7 days ago
    (7, 17, 50, 0, 1, 290),   # Mom, Incoming 7 days ago
    (8, 20, 0, 5, 1, 450),    # Rahul Verma, Incoming 8 days ago
    (8, 12, 30, 19, 2, 180),  # CA Gupta, Outgoing 8 days ago
    (9, 21, 30, 0, 2, 210),   # Mom, Outgoing 9 days ago
    (9, 16, 15, 15, 1, 240),  # Vivek HDFC RM, Incoming 9 days ago
    (10, 19, 10, 2, 1, 360),  # Rohit Bhai, Incoming 10 days ago
    (11, 20, 45, 1, 1, 300),  # Papa, Incoming 11 days ago
    (12, 18, 20, 7, 2, 160),  # Neha Kapoor, Outgoing 12 days ago
    (13, 21, 0, 0, 1, 320),   # Mom, Incoming 13 days ago
    (14, 17, 15, 5, 2, 190),  # Rahul Verma, Outgoing 14 days ago
    (15, 20, 30, 2, 2, 480),  # Rohit Bhai, Outgoing 15 days ago
    (16, 19, 0, 1, 2, 250),   # Papa, Outgoing 16 days ago
    (17, 21, 10, 0, 1, 210),  # Mom, Incoming 17 days ago
    (18, 16, 40, 8, 1, 130),  # Vikram Malhotra, Incoming 18 days ago
    (19, 20, 15, 5, 2, 270),  # Rahul Verma, Outgoing 19 days ago
    (20, 18, 50, 2, 1, 350),  # Rohit Bhai, Incoming 20 days ago
    (22, 21, 20, 0, 2, 310),  # Mom, Outgoing 22 days ago
    (24, 20, 5, 1, 1, 290),   # Papa, Incoming 24 days ago
    (26, 19, 30, 5, 1, 340),  # Rahul Verma, Incoming 26 days ago
    (28, 21, 0, 0, 1, 240),   # Mom, Incoming 28 days ago
    (30, 20, 15, 2, 2, 420),  # Rohit Bhai, Outgoing 30 days ago
]

def seed_contacts():
    print("[+] Hard purging old raw contacts...")
    run_adb('shell "content delete --uri \'content://com.android.contacts/raw_contacts?caller_is_syncadapter=true\'"')

    print(f"[+] Seeding {len(CONTACTS_CATALOG)} contacts with dynamic ID resolution...")
    for c in CONTACTS_CATALOG:
        # 1. Insert raw contact
        run_adb(
            f"shell content insert --uri content://com.android.contacts/raw_contacts "
            f"--bind account_type:s:com.google --bind account_name:s:primary --bind starred:i:{c['starred']}"
        )

        # 2. Query newly generated _id
        q = run_adb("shell \"content query --uri content://com.android.contacts/raw_contacts --projection _id --sort '_id DESC'\"")
        m = re.search(r"_id=(\d+)", q)
        if not m:
            continue
        raw_id = m.group(1)

        # 3. Insert Name
        run_adb(
            f"shell \"content insert --uri content://com.android.contacts/data "
            f"--bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/name "
            f"--bind data1:s:'{c['name']}' --bind data2:s:'{c['name']}'\""
        )

        # 4. Insert Phone
        run_adb(
            f"shell \"content insert --uri content://com.android.contacts/data "
            f"--bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/phone_v2 "
            f"--bind data1:s:'{c['phone']}' --bind data2:i:{c['type']}\""
        )

        # 5. Insert Email (if any)
        if c['email']:
            run_adb(
                f"shell \"content insert --uri content://com.android.contacts/data "
                f"--bind raw_contact_id:i:{raw_id} --bind mimetype:s:vnd.android.cursor.item/email_v2 "
                f"--bind data1:s:'{c['email']}' --bind data2:i:1\""
            )

    print(f"[✓] Successfully inserted all {len(CONTACTS_CATALOG)} contacts into phonebook.")

def seed_call_logs():
    print(f"[+] Seeding {len(call_templates)} call logs spanning past 30 days...")
    run_adb('shell "content delete --uri content://call_log/calls"')

    now_epoch = int(time.time())
    for days_ago, hour, minute, c_idx, call_type, dur in call_templates:
        contact = CONTACTS_CATALOG[c_idx]
        call_dt = datetime.fromtimestamp(now_epoch) - timedelta(days=days_ago)
        call_dt = call_dt.replace(hour=hour, minute=minute, second=random.randint(5, 55))
        timestamp_ms = int(call_dt.timestamp() * 1000)

        run_adb(
            f"shell \"content insert --uri content://call_log/calls "
            f"--bind number:s:'{contact['phone']}' "
            f"--bind date:l:{timestamp_ms} "
            f"--bind duration:i:{dur} "
            f"--bind type:i:{call_type} "
            f"--bind new:i:0 "
            f"--bind name:s:'{contact['name']}'\""
        )

    print(f"[✓] Successfully inserted {len(call_templates)} call log entries.")

if __name__ == "__main__":
    seed_contacts()
    seed_call_logs()
    print("[★] Galaxy S24 Ultra Indian Contacts & Call Logs 100% Restored!")
