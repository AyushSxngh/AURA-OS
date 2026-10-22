#!/usr/bin/env python3
"""
AURA OS ARM64 — Historical Transactional SMS Enricher
Populates perfectly spaced, authentic monthly financial history with verified
millisecond timestamps across May, June, July, August, September, and October 2026.
Ensures underwriting engines see 6 continuous months of verified banking activity.
"""

import os
import sys
import time
import random
import datetime
import subprocess
from typing import List, Tuple

ADB_BIN = "/opt/homebrew/bin/adb" if os.path.exists("/opt/homebrew/bin/adb") else "adb"
DEVICE_SERIAL = "emulator-5554"

def run_adb(args: List[str], check: bool = False) -> subprocess.CompletedProcess:
    cmd = [ADB_BIN, "-s", DEVICE_SERIAL] + args
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

def set_device_time(epoch_ms: int):
    run_adb(["shell", "cmd", "alarm", "set-time", str(epoch_ms)], check=True)

def generate_monthly_events() -> List[Tuple[int, str, str]]:
    """
    Generates authentic monthly financial and lifestyle transactions
    for May, June, July, August, September, and October 2026.
    """
    events = []
    
    # Financial state
    acc = "XX4821"
    card = "7014"
    jio = "9315294420"
    loan = "B849201"
    
    months = [
        (2026, 5, 20700.0, 82450.0),
        (2026, 6, 17250.0, 84200.0),
        (2026, 7, 13800.0, 84200.0),
        (2026, 8, 10350.0, 84200.0),
        (2026, 9, 6900.0, 84200.0),
        (2026, 10, 3450.0, 84200.0),
    ]
    
    bal = 88400.0
    
    for year, month, loan_rem, sal in months:
        m_str = datetime.date(year, month, 1).strftime("%b-%y")
        
        def dt_to_ms(day: int, hour: int, minute: int) -> Tuple[int, str]:
            d = datetime.datetime(year, month, min(day, 28), hour, minute, random.randint(0, 59))
            return int(d.timestamp() * 1000), d.strftime("%d-%b-%y")

        # 1. Day 1: Salary Credit
        ms, ds = dt_to_ms(1, 10, random.randint(15, 45))
        bal += sal
        events.append((ms, "VK-HDFCBK", f"Dear Customer, INR {sal:,.2f} credited to your A/c {acc} on {ds} towards Salary by INFOSYS BPM LTD. Avl Bal: INR {bal:,.2f} - HDFC Bank"))

        # 2. Day 3: Grocery UPI (Blinkit)
        ms, ds = dt_to_ms(3, 12, random.randint(10, 50))
        g_amt = round(random.uniform(520.0, 880.0), 2)
        bal -= g_amt
        ref = f"6{random.randint(10000000000, 99999999999)}"
        events.append((ms, "VK-HDFCBK", f"Sent Rs. {g_amt:,.2f} from HDFC Bank A/c {acc} to Blinkit via UPI on {ds}. UPI Ref {ref}. Avl Bal: INR {bal:,.2f}."))

        # 3. Day 5: Bajaj EMI Debit
        ms, ds = dt_to_ms(5, 11, random.randint(5, 30))
        bal -= 3450.0
        events.append((ms, "AX-BAJAJF", f"Dear Customer, your EMI of Rs 3,450.00 for Loan No. {loan} has been successfully debited from A/c {acc} on {ds}. Outstanding: Rs {loan_rem:,.2f}. - Bajaj Finserv"))

        # 4. Day 7: Credit Card Repayment & CRED Confirmation
        ms, ds = dt_to_ms(7, 13, random.randint(10, 45))
        cc_pay = round(random.uniform(12400.0, 15800.0), 2)
        bal -= cc_pay
        events.append((ms, "AD-HDFCBK", f"Thank you for payment of Rs {cc_pay:,.2f} towards your HDFC Bank Credit Card ending {card} on {ds}. Available limit: Rs {200000.0 - 1500.0:,.2f}."))
        events.append((ms + 120000, "BW-CRED", f"Payment of Rs {cc_pay:,.2f} received for HDFC Bank Credit Card ending {card}. Your payment is settled successfully."))

        # 5. Day 8: Food Delivery UPI (Swiggy)
        ms, ds = dt_to_ms(8, 20, random.randint(10, 40))
        sw_amt = round(random.uniform(320.0, 580.0), 2)
        bal -= sw_amt
        ref = f"6{random.randint(10000000000, 99999999999)}"
        events.append((ms, "VK-HDFCBK", f"Sent Rs. {sw_amt:,.2f} from HDFC Bank A/c {acc} to Swiggy via UPI on {ds}. UPI Ref {ref}. Avl Bal: INR {bal:,.2f}."))

        # 6. Day 10: Mutual Fund SIP (Zerodha)
        ms, ds = dt_to_ms(10, 9, random.randint(30, 55))
        bal -= 5000.0
        events.append((ms, "AD-ZERODH", f"Dear Investor, SIP of Rs 5,000.00 for Parag Parikh Flexi Cap Fund successfully debited via NACH from A/c {acc} on {ds}. - Zerodha Broking"))

        # 7. Day 11: BESCOM Electricity Bill
        ms, ds = dt_to_ms(11, 14, random.randint(15, 50))
        el_amt = round(random.uniform(1750.0, 2250.0), 2)
        bal -= el_amt
        ref = f"6{random.randint(10000000000, 99999999999)}"
        events.append((ms, "VK-HDFCBK", f"Sent Rs. {el_amt:,.2f} from HDFC Bank A/c {acc} to BESCOM Electricity Bill on {ds}. UPI Ref {ref}. Avl Bal: INR {bal:,.2f}."))

        # 8. Day 12: ACT Fibernet Broadband Bill
        ms, ds = dt_to_ms(12, 15, random.randint(10, 40))
        bal -= 1179.0
        ref = f"6{random.randint(10000000000, 99999999999)}"
        events.append((ms, "VK-HDFCBK", f"Sent Rs. 1,179.00 from HDFC Bank A/c {acc} to ACT Fibernet on {ds}. UPI Ref {ref}. Avl Bal: INR {bal:,.2f}."))

        # 9. Day 14: Uber Cab Commute
        ms, ds = dt_to_ms(14, 9, random.randint(10, 45))
        ub_amt = round(random.uniform(180.0, 320.0), 2)
        bal -= ub_amt
        ref = f"6{random.randint(10000000000, 99999999999)}"
        events.append((ms, "VK-HDFCBK", f"Sent Rs. {ub_amt:,.2f} from HDFC Bank A/c {acc} to Uber via UPI on {ds}. UPI Ref {ref}. Avl Bal: INR {bal:,.2f}."))

        # 10. Day 16: Amazon Shopping Card Swipe + OTP
        ms, ds = dt_to_ms(16, 17, random.randint(10, 35))
        az_amt = round(random.uniform(1200.0, 2800.0), 2)
        otp = random.randint(100000, 999999)
        events.append((ms, "AX-HDFCBK", f"{otp} is OTP for transaction of Rs {az_amt:,.2f} on your HDFC Bank Card ending {card} at AMAZON RETAIL. Valid for 10 mins. Do not share with anyone."))
        events.append((ms + 90000, "AD-HDFCBK", f"Alert: INR {az_amt:,.2f} spent on your HDFC Bank Card ending {card} at AMAZON RETAIL on {ds}. Avl Limit: INR 182,500.00."))

        # 11. Day 18: Petrol Fuel UPI (Indian Oil)
        ms, ds = dt_to_ms(18, 18, random.randint(15, 50))
        fuel_amt = round(random.uniform(1800.0, 2200.0), 2)
        bal -= fuel_amt
        ref = f"6{random.randint(10000000000, 99999999999)}"
        events.append((ms, "VK-HDFCBK", f"Sent Rs. {fuel_amt:,.2f} from HDFC Bank A/c {acc} to Indian Oil Petrol via UPI on {ds}. UPI Ref {ref}. Avl Bal: INR {bal:,.2f}."))

        # 12. Day 20: Credit Card Statement Generated
        ms, ds = dt_to_ms(20, 16, random.randint(5, 45))
        stmt_amt = round(random.uniform(13000.0, 17500.0), 2)
        events.append((ms, "AD-HDFCBK", f"Your HDFC Bank Credit Card ending {card} statement for {m_str} is generated. Total Amt Due: Rs {stmt_amt:,.2f}, Min Due: Rs {stmt_amt*0.05:,.2f}. Due Date: 07-{(datetime.date(year, month, 1) + datetime.timedelta(days=32)).strftime('%b-%y')}."))

        # 13. Day 22: Weekend Dining UPI (Zomato)
        ms, ds = dt_to_ms(22, 21, random.randint(10, 50))
        zm_amt = round(random.uniform(450.0, 780.0), 2)
        bal -= zm_amt
        ref = f"6{random.randint(10000000000, 99999999999)}"
        events.append((ms, "VK-HDFCBK", f"Sent Rs. {zm_amt:,.2f} from HDFC Bank A/c {acc} to Zomato via UPI on {ds}. UPI Ref {ref}. Avl Bal: INR {bal:,.2f}."))

        # 14. Day 25: Jio Telecom Alert
        ms, ds = dt_to_ms(25, 19, random.randint(10, 45))
        events.append((ms, "BZ-JIOINF", f"You have consumed 50% of your 2GB high-speed daily data quota for Jio Number {jio} on {ds}. Check usage on MyJio."))

        # 15. Day 27: Pharmacy UPI (Apollo Pharmacy)
        ms, ds = dt_to_ms(27, 15, random.randint(10, 45))
        ph_amt = round(random.uniform(320.0, 640.0), 2)
        bal -= ph_amt
        ref = f"6{random.randint(10000000000, 99999999999)}"
        events.append((ms, "VK-HDFCBK", f"Sent Rs. {ph_amt:,.2f} from HDFC Bank A/c {acc} to Apollo Pharmacy via UPI on {ds}. UPI Ref {ref}. Avl Bal: INR {bal:,.2f}."))

    # Sort strictly chronologically
    events.sort(key=lambda x: x[0])
    return events

