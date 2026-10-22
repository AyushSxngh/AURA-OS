#!/usr/bin/env python3
"""
AURA OS ARM64 — Massive Financial & Transactional SMS Profile Seeder
Generates and injects 600–800 authentic Indian financial & transactional SMS records
spanning 180 days across major Indian banks, UPI, EMIs, utilities, and lifestyle merchants.

Target device: emulator-5554 (Zero-su compliant via Android Emulator modem RIL)
"""

import os
import sys
import time
import random
import datetime
import subprocess
from typing import List, Dict, Tuple

ADB_BIN = "/opt/homebrew/bin/adb" if os.path.exists("/opt/homebrew/bin/adb") else "adb"
DEVICE_SERIAL = "emulator-5554"

def run_adb(args: List[str], check: bool = False) -> subprocess.CompletedProcess:
    cmd = [ADB_BIN, "-s", DEVICE_SERIAL] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

def set_device_time(epoch_ms: int):
    run_adb(["shell", "cmd", "alarm", "set-time", str(epoch_ms)], check=True)

# =============================================================================
# Transaction & Merchant Templates
# =============================================================================

UPI_MERCHANTS = [
    ("Swiggy", ["AD-SWIGGY", "VK-HDFCBK"], [180, 240, 320, 450, 580, 720]),
    ("Zomato", ["VM-ZOMATO", "VK-HDFCBK"], [195, 275, 380, 490, 640]),
    ("Blinkit", ["VM-BLNKIT", "VK-HDFCBK"], [340, 520, 680, 890, 1150]),
    ("Zepto", ["VK-ZEPTO", "VK-HDFCBK"], [210, 390, 480, 620, 850]),
    ("Uber", ["AD-UBERIN", "VK-HDFCBK"], [120, 185, 240, 310, 420]),
    ("Ola Cabs", ["VM-OLACAB", "VK-HDFCBK"], [110, 160, 230, 290]),
    ("Indian Oil Petrol", ["VK-HDFCBK"], [1500, 1800, 2000, 2200]),
    ("BPCL Fuel", ["VK-HDFCBK"], [1600, 1900, 2100]),
    ("Shell Fuel", ["VK-HDFCBK"], [1800, 2200, 2500]),
    ("Chai Point", ["VK-HDFCBK"], [80, 120, 160]),
    ("Third Wave Coffee", ["VK-HDFCBK"], [240, 290, 380]),
    ("Starbucks", ["VK-HDFCBK"], [350, 420, 560]),
    ("DMart", ["VK-HDFCBK"], [1850, 2450, 3100, 4200]),
    ("Apollo Pharmacy", ["VK-HDFCBK"], [180, 320, 450, 780]),
    ("Medplus", ["VK-HDFCBK"], [210, 390, 640]),
    ("BookMyShow", ["VK-HDFCBK"], [480, 650, 820]),
    ("PVR Cinemas", ["VK-HDFCBK"], [600, 850, 1200]),
]

PEER_NAMES = [
    "Rahul Sharma", "Amit Verma", "Sneha Patel", "Vikram Singh",
    "Priya Nair", "Rohan Joshi", "Ankit Gupta", "Neha Iyer"
]

CARD_MERCHANTS = [
    ("AMAZON RETAIL", [599, 899, 1299, 2499, 4999]),
    ("FLIPKART INTERNET", [649, 1199, 1899, 3299]),
    ("MYNTRA DESIGNS", [1499, 2199, 3499]),
    ("ZOMATO ONLINE", [450, 680, 920]),
    ("SWIGGY BANGALORE", [380, 540, 790]),
    ("DECATHLON SPORTS", [899, 1499, 2899]),
    ("TATA CLiQ", [1200, 2100, 3500]),
]

