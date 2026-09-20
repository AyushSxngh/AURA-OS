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
