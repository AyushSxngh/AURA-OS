#!/usr/bin/env python3
"""
Samsung Electronics Co., Ltd. — Galaxy S24 Ultra Hardware Battery Service
Daemon simulating genuine Samsung Battery management:
1. Dynamic discharging: drops steadily over time (1% every ~2-3 minutes during active use)
2. Super Fast Charging: charges smoothly (0-50% in ~20m, 50-80% in ~25m, 80-100% taper)
3. Dynamic capacity adjustment: 5000 mAh total, counter in µAh (level * 50,000 µAh)
4. Non-linear Li-ion voltage curve: 3550 mV to 4350 mV
5. Thermal dynamics: discharging ~29.2-32.0°C, charging ~34-37.5°C
6. True persistence: state saves to disk continuously and survives reboots
"""

import os
import sys
import time
import json
import random
import subprocess
import signal

STATE_FILE = "/tmp/sec_battery_state.json"
PID_FILE = "/tmp/sec_battery_service.pid"
LOG_FILE = "/tmp/sec_battery_service.log"

BATTERY_CAPACITY_MAH = 5000
BATTERY_CAPACITY_UAH = BATTERY_CAPACITY_MAH * 1000  # 5,000,000 uAh

# Non-linear Li-ion OCV discharge/charge curve (level -> voltage in mV)
VOLTAGE_POINTS = [
    (100, 4350),
    (95, 4280),
    (90, 4210),
    (80, 4130),
    (70, 4060),
    (60, 4000),
    (50, 3930),
    (40, 3870),
    (30, 3820),
    (20, 3760),
    (10, 3680),
    (5, 3620),
    (0, 3550),
]

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] [sec_battery_service] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def get_voltage_mv(level: int, is_charging: bool) -> int:
    for i in range(len(VOLTAGE_POINTS) - 1):
        l_high, v_high = VOLTAGE_POINTS[i]
        l_low, v_low = VOLTAGE_POINTS[i + 1]
        if l_low <= level <= l_high:
            ratio = (level - l_low) / max(1, (l_high - l_low))
            base_v = v_low + ratio * (v_high - v_low)
            if is_charging:
                base_v += random.randint(30, 70)  # Charging IR drop delta
            else:
                base_v += random.randint(-8, 8)   # Minor load fluctuation
            return int(base_v)
    return 3850

def get_temp_c(is_charging: bool, level: int) -> float:
    if is_charging:
        if level > 85:
            return round(33.5 + random.uniform(0.1, 0.8), 1)
        return round(35.5 + random.uniform(0.1, 1.2), 1)
    else:
        return round(29.2 + random.uniform(0.1, 0.8), 1)

def run_adb(cmd: str) -> str:
    try:
        res = subprocess.run(f"adb {cmd}", shell=True, capture_output=True, text=True, timeout=10)
        return res.stdout.strip()
    except Exception:
        return ""

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
                if "auto_charge_threshold" not in state or state["auto_charge_threshold"] not in range(1, 16):
                    state["auto_charge_threshold"] = random.randint(1, 15)
                if "target_full_threshold" not in state:
                    state["target_full_threshold"] = random.randint(85, 95)
                # If level is critically low from previous shutdown, recover to safe charging level
                if int(state.get("level", 0)) < 15:
                    state["level"] = random.randint(25, 45)
                    state["is_charging"] = True
                return state
        except Exception:
            pass
    # Default initial state
    default_state = {
        "level": 42,
        "is_charging": False,
        "last_tick": time.time(),
        "discharge_interval_sec": 120,  # ~1% drop every 2 minutes (active phone use)
        "charge_interval_sec": 60,      # ~1% gain every 60 seconds (Samsung 45W PPS fast charge)
        "auto_charge_threshold": random.randint(1, 15), # Pick random 1 to 15 %
        "target_full_threshold": random.randint(85, 95),
        "demo_mode": False
    }
    save_state(default_state)
    return default_state

