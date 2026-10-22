#!/usr/bin/env python3
"""
Samsung Electronics Co., Ltd. — Galaxy S24 Ultra Sensor Noise Service
Daemon injecting Gaussian noise (μ=0, σ=0.02) into accelerometer and gyroscope
input streams to simulate realistic human physical micro-tremors and sensor ADC noise.
"""

import os
import sys
import time
import json
import socket
import random
import signal
import subprocess
from typing import Tuple, Generator

PID_FILE = "/tmp/sec_sensor_service.pid"
LOG_FILE = "/tmp/sec_sensor_service.log"
STATE_FILE = "/tmp/sec_sensor_state.json"

DEFAULT_POSTURES = {
    # Handheld portrait tilted ~15° back (||g|| ≈ 9.81 m/s²)
    "portrait": {"accel": [0.15, 9.65, 1.75], "gyro": [0.0, 0.0, 0.0]},
    # Flat on desk/table
    "flat": {"accel": [0.0, 0.0, 9.81], "gyro": [0.0, 0.0, 0.0]},
    # Landscape handheld
    "landscape": {"accel": [9.65, 0.15, 1.75], "gyro": [0.0, 0.0, 0.0]},
}

def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] [sec_sensor_service] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "mu": 0.0,
        "sigma": 0.02,
        "sampling_rate_hz": 25.0,
        "posture": "portrait",
        "accel_base": DEFAULT_POSTURES["portrait"]["accel"],
        "gyro_base": DEFAULT_POSTURES["portrait"]["gyro"],
        "enable_hand_drift": True,
        "active": True
    }

def save_state(state: dict):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

class SensorNoiseInjector:
    """
    Mathematical Gaussian noise injector for tri-axial sensors.
    """
    def __init__(self, state: dict):
        self.mu = state.get("mu", 0.0)
        self.sigma = state.get("sigma", 0.02)
        self.sampling_rate_hz = state.get("sampling_rate_hz", 25.0)
        self.dt = 1.0 / max(1.0, self.sampling_rate_hz)
        self.enable_hand_drift = state.get("enable_hand_drift", True)

        self.accel_base = list(state.get("accel_base", DEFAULT_POSTURES["portrait"]["accel"]))
        self.gyro_base = list(state.get("gyro_base", DEFAULT_POSTURES["portrait"]["gyro"]))

        self._drift_accel = [0.0, 0.0, 0.0]
        self._drift_gyro = [0.0, 0.0, 0.0]

    def update_params(self, state: dict):
        self.mu = state.get("mu", 0.0)
        self.sigma = state.get("sigma", 0.02)
        self.accel_base = list(state.get("accel_base", self.accel_base))
        self.gyro_base = list(state.get("gyro_base", self.gyro_base))
        self.enable_hand_drift = state.get("enable_hand_drift", True)

    def _sample_noise(self) -> Tuple[float, float, float]:
        return (
            random.gauss(self.mu, self.sigma),
            random.gauss(self.mu, self.sigma),
            random.gauss(self.mu, self.sigma)
        )

    def step(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        noise_a = self._sample_noise()
        noise_g = self._sample_noise()

        if self.enable_hand_drift:
            for i in range(3):
                self._drift_accel[i] = self._drift_accel[i] * 0.92 + random.gauss(0.0, 0.005)
                self._drift_gyro[i] = self._drift_gyro[i] * 0.90 + random.gauss(0.0, 0.004)
        else:
            self._drift_accel = [0.0, 0.0, 0.0]
            self._drift_gyro = [0.0, 0.0, 0.0]

        accel = (
            round(self.accel_base[0] + self._drift_accel[0] + noise_a[0], 5),
            round(self.accel_base[1] + self._drift_accel[1] + noise_a[1], 5),
            round(self.accel_base[2] + self._drift_accel[2] + noise_a[2], 5),
        )
        gyro = (
            round(self.gyro_base[0] + self._drift_gyro[0] + noise_g[0], 5),
            round(self.gyro_base[1] + self._drift_gyro[1] + noise_g[1], 5),
            round(self.gyro_base[2] + self._drift_gyro[2] + noise_g[2], 5),
        )
        return accel, gyro


class EmulatorConsoleClient:
    """Manages persistent connection to Android Emulator console."""
    def __init__(self, host: str = "127.0.0.1", port: int = 5554):
        self.host = host
        self.port = port
        self.sock = None

    def _get_auth_token(self) -> str:
        token_path = os.path.expanduser("~/.emulator_console_auth_token")
        if os.path.exists(token_path):
            try:
                with open(token_path, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return ""

    def connect(self) -> bool:
        if self.sock:
            return True
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect((self.host, self.port))
            s.recv(1024)  # Greeting

            token = self._get_auth_token()
            if token:
                s.sendall(f"auth {token}\n".encode())
                res = s.recv(1024).decode()
                if "OK" not in res:
                    s.close()
                    return False
            self.sock = s
            return True
        except Exception:
            self.sock = None
            return False

    def send_sensor_data(self, accel: Tuple[float, float, float], gyro: Tuple[float, float, float]) -> bool:
        if not self.connect():
            return False
        try:
            # Batch both sensor set commands in one socket frame for low latency
            payload = (
                f"sensor set acceleration {accel[0]}:{accel[1]}:{accel[2]}\n"
                f"sensor set gyroscope {gyro[0]}:{gyro[1]}:{gyro[2]}\n"
            ).encode()
            self.sock.sendall(payload)
            return True
        except Exception:
            try:
                if self.sock:
                    self.sock.close()
            except Exception:
                pass
            self.sock = None
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


def daemon_loop():
    pid = os.getpid()
    log(f"Samsung Sensor Noise Daemon started (PID {pid})")
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(pid))
    except Exception:
        pass

    state = load_state()
    injector = SensorNoiseInjector(state)
    client = EmulatorConsoleClient()

    last_state_check = time.time()
    last_log_time = time.time()
    injected_count = 0

    while True:
        try:
            t0 = time.time()

            # Refresh dynamic state every 3 seconds
            if t0 - last_state_check >= 3.0:
                last_state_check = t0
                state = load_state()
                injector.update_params(state)

            if not state.get("active", True):
                time.sleep(1.0)
                continue

            accel, gyro = injector.step()
            success = client.send_sensor_data(accel, gyro)
            if success:
                injected_count += 1
            else:
                # If emulator is not running, back off briefly
                time.sleep(0.5)

            # Log periodically
            if t0 - last_log_time >= 30.0:
                last_log_time = t0
                log(f"Injected {injected_count} frames | Accel: [{accel[0]:+0.3f}, {accel[1]:+0.3f}, {accel[2]:+0.3f}] m/s² | Gyro: [{gyro[0]:+0.3f}, {gyro[1]:+0.3f}, {gyro[2]:+0.3f}] rad/s")
                injected_count = 0

            # Sleep to match target sampling rate
            elapsed = time.time() - t0
            sleep_time = injector.dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        except Exception as e:
            log(f"Daemon exception: {e}")
            time.sleep(1.0)


def stop_daemon():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"🛑 Stopped Sensor Daemon (PID {pid})")
        except Exception:
            pass
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