def run_enrichment():
    real_host_ms = int(time.time() * 1000)
    print("================================================================================")
    print(" 🚀 AURA OS ARM64 — 6-Month Historical SMS Enricher")
    print("================================================================================")
    
    events = generate_monthly_events()
    print(f"[+] Total Verified Historical Financial Events to Seed: {len(events)}")
    print(f"[+] Span: {time.strftime('%d-%b-%Y', time.localtime(events[0][0]/1000))} to {time.strftime('%d-%b-%Y', time.localtime(events[-1][0]/1000))}")
    print("[+] Seeding with dedicated modem commit intervals (320ms)...")
    
    t0 = time.time()
    try:
        for idx, (epoch_ms, sender, body) in enumerate(events, 1):
            # 1. Set historical clock
            set_device_time(epoch_ms)
            
            # 2. Transmit SMS through modem
            run_adb(["emu", "sms", "send", sender, body], check=True)
            
            # 3. Allow InboundSmsHandler to commit row to SQLite before clock changes
            time.sleep(0.32)
            
            if idx % 15 == 0 or idx == len(events):
                pct = (idx / len(events)) * 100
                d_str = time.strftime("%Y-%m-%d", time.localtime(epoch_ms/1000))
                print(f"  [{idx:3d}/{len(events):3d}] ({pct:5.1f}%) | Seeded date: {d_str} | From: {sender:10s}")

    finally:
        print("\n[*] Restoring emulator system clock to exact real host time...")
        set_device_time(real_host_ms)
        date_res = run_adb(["shell", "date"]).stdout.strip()
        print(f"[+] Device System Clock Restored: {date_res}")

    print(f"✅ Seeding finished in {time.time() - t0:.2f}s.")

if __name__ == "__main__":
    run_enrichment()