def save_state(state: dict):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def apply_battery_state(state: dict) -> dict:
    level = max(0, min(100, int(state.get("level", 43))))
    is_charging = bool(state.get("is_charging", False))

    if level >= 100 and is_charging:
        status_val = 5  # 5: FULL
        status_str = "Full"
    elif is_charging:
        status_val = 2  # 2: CHARGING
        status_str = "Charging"
    else:
        status_val = 3  # 3: DISCHARGING
        status_str = "Discharging"

    ac_val = "1" if is_charging else "0"

    voltage_mv = get_voltage_mv(level, is_charging)
    temp_c = get_temp_c(is_charging, level)
    temp_decic = int(temp_c * 10)

    # Dynamic capacity scaling: level * 50,000 uAh
    counter_uah = int(level * (BATTERY_CAPACITY_UAH / 100))
    counter_mah = counter_uah / 1000.0

    # Inject into Android Batterystats & BatteryManager
    cmd = (
        f"shell \"dumpsys battery set ac {ac_val}; "
        f"dumpsys battery set status {status_val}; "
        f"dumpsys battery set level {level}; "
        f"dumpsys battery set voltage {voltage_mv}; "
        f"dumpsys battery set temp {temp_decic}; "
        f"dumpsys battery set counter {counter_uah}\""
    )
    run_adb(cmd)

    return {
        "level": level,
        "status_str": status_str,
        "ac": is_charging,
        "voltage_mv": voltage_mv,
        "temp_c": temp_c,
        "counter_mah": counter_mah,
        "counter_uah": counter_uah
    }

def get_target_interval(state: dict) -> float:
    if state.get("demo_mode", False):
        return 6.0 if state.get("is_charging", False) else 10.0
    
    is_charging = state.get("is_charging", False)
    level = state.get("level", 43)

    if is_charging:
        # Samsung 45W PPS charging curve:
        # Fast below 50% (~35s per 1%), moderate 50-80% (~55s per 1%), trickle above 80% (~80s per 1%)
        if level < 50:
            return 35.0
        elif level < 80:
            return 55.0
        else:
            return 80.0
    else:
        # Normal discharge curve: ~120s per 1% during active use, ~180s when idle
        return float(state.get("discharge_interval_sec", 120))

def daemon_loop():
    pid = os.getpid()
    log(f"Samsung Electronics Battery Service started (PID {pid})")
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(pid))
    except Exception:
        pass

    state = load_state()
    # Apply initial state right away
    apply_battery_state(state)

    while True:
        try:
            # Reload state in case external CLI modified it (e.g., plug/unplug/set-level)
            state = load_state()
            now = time.time()
            last_tick = state.get("last_tick", now)
            elapsed = now - last_tick

            target_interval = get_target_interval(state)

            if elapsed >= target_interval:
                current_level = int(state.get("level", 43))
                is_charging = bool(state.get("is_charging", False))
                auto_charge_threshold = int(state.get("auto_charge_threshold", random.randint(1, 15)))
                target_full_threshold = int(state.get("target_full_threshold", random.randint(85, 95)))

                if is_charging:
                    if current_level < 100:
                        state["level"] = current_level + 1
                    else:
                        state["level"] = 100

                    # Auto-unplug once full target reached
                    if state["level"] >= target_full_threshold:
                        state["is_charging"] = False
                        # Pick new random 1 to 15 % for the next auto-charge trigger
                        state["auto_charge_threshold"] = random.randint(1, 15)
                        state["target_full_threshold"] = random.randint(85, 95)
                        log(f"⚡ Charged to {state['level']}% (target reached). Auto-unplugged! Next auto-charge threshold: {state['auto_charge_threshold']}%.")
                else:
                    new_level = current_level - 1
                    # Auto-charge trigger: when level comes down to under 15 (picked random 1 to 15)
                    if new_level <= auto_charge_threshold:
                        state["level"] = max(1, new_level)
                        state["is_charging"] = True
                        log(f"🔋 Battery dropped to {state['level']}% (hit auto-charge threshold {auto_charge_threshold}%). Auto-plugging in charger (Fast Charging)!")
                    else:
                        state["level"] = max(1, new_level)

                state["last_tick"] = now
                save_state(state)
                info = apply_battery_state(state)
                log(f"Battery Update: {info['level']}% {info['status_str']} | {info['voltage_mv']}mV | {info['temp_c']}°C | {info['counter_mah']} mAh | Auto-Charge: {state.get('auto_charge_threshold')}%")
            else:
                # Keep state fresh without changing level
                apply_battery_state(state)

            time.sleep(2.0)
        except Exception as e:
            log(f"Error in battery daemon: {e}")
            time.sleep(2.0)

def stop_daemon():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"🛑 Stopped daemon (PID {pid})")
        except Exception:
            pass
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

