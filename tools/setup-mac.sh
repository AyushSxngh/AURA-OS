#!/usr/bin/env bash
# ==============================================================================
# AURA OS — Automated macOS / Apple Silicon Setup Script
# Configures Android SDK, ARM64 Android 14 Image, and compiles AURA OS
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=========================================================="
echo "      🍎 AURA OS — Apple Silicon Automated Setup         "
echo "=========================================================="
echo ""

# 1. Check Architecture
ARCH=$(uname -m)
echo "Detected Host Architecture: $ARCH"
if [ "$ARCH" = "arm64" ]; then
    echo "✅ Native Apple Silicon detected (M1/M2/M3/M4/M5). Maximum performance enabled."
else
    echo "ℹ️  Intel x86_64 Mac detected."
fi
echo ""

# 2. Check Rust
if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
fi

if ! command -v cargo &> /dev/null; then
    echo "📦 Installing Rust toolchain..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
    echo "✅ Rust installed successfully."
else
    echo "✅ Rust toolchain is ready: $(rustc --version)"
fi
echo ""

# 3. Check / Configure Android SDK
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"

if [ ! -d "$ANDROID_HOME" ]; then
    echo "⚠️  Android SDK not detected at $ANDROID_HOME."
    echo "   Please install Android Studio (Apple Silicon) from https://developer.android.com/studio"
    echo "   or install cmdline-tools via Homebrew:"
    echo "   brew install --cask android-commandlinetools"
    echo ""
else
    echo "✅ Android SDK found at: $ANDROID_HOME"
fi

# 4. Download ARM64 Play Store System Image if sdkmanager is available
SDKMANAGER=""
for CANDIDATE in \
    "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" \
    "$ANDROID_HOME/cmdline-tools/bin/sdkmanager" \
    "$ANDROID_HOME/tools/bin/sdkmanager"; do
    if [ -x "$CANDIDATE" ]; then
        SDKMANAGER="$CANDIDATE"
        break
    fi
done

if [ -n "$SDKMANAGER" ]; then
    echo "📦 Checking Android 14 System Image..."
    if [ "$ARCH" = "arm64" ]; then
        SYS_IMAGE="system-images;android-34;google_apis_playstore;arm64-v8a"
    else
        SYS_IMAGE="system-images;android-34;google_apis_playstore;x86_64"
    fi

    echo "   Ensuring $SYS_IMAGE is installed..."
    yes | "$SDKMANAGER" --licenses > /dev/null 2>&1 || true
    "$SDKMANAGER" "$SYS_IMAGE" "platform-tools" "emulator" || true
    echo "✅ System image check completed."
fi
echo ""

# 5. Build AURA OS
echo "🔨 Compiling AURA OS release binary for $ARCH..."
cargo build --release --workspace

echo ""
echo "=========================================================="
echo "🎉 Setup Complete! You can now run AURA OS on your Mac:"
echo "   ./Launch-AURA-OS.command"
echo "=========================================================="
