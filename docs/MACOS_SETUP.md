# AURA OS on macOS (Apple Silicon M1 / M2 / M3 / M4 / M5)

<div align="center">

![AURA OS Logo](../launcher/ui/assets/icon.png)

**Native ARM64 • Apple Hypervisor Framework (HVF) • 120 Hz ProMotion • Zero Binary Translation**

</div>

---

## 🌟 Why AURA OS is Exceptional on Apple Silicon

Running Android on an **Apple Silicon Mac (M1–M5)** offers a major architectural advantage over traditional x86 PCs:
- **Native Instruction Set**: 99% of Android apps and games are compiled for `arm64-v8a`. Your Mac's M-series CPU is also **ARM64**. This means Android instructions run **directly on host silicon** with zero emulator translation overhead or lag!
- **Apple Hypervisor Framework (HVF)**: Uses macOS's native in-kernel virtualization APIs (`-accel hvf`) with no third-party kernel drivers required.
- **Unified Memory Performance**: With 16 GB of high-bandwidth unified RAM (~100–150 GB/s), Android VM memory access is near-instantaneous.
- **Fanless & Silent**: Runs completely cool and silent on the MacBook Air without throttling or battery drain.
- **Liquid Retina Display**: Android 14 UI renders with crystal-clear high-DPI scaling.

---

## 📋 Prerequisites

1. **MacBook Air / Pro / Mac Mini / iMac** with Apple Silicon (M1, M2, M3, M4, or M5) or Intel Core.
2. **macOS 12 (Monterey)** or higher (Ventura, Sonoma, Sequoia).
3. **Android Studio for Mac** (Apple Silicon `.dmg`):
   - Download from: [developer.android.com/studio](https://developer.android.com/studio)
   - During setup, install the **Android SDK**, **Android Emulator**, and **Android 14 (API 34) ARM64 Google Play system image**.
4. **Rust Toolchain**:
   - Open Terminal and install Rust via rustup:
     ```bash
     curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
     ```

---

## 🚀 Quick Setup (Automated)

Clone the repository and run the automated setup script:

```bash
git clone https://github.com/AyushSxngh/AURA-OS.git
cd AURA-OS

# Make scripts executable
chmod +x Launch-AURA-OS.command tools/setup-mac.sh

# Run automated setup (checks SDK, downloads ARM64 image, compiles release binary)
./tools/setup-mac.sh
```

---

## 🕹 Launching AURA OS

You can launch AURA OS in two ways:

### Option 1: Double-Click Finder Launcher
1. In macOS Finder, navigate to the `AURA-OS` folder.
2. Double-click **`Launch-AURA-OS.command`**.
3. The sleek glassmorphic AURA OS dashboard will appear with native Apple Silicon detection!

### Option 2: Terminal
```bash
cargo run --release --bin aura-gui
```

---

## ⚙️ Recommended Configuration for 16 GB Mac

When running on a 16 GB MacBook Air, the recommended settings are:
* **RAM Allocation**: 6,144 MB – 8,192 MB (leaves 8–10 GB for macOS).
* **CPU Cores**: 4 to 6 Cores.
* **Display**: 1920x1080 Landscape @ 240 DPI.
* **Refresh Rate**: 60 Hz / 120 Hz ProMotion.
* **Storage**: 32 GB Virtual Disk (uses APFS sparse allocation, only takes space when filled).
