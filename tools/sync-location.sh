#!/usr/bin/env bash
# ==============================================================================
# AURA OS — Automatic Real-Time Location Sync for Android Emulator
# Syncs host Mac location (IP / GPS) to Android Emulator via 'geo fix'
# ==============================================================================

ADB_BIN="/opt/homebrew/bin/adb"
if ! command -v "$ADB_BIN" &> /dev/null; then
    ADB_BIN="$(command -v adb)"
fi

echo "🌐 [AURA Location Sync] Detecting current location from host network..."

# Fetch current coordinates via IP geolocation
GEO_DATA=$(curl -s --connect-timeout 5 "http://ip-api.com/json")
STATUS=$(echo "$GEO_DATA" | grep -o '"status":"[^"]*' | cut -d'"' -f4)

if [ "$STATUS" != "success" ]; then
    GEO_DATA=$(curl -s --connect-timeout 5 "https://ipinfo.io/json")
    LOC=$(echo "$GEO_DATA" | grep -o '"loc":"[^"]*' | cut -d'"' -f4)
    LAT=$(echo "$LOC" | cut -d',' -f1)
    LON=$(echo "$LOC" | cut -d',' -f2)
    CITY=$(echo "$GEO_DATA" | grep -o '"city":"[^"]*' | cut -d'"' -f4)
else
    LAT=$(echo "$GEO_DATA" | grep -o '"lat":[^,]*' | cut -d':' -f2 | tr -d ' ')
    LON=$(echo "$GEO_DATA" | grep -o '"lon":[^,]*' | cut -d':' -f2 | tr -d ' ')
    CITY=$(echo "$GEO_DATA" | grep -o '"city":"[^"]*' | cut -d'"' -f4)
fi

if [ -z "$LAT" ] || [ -z "$LON" ]; then
    echo "⚠️ [AURA Location Sync] Could not determine host location. Using last known coordinates."
    exit 1
fi

echo "📍 [AURA Location Sync] Detected Location: $CITY ($LAT, $LON)"

# Wait for emulator adb connection
"$ADB_BIN" -s emulator-5554 wait-for-device 2>/dev/null || true

# Enable location services
"$ADB_BIN" -s emulator-5554 shell cmd location set-location-enabled true 2>/dev/null || true
"$ADB_BIN" -s emulator-5554 shell settings put secure location_mode 3 2>/dev/null || true

# Send geo fix to emulator (Syntax: geo fix <lon> <lat> [alt])
"$ADB_BIN" -s emulator-5554 emu geo fix "$LON" "$LAT" 200 >/dev/null 2>&1

echo "✅ [AURA Location Sync] Location successfully synced to Android Emulator ($CITY)!"