def generate_financial_profile(total_days: int = 180) -> List[Tuple[int, str, str]]:
    """
    Generates a coherent chronological ledger of SMS messages over the specified days.
    Returns: List of (timestamp_epoch_ms, sender, body) sorted chronologically.
    """
    now = int(time.time() * 1000)
    messages: List[Tuple[int, str, str]] = []
    
    # Running account state
    account_num = "XX4821"
    card_last4 = "7014"
    jio_num = "9315294420"
    loan_num = "B849201"
    
    balance = 82450.00
    card_limit = 200000.00
    card_outstanding = 14200.00
    loan_outstanding = 24150.00
    
    # Base datetime corresponding to total_days ago
    base_dt = datetime.datetime.now() - datetime.timedelta(days=total_days)
    
    print(f"[*] Simulating financial timeline from {base_dt.strftime('%d-%b-%Y')} to {datetime.datetime.now().strftime('%d-%b-%Y')}...")

    for day_idx in range(total_days + 1):
        cur_dt = base_dt + datetime.timedelta(days=day_idx)
        d_str = cur_dt.strftime("%d-%b-%y")
        day_m = cur_dt.day
        month_str = cur_dt.strftime("%b-%y")
        
        # Day base epoch
        day_epoch_s = int(cur_dt.timestamp())
        
        def make_ts(hour: int, minute: int) -> int:
            return (day_epoch_s - (cur_dt.hour * 3600 + cur_dt.minute * 60 + cur_dt.second) + (hour * 3600 + minute * 60 + random.randint(0, 59))) * 1000

        # -------------------------------------------------------------
        # 1. Monthly Recurring Events
        # -------------------------------------------------------------
        # 1st of Month: Salary Credit
        if day_m == 1:
            salary = random.choice([82450.00, 84200.00, 84200.00, 85600.00])
            balance += salary
            ts = make_ts(10, random.randint(15, 45))
            body = f"Dear Customer, INR {salary:,.2f} credited to your A/c {account_num} on {d_str} towards Salary by INFOSYS BPM LTD. Avl Bal: INR {balance:,.2f} - HDFC Bank"
            messages.append((ts, "VK-HDFCBK", body))

        # 5th of Month: Bajaj Finserv Loan EMI
        if day_m == 5:
            emi = 3450.00
            balance -= emi
            loan_outstanding = max(0.0, loan_outstanding - emi)
            ts = make_ts(11, random.randint(10, 30))
            body = f"Dear Customer, your EMI of Rs {emi:,.2f} for Loan No. {loan_num} has been successfully debited from A/c {account_num} on {d_str}. Outstanding: Rs {loan_outstanding:,.2f}. - Bajaj Finserv"
            messages.append((ts, "AX-BAJAJF", body))

        # 7th of Month: Credit Card Bill Payment
        if day_m == 7:
            cc_pay = round(random.uniform(11500.0, 16800.0), 2)
            balance -= cc_pay
            card_outstanding = max(0.0, card_outstanding - cc_pay)
            avail_lim = card_limit - card_outstanding
            ts = make_ts(12, random.randint(5, 50))
            body = f"Thank you for payment of Rs {cc_pay:,.2f} towards your HDFC Bank Credit Card ending {card_last4} on {d_str}. Available limit: Rs {avail_lim:,.2f}."
            messages.append((ts, "AD-HDFCBK", body))
            
            # CRED receipt
            ts_cred = ts + 180000
            cred_body = f"Payment of Rs {cc_pay:,.2f} received for HDFC Bank Credit Card ending {card_last4}. Your cashback of Rs 25 has been credited to CRED balance."
            messages.append((ts_cred, "BW-CRED", cred_body))

        # 10th of Month: SIP Mutual Fund Investment (Parag Parikh Flexi Cap)
        if day_m == 10:
            sip_amt = 5000.00
            balance -= sip_amt
            ts = make_ts(9, random.randint(30, 55))
            body = f"Dear Investor, SIP of Rs {sip_amt:,.2f} for Parag Parikh Flexi Cap Fund successfully debited via NACH from A/c {account_num} on {d_str}. - Zerodha Broking"
            messages.append((ts, "AD-ZERODH", body))

        # 11th of Month: BESCOM Electricity Bill
        if day_m == 11:
            elec_amt = round(random.uniform(1650.0, 2350.0), 2)
            balance -= elec_amt
            ref_num = f"6{random.randint(10000000000, 99999999999)}"
            ts = make_ts(14, random.randint(10, 40))
            body = f"Sent Rs. {elec_amt:,.2f} from HDFC Bank A/c {account_num} to BESCOM Electricity Bill on {d_str}. UPI Ref {ref_num}. Avl Bal: INR {balance:,.2f}."
            messages.append((ts, "VK-HDFCBK", body))

        # 12th of Month: ACT Fibernet Broadband Bill
        if day_m == 12:
            net_amt = 1179.00
            balance -= net_amt
            ref_num = f"6{random.randint(10000000000, 99999999999)}"
            ts = make_ts(15, random.randint(20, 50))
            body = f"Sent Rs. {net_amt:,.2f} from HDFC Bank A/c {account_num} to ACT Fibernet on {d_str}. UPI Ref {ref_num}. Avl Bal: INR {balance:,.2f}."
            messages.append((ts, "VK-HDFCBK", body))

        # 20th of Month: Credit Card Statement Generated
        if day_m == 20:
            new_cc_bill = round(random.uniform(12000.0, 17500.0), 2)
            card_outstanding = new_cc_bill
            due_date = (cur_dt + datetime.timedelta(days=18)).strftime("%d-%b-%y")
            ts = make_ts(16, random.randint(10, 30))
            body = f"Your HDFC Bank Credit Card ending {card_last4} statement for {month_str} is generated. Total Amt Due: Rs {new_cc_bill:,.2f}, Min Due: Rs {new_cc_bill*0.05:,.2f}. Due Date: {due_date}."
            messages.append((ts, "AD-HDFCBK", body))

        # Every 84 days: Jio Prepaid Plan Recharge
        if day_idx % 84 == 15:
            recharge_amt = 749
            balance -= recharge_amt
            ts = make_ts(11, random.randint(20, 40))
            body = f"Recharge of Rs {recharge_amt} successful for Jio Number {jio_num} on {d_str}. Benefits: 2GB/day + Unlimited Calls for 84 days."
            messages.append((ts, "BZ-JIOINF", body))

        # Quarterly EPFO Balance Alert
        if day_m == 28 and cur_dt.month in [4, 7, 10]:
            pf_bal = 320000 + (day_idx * 150)
            ts = make_ts(17, random.randint(10, 50))
            body = f"EPF balance in Passbook for member ID BGBLR0028190000 is Rs {pf_bal:,.2f}. Contributions up to {cur_dt.strftime('%b-%y')} credited. - EPFO"
            messages.append((ts, "VK-EPFOHO", body))

        # -------------------------------------------------------------
        # 2. Daily Merchant UPI Transactions (1 to 3 per day)
        # -------------------------------------------------------------
        num_upi = random.choices([1, 2, 3], weights=[0.25, 0.55, 0.20])[0]
        for _ in range(num_upi):
            merchant, senders, amounts = random.choice(UPI_MERCHANTS)
            amt = float(random.choice(amounts))
            balance -= amt
            ref_num = f"6{random.randint(10000000000, 99999999999)}"
            hour = random.choice([9, 12, 13, 14, 18, 19, 20, 21, 22])
            minute = random.randint(0, 59)
            ts = make_ts(hour, minute)
            
            body = f"Sent Rs. {amt:,.2f} from HDFC Bank A/c {account_num} to {merchant} via UPI on {d_str}. UPI Ref {ref_num}. Avl Bal: INR {balance:,.2f}."
            messages.append((ts, "VK-HDFCBK", body))
            
            # Merchant app confirmation (Swiggy / Zomato / Zepto / Blinkit)
            if merchant in ["Swiggy", "Zomato", "Blinkit", "Zepto"]:
                m_sender = senders[0] if len(senders) > 1 else "AD-ORDERS"
                conf_ts = ts + random.randint(120000, 300000)
                conf_body = f"Your order #{random.randint(1000000, 9999999)} at {merchant} has been placed successfully! Estimated delivery in 20-30 mins."
                messages.append((conf_ts, m_sender, conf_body))

        # -------------------------------------------------------------
        # 3. Credit Card Spend & OTP (every 2-4 days)
        # -------------------------------------------------------------
        if random.random() < 0.35:
            merchant_name, card_amts = random.choice(CARD_MERCHANTS)
            amt = float(random.choice(card_amts))
            card_outstanding += amt
            avail_lim = max(0.0, card_limit - card_outstanding)
            hour = random.choice([11, 14, 16, 18, 20, 21])
            minute = random.randint(5, 50)
            
            # OTP first
            otp_val = random.randint(100000, 999999)
            otp_ts = make_ts(hour, minute)
            otp_body = f"{otp_val} is OTP for transaction of Rs {amt:,.2f} on your HDFC Bank Card ending {card_last4} at {merchant_name}. Valid for 10 mins. Do not share with anyone."
            messages.append((otp_ts, "AX-HDFCBK", otp_body))
            
            # Spend alert 2 minutes later
            spend_ts = otp_ts + random.randint(60000, 150000)
            spend_body = f"Alert: INR {amt:,.2f} spent on your HDFC Bank Card ending {card_last4} at {merchant_name} on {d_str}. Avl Limit: INR {avail_lim:,.2f}."
            messages.append((spend_ts, "AD-HDFCBK", spend_body))

        # -------------------------------------------------------------
        # 4. Peer UPI transfers (Friends / Family) (every 4-6 days)
        # -------------------------------------------------------------
        if random.random() < 0.20:
            peer = random.choice(PEER_NAMES)
            is_incoming = random.random() < 0.35
            hour = random.choice([11, 15, 17, 19, 21])
            minute = random.randint(0, 59)
            ts = make_ts(hour, minute)
            ref_num = f"6{random.randint(10000000000, 99999999999)}"

            if is_incoming:
                p_amt = float(random.choice([350, 500, 800, 1200, 2000]))
                balance += p_amt
                body = f"Dear Customer, INR {p_amt:,.2f} received in your A/c {account_num} from {peer} via UPI on {d_str}. UPI Ref {ref_num}. Avl Bal: INR {balance:,.2f} - HDFC Bank"
            else:
                p_amt = float(random.choice([200, 350, 500, 750, 1000, 1500]))
                balance -= p_amt
                body = f"Sent Rs. {p_amt:,.2f} from HDFC Bank A/c {account_num} to {peer} via UPI on {d_str}. UPI Ref {ref_num}. Avl Bal: INR {balance:,.2f}."
            messages.append((ts, "VK-HDFCBK", body))

        # -------------------------------------------------------------
        # 5. Telecom Usage / Data Alerts (every 3-5 days)
        # -------------------------------------------------------------
        if random.random() < 0.25:
            ts = make_ts(random.choice([16, 18, 20, 22]), random.randint(10, 50))
            body = f"You have consumed 50% of your 2GB high-speed daily data quota for Jio Number {jio_num} on {d_str}. Check usage on MyJio."
            messages.append((ts, "BZ-JIOINF", body))

        # -------------------------------------------------------------
        # 6. Periodic NetBanking Login OTP / Security (every 8-12 days)
        # -------------------------------------------------------------
        if random.random() < 0.10:
            otp_val = random.randint(100000, 999999)
            ts = make_ts(random.choice([10, 14, 19]), random.randint(5, 55))
            body = f"{otp_val} is OTP for login to HDFC Bank NetBanking. Valid for 5 mins. Do not share OTP with anyone for security reasons."
            messages.append((ts, "AX-HDFCBK", body))

    # Sort all messages strictly chronologically
    messages.sort(key=lambda x: x[0])
    return messages

