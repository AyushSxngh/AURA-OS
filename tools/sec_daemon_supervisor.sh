#!/usr/bin/env bash
# ==============================================================================
# AURA OS — Master Background Daemons & Anti-Detection Supervisor
# ==============================================================================
# This supervisor runs autonomously in the background on macOS.
# Whenever the Android emulator boots, it automatically ensures:
# 1. Reverse port 8080 forwarding (Camera stream to guest)
# 2. Battery service (sec_battery_service.py - auto drain & auto charge 1-15%)
# 3. Wi-Fi service (sec_wifi_service.py - live host Wi-Fi stack & Indian RF environment)
# 4. Sensor service (sec_sensor_service.py - Gaussian motion jitter)
# 5. Location sync (sync-location.sh - host CoreLocation GPS to emulator)
# 6. Bridge service (sec_bridge_service.py - offline host <-> guest file transfer on port 8088)
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( cd "$DIR/.." >/dev/null 2>&1 && pwd )"

# Singleton check
PID_FILE="/tmp/sec_daemon_supervisor.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        # Already running
        exit 0
    fi
fi
echo "$$" > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT

# Locate ADB
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
ADB="$ANDROID_HOME/platform-tools/adb"
if [ ! -x "$ADB" ]; then
    if command -v adb >/dev/null 2>&1; then
        ADB="adb"
    else
        echo "⚠️ ADB not found!"
        exit 1
    fi
fi

LAST_LOCATION_SYNC=0
WAS_ONLINE=0

echo "🚀 [$(date '+%Y-%m-%d %H:%M:%S')] AURA OS Supervisor active (PID $$)"

while true; do
    # Check if QEMU or emulator is running
    if pgrep -f "qemu-system-aarch64" >/dev/null 2>&1 || pgrep -f "emulator.*AURA_OS" >/dev/null 2>&1; then
        # Check if ADB detects device
        STATE=$("$ADB" -s emulator-5554 get-state 2>/dev/null || true)
        if [ "$STATE" = "device" ]; then
            BOOT_COMPLETE=$("$ADB" -s emulator-5554 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r\n')
            
            if [ "$BOOT_COMPLETE" = "1" ]; then
                # Device is online and boot completed
                if [ "$WAS_ONLINE" -eq 0 ]; then
                    echo "📱 [$(date '+%Y-%m-%d %H:%M:%S')] Emulator boot completed! Initializing background services..."
                    WAS_ONLINE=1
                fi

                # 1. Reverse camera proxy (tcp:8080)
                if ! "$ADB" -s emulator-5554 reverse --list 2>/dev/null | grep -q "tcp:8080"; then
                    "$ADB" -s emulator-5554 reverse tcp:8080 tcp:8080 >/dev/null 2>&1 || true
                fi

                # 1b. Camera Shared Memory bridge (/tmp/sec_cam_shm <-> /tmp/aura_cam_shm)
                if [ -e "/tmp/aura_cam_shm" ] && [ ! -e "/tmp/sec_cam_shm" ]; then
                    ln -sf /tmp/aura_cam_shm /tmp/sec_cam_shm 2>/dev/null || true
                fi

                # 2. Battery Daemon (sec_battery_service.py)
                if ! pgrep -f "sec_battery_service.py daemon" >/dev/null 2>&1; then
                    echo "🔋 Starting sec_battery_service daemon..."
                    python3 "$DIR/sec_battery_service.py" start >/dev/null 2>&1 || true
                fi

                # 3. Wi-Fi Daemon (sec_wifi_service.py)
                if ! pgrep -f "sec_wifi_service.py daemon" >/dev/null 2>&1; then
                    echo "📶 Starting sec_wifi_service daemon..."
                    python3 "$DIR/sec_wifi_service.py" start >/dev/null 2>&1 || true
                fi

                # 4. Sensor Daemon (sec_sensor_service.py)
                if ! pgrep -f "sec_sensor_service.py daemon" >/dev/null 2>&1; then
                    echo "🧭 Starting sec_sensor_service daemon..."
                    python3 "$DIR/sec_sensor_service.py" start >/dev/null 2>&1 || true
                fi

                # 5. Location Daemon (sec_location_service.py - continuous IP GNSS sync)
                if ! pgrep -f "sec_location_service.py daemon" >/dev/null 2>&1; then
                    echo "📍 Starting sec_location_service daemon..."
                    python3 "$DIR/sec_location_service.py" start >/dev/null 2>&1 || true
                fi

                # 6. Offline Transfer Bridge Service (sec_bridge_service.py) & Port Forwarding
                if ! "$ADB" -s emulator-5554 reverse --list 2>/dev/null | grep -q "tcp:8088"; then
                    "$ADB" -s emulator-5554 reverse tcp:8088 tcp:8088 >/dev/null 2>&1 || true
                fi

                if ! pgrep -f "sec_bridge_service.py daemon" >/dev/null 2>&1; then
                    echo "🌉 Starting sec_bridge_service daemon..."
                    python3 "$DIR/sec_bridge_service.py" start >/dev/null 2>&1 || true
                fi
            fi
        else
            WAS_ONLINE=0
        fi
    else
        WAS_ONLINE=0
    fi

    sleep 5
done