def main():
    if len(sys.argv) < 2:
        print("Usage: sec_sensor_service.py [start|stop|status|daemon|test|set-posture <portrait|flat|landscape>]")
        return

    cmd = sys.argv[1].lower()

    if cmd == "daemon":
        daemon_loop()
    elif cmd == "start":
        stop_daemon()
        script = os.path.abspath(__file__)
        log_f = open(LOG_FILE, "a")
        proc = subprocess.Popen([sys.executable, "-u", script, "daemon"], stdin=subprocess.DEVNULL, stdout=log_f, stderr=log_f, start_new_session=True)
        print(f"🚀 Started Samsung Sensor Noise Service in background (PID {proc.pid})")
    elif cmd == "stop":
        stop_daemon()
    elif cmd == "status":
        state = load_state()
        is_running = False
        pid_val = None
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    pid_val = int(f.read().strip())
                os.kill(pid_val, 0)
                is_running = True
            except Exception:
                is_running = False

        print("📊 Samsung Galaxy S24 Ultra Sensor Noise Service Status:")
        print(f"   Status: {'RUNNING (PID ' + str(pid_val) + ')' if is_running else 'STOPPED'}")
        print(f"   Noise Parameters: μ={state['mu']}, σ={state['sigma']}")
        print(f"   Sampling Rate: {state['sampling_rate_hz']} Hz")
        print(f"   Current Posture: {state['posture']}")
        print(f"   Base Accelerometer: {state['accel_base']} m/s²")
        print(f"   Base Gyroscope: {state['gyro_base']} rad/s")
        print(f"   Physiological Drift: {state['enable_hand_drift']}")

        # Sample test reading
        injector = SensorNoiseInjector(state)
        accel, gyro = injector.step()
        print(f"   Live Sample -> Accel: {accel} m/s² | Gyro: {gyro} rad/s")

    elif cmd == "set-posture":
        if len(sys.argv) < 3:
            print("Please specify posture: portrait, flat, or landscape")
            return
        posture = sys.argv[2].lower()
        if posture not in DEFAULT_POSTURES:
            print(f"Unknown posture: {posture}. Available: portrait, flat, landscape")
            return
        state = load_state()
        state["posture"] = posture
        state["accel_base"] = DEFAULT_POSTURES[posture]["accel"]
        state["gyro_base"] = DEFAULT_POSTURES[posture]["gyro"]
        save_state(state)
        print(f"🎯 Sensor posture updated to '{posture}': {state['accel_base']} m/s²")

    elif cmd == "test":
        state = load_state()
        injector = SensorNoiseInjector(state)
        client = EmulatorConsoleClient()
        connected = client.connect()
        print(f"[+] Emulator Connected: {connected}")
        print("[+] Streaming live noisy sensor samples (Press Ctrl+C to stop)...")
        try:
            for _ in range(30):
                accel, gyro = injector.step()
                if connected:
                    client.send_sensor_data(accel, gyro)
                sys.stdout.write(
                    f"\rAccel: [{accel[0]:+0.4f}, {accel[1]:+0.4f}, {accel[2]:+0.4f}] m/s² | "
                    f"Gyro: [{gyro[0]:+0.4f}, {gyro[1]:+0.4f}, {gyro[2]:+0.4f}] rad/s"
                )
                sys.stdout.flush()
                time.sleep(injector.dt)
            print("\n[+] Test complete.")
        except KeyboardInterrupt:
            print("\n[+] Stopped.")
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