def seed_massive_sms(days: int = 180):
    real_host_ms = int(time.time() * 1000)
    print("================================================================================")
    print(f" 🚀 AURA OS ARM64 — Massive Financial Profile SMS Seeder ({days} Days)")
    print("================================================================================")
    
    # Check device connection
    res = run_adb(["get-state"])
    if res.stdout.strip() != "device":
        print(f"[-] Emulator {DEVICE_SERIAL} not connected! (State: {res.stdout.strip()})")
        sys.exit(1)
        
    messages = generate_financial_profile(total_days=days)
    total_msgs = len(messages)
    print(f"[+] Total Authentic Financial Transactions Generated: {total_msgs}")
    print(f"[+] Date Span: {time.strftime('%Y-%m-%d', time.localtime(messages[0][0]/1000))} to {time.strftime('%Y-%m-%d', time.localtime(messages[-1][0]/1000))}")
    print(f"[+] Starting injection via Android Emulator Modem RIL...")

    # Group messages by distinct calendar date to optimize clock synchronization
    day_groups: Dict[str, List[Tuple[int, str, str]]] = {}
    for ts, sender, body in messages:
        d_key = time.strftime("%Y-%m-%d", time.localtime(ts / 1000))
        if d_key not in day_groups:
            day_groups[d_key] = []
        day_groups[d_key].append((ts, sender, body))

    injected = 0
    t_start = time.time()
    
    try:
        total_days_count = len(day_groups)
        for day_idx, (d_key, day_msgs) in enumerate(day_groups.items(), 1):
            for ts, sender, body in day_msgs:
                # 1. Synchronize system clock to historical transaction epoch
                set_device_time(ts)
                
                # 2. Dispatch carrier SMS directly through cellular modem
                run_adb(["emu", "sms", "send", sender, body])
                injected += 1
                
                # Brief yield for modem handler to process PDU
                time.sleep(0.015)
            
            # Progress display every 10 days or on final day
            if day_idx % 15 == 0 or day_idx == total_days_count:
                pct = (injected / total_msgs) * 100.0
                elapsed = time.time() - t_start
                rate = injected / max(elapsed, 0.01)
                print(f"  [{day_idx:3d}/{total_days_count:3d} days] Injected {injected:4d}/{total_msgs} SMS ({pct:5.1f}%) | {rate:4.1f} msgs/sec | Current: {d_key}")

    finally:
        # CRITICAL: Always restore real host time
        print("\n[*] Restoring emulator system clock to exact real host time...")
        set_device_time(real_host_ms)
        date_res = run_adb(["shell", "date"]).stdout.strip()
        print(f"[+] Emulator System Time Restored: {date_res}")

    total_time = time.time() - t_start
    print(f"\n✅ Injection completed in {total_time:.2f} seconds ({injected} messages injected).")

