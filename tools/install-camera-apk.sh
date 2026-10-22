#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
APK_PATH="/Users/ayush/Desktop/AURA-DeepFake-Camera.apk"
ADB_BIN="/opt/homebrew/bin/adb"

if ! command -v "$ADB_BIN" &> /dev/null; then
    ADB_BIN="$(command -v adb)"
fi

echo "========================================================"
echo "    📸 Installing AURA DeepFake Camera into AURA OS     "
echo "========================================================"
echo ""

if [ ! -f "$APK_PATH" ]; then
    echo "❌ APK not found at $APK_PATH"
    read -p "Press [Enter] to exit..."
    exit 1
fi

echo "⏳ Checking for running AURA OS emulator via adb..."
DEVICE_COUNT=$("$ADB_BIN" devices | grep -v "List" | grep "device" | wc -l | tr -d ' ')

if [ "$DEVICE_COUNT" -eq "0" ]; then
    echo "⚠️  No emulator detected! Please start AURA OS first, then run this installer."
    echo "   (You can start it with /Users/ayush/Desktop/AURA\ OS.app or Launch-AURA-OS.command)"
    echo ""
    read -p "Press [Enter] once AURA OS is running to continue..."
fi

echo "📦 Installing Camera app ($APK_PATH)..."
"$ADB_BIN" uninstall com.aura.camera 2>/dev/null || true
"$ADB_BIN" install -r -d -g "$APK_PATH"

echo "🔑 Granting camera and storage permissions..."
"$ADB_BIN" shell pm grant com.sec.android.app.camera android.permission.CAMERA 2>/dev/null || true
"$ADB_BIN" shell pm grant com.sec.android.app.camera android.permission.RECORD_AUDIO 2>/dev/null || true
"$ADB_BIN" shell pm grant com.sec.android.app.camera android.permission.READ_MEDIA_IMAGES 2>/dev/null || true

echo "⚙️  Setting Camera as default system camera app..."
"$ADB_BIN" shell cmd role set-bidi-default-holder android.app.role.CAMERA com.sec.android.app.camera 2>/dev/null || true

echo "🚀 Launching Camera in emulator..."
"$ADB_BIN" shell monkey -p com.sec.android.app.camera -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1

echo ""
echo "========================================================"
echo "✅ Installation complete!"
echo "   AURA DeepFake Camera is set as your default camera."
echo "   It runs 100% on-device inside the emulator and can"
echo "   optionally connect to your Mac for 60 FPS CoreML."
echo "========================================================"
echo ""
read -p "Press [Enter] to exit..."
