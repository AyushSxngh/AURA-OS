#!/usr/bin/env bash
# ==============================================================================
# AURA OS — macOS One-Click Launcher (Apple Silicon M1-M5 & Intel)
# ==============================================================================

set -e

# Resolve repository root directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "========================================================"
echo "    🚀 AURA OS — Android 14 Virtualization Platform     "
echo "           Native macOS & Apple Silicon Edition         "
echo "========================================================"
echo ""

# Ensure Rust / Cargo is on PATH
if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
fi

if ! command -v cargo &> /dev/null; then
    echo "⚠️  Rust toolchain not found!"
    echo "   Please install Rust by opening Terminal and running:"
    echo "   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo ""
    read -p "Press [Enter] to exit..."
    exit 1
fi

# Detect Android SDK
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}"

if [ ! -d "$ANDROID_HOME" ]; then
    echo "⚠️  Android SDK not found at $ANDROID_HOME"
    echo "   Please install Android Studio for Mac (Apple Silicon) from:"
    echo "   https://developer.android.com/studio"
    echo ""
fi

# Auto-start DeepFake Realtime streaming engine in background if not already running
if ! nc -z 127.0.0.1 8080 2>/dev/null; then
    echo "🎭 Starting DeepFake Realtime background engine..."
    DEEPFAKE_DIR="/Users/ayush/Desktop/DeepFake/DeepFake_realtime"
    if [ -f "$DEEPFAKE_DIR/.venv_mac/bin/python" ]; then
        nohup "$DEEPFAKE_DIR/.venv_mac/bin/python" "$DEEPFAKE_DIR/main.py" > "$DEEPFAKE_DIR/app.log" 2>&1 &
        (for i in {1..10}; do nc -z 127.0.0.1 8080 2>/dev/null && curl -s -X POST http://127.0.0.1:8080/api/start_camera >/dev/null 2>&1 && break; sleep 1; done) &
    fi
else
    # Ensure camera capture is active for QEMU injection
    curl -s -X POST http://127.0.0.1:8080/api/start_camera >/dev/null 2>&1 &
fi

# Auto-start AURA OS Autonomous Supervisor (Battery, Wi-Fi, Sensor, Camera Reverse Proxy, Location Sync)
nohup "$DIR/tools/sec_daemon_supervisor.sh" > /tmp/sec_supervisor.log 2>&1 &

# GPU Rendering Pipeline (Switch from host Apple Metal to SwiftShader Software Rendering)
# -gpu host -> -gpu swiftshader_indirect
export AURA_GPU_MODE="${AURA_GPU_MODE:-swiftshader_indirect}"

# Host-side camera HAL & Adreno 750 GPU Interposition
export DYLD_INSERT_LIBRARIES="/Users/ayush/Desktop/HEBB NETWORK/Emulator/tools/libsec_camera_provider.dylib:/Users/ayush/Desktop/HEBB NETWORK/Emulator/tools/libsec_gpu_interposer.dylib${DYLD_INSERT_LIBRARIES:+:$DYLD_INSERT_LIBRARIES}"

# Build or run AURA OS GUI
BINARY="target/release/aura-gui"

if [ -f "$BINARY" ]; then
    echo "✨ Launching AURA OS..."
    exec "$BINARY"
else
    echo "🔨 Building AURA OS for macOS (Release Mode)..."
    cargo build --release --bin aura-gui
    echo "✨ Launching AURA OS..."
    exec "$BINARY"
fi