def verify_sms_count():
    print("\n🔍 --- AUDIT OF IN-GUEST TELEPHONY SMS DATABASE ---")
    res = run_adb(["shell", "content", "query", "--uri", "content://sms", "--projection", "_id"])
    lines = [l for l in res.stdout.splitlines() if l.startswith("Row:")]
    count = len(lines)
    print(f"[+] Total Telephony SMS Rows in `content://sms`: {count}")

    # Breakdown by sender
    res_senders = run_adb(["shell", "content", "query", "--uri", "content://sms", "--projection", "address"])
    senders = {}
    for l in res_senders.stdout.splitlines():
        if "address=" in l:
            addr = l.split("address=")[1].split(",")[0].strip()
            senders[addr] = senders.get(addr, 0) + 1

    print("\n📊 Top Sender Breakdown:")
    for addr, cnt in sorted(senders.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  • {addr:15s}: {cnt:3d} messages")

    # Sample latest 5 messages
    print("\n📨 Sample Recent SMS Rows:")
    sample = run_adb(["shell", "content", "query", "--uri", "content://sms", "--projection", "address:body:date"])
    sample_rows = [l for l in sample.stdout.splitlines() if l.startswith("Row:")]
    for r in sample_rows[:5]:
        print(f"  {r}")

if __name__ == "__main__":
    days = 180
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        days = int(sys.argv[1])
    seed_massive_sms(days=days)
    verify_sms_count()