def main():
    if len(sys.argv) < 2:
        print("Usage: sec_battery_service.py [start|stop|status|plug|unplug|set-level <N>|drop-now|demo-on|demo-off|seed-history]")
        return

    cmd = sys.argv[1].lower()

    if cmd == "daemon":
        daemon_loop()
    elif cmd == "start":
        stop_daemon()
        script = os.path.abspath(__file__)
        log_f = open(LOG_FILE, "a")
        proc = subprocess.Popen([sys.executable, "-u", script, "daemon"], stdin=subprocess.DEVNULL, stdout=log_f, stderr=log_f, start_new_session=True)
        print(f"🚀 Started Samsung Battery Service in background (PID {proc.pid})")
    elif cmd == "stop":
        stop_daemon()
    elif cmd == "status":
        state = load_state()
        info = apply_battery_state(state)
        target_sec = get_target_interval(state)
        elapsed = time.time() - state.get("last_tick", time.time())
        next_sec = max(0, int(target_sec - elapsed))
        is_running = False
        pid_val = None
        if os.path.exists(PID_FILE):
            try:
                pid_val = int(open(PID_FILE).read().strip())
                os.kill(pid_val, 0)
                is_running = True
            except Exception:
                is_running = False

        print(f"📊 Samsung Galaxy S24 Ultra Battery Status:")
        print(f"   Daemon: {'RUNNING (PID ' + str(pid_val) + ')' if is_running else 'STOPPED'}")
        print(f"   Level: {info['level']}%")
        print(f"   State: {info['status_str']} (AC: {info['ac']})")
        print(f"   Voltage: {info['voltage_mv']} mV (Non-linear Li-ion curve)")
        print(f"   Temperature: {info['temp_c']} °C")
        print(f"   Capacity Counter: {info['counter_mah']} mAh ({info['counter_uah']} µAh) / {BATTERY_CAPACITY_MAH} mAh")
        print(f"   Next Level Change In: ~{next_sec} seconds ({'charging' if info['ac'] else 'discharging'} rate)")
        print(f"   Demo Mode (Accelerated): {state.get('demo_mode', False)}")
    elif cmd == "plug":
        state = load_state()
        state["is_charging"] = True
        state["last_tick"] = time.time()
        save_state(state)
        run_adb("shell am broadcast -a com.android.settings.battery.action.ACTION_BATTERY_PLUGGING -n com.android.settings/.fuelgauge.batteryusage.BatteryUsageBroadcastReceiver >/dev/null 2>&1")
        info = apply_battery_state(state)
        print(f"⚡ Charger Plugged In: {info['level']}% Charging ({info['voltage_mv']}mV, {info['temp_c']}°C, {info['counter_mah']} mAh)")
    elif cmd == "unplug":
        state = load_state()
        state["is_charging"] = False
        state["last_tick"] = time.time()
        save_state(state)
        run_adb("shell am broadcast -a com.android.settings.battery.action.ACTION_BATTERY_UNPLUGGING -n com.android.settings/.fuelgauge.batteryusage.BatteryUsageBroadcastReceiver >/dev/null 2>&1")
        info = apply_battery_state(state)
        print(f"🔋 Charger Unplugged: {info['level']}% Discharging ({info['voltage_mv']}mV, {info['temp_c']}°C, {info['counter_mah']} mAh)")
    elif cmd == "drop-now":
        state = load_state()
        cur = int(state.get("level", 43))
        state["level"] = max(0, cur - 1)
        state["last_tick"] = time.time()
        save_state(state)
        info = apply_battery_state(state)
        print(f"📉 Discharged 1%: {cur}% -> {info['level']}% ({info['voltage_mv']}mV, {info['counter_mah']} mAh)")
    elif cmd == "set-level":
        if len(sys.argv) < 3:
            print("Please provide level (0-100)")
            return
        lvl = max(0, min(100, int(sys.argv[2])))
        state = load_state()
        state["level"] = lvl
        state["last_tick"] = time.time()
        save_state(state)
        info = apply_battery_state(state)
        print(f"🎯 Battery level set to {lvl}% ({info['status_str']}, {info['voltage_mv']}mV, {info['counter_mah']} mAh)")
    elif cmd == "demo-on":
        state = load_state()
        state["demo_mode"] = True
        save_state(state)
        print("⏩ Demo mode ON: Battery ticks every 10 seconds for visual observation")
    elif cmd == "demo-off":
        state = load_state()
        state["demo_mode"] = False
        save_state(state)
        print("⏱️ Demo mode OFF: Battery ticks at realistic phone rate")
    elif cmd == "seed-history":
        from seed_battery_history import seed_history
        seed_history()
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
