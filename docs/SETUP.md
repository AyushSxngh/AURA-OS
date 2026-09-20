# AURA OS — Environment Setup & Diagnostic Guide

This guide details host requirements, dependency installation, and diagnostic procedures for building and running **AURA OS**.

---

## 1. Prerequisites

### Windows x86-64
1. **Windows 10/11 64-bit** with Hardware Virtualization enabled in BIOS/UEFI.
2. **Windows Hypervisor Platform (WHPX)** enabled in Windows Features.
3. **Android SDK & Platform Tools**:
   - `ANDROID_HOME` or default path `%LOCALAPPDATA%\Android\Sdk`.
   - `platform-tools` (adb version 1.0.41+).
   - `emulator` (version 36.0+).
4. **Rust Toolchain**: Rust 1.80+ (`rustc`, `cargo`).
5. **JDK**: OpenJDK 17 or 21 (bundled with Android Studio at `C:\Program Files\Android\Android Studio\jbr`).

### macOS Apple Silicon
1. **macOS 14+ (ARM64)**.
2. **Android SDK** with arm64-v8a system images.
3. **Rust Toolchain** (`aarch64-apple-darwin`).

---

## 2. Environment Audit & Diagnostics

Run the AURA OS platform diagnostic CLI:

```bash
# Display full host OS, CPU, acceleration, and toolchain resolution
cargo run --bin aura-cli -- info

# Run actionable environment diagnostics
cargo run --bin aura-cli -- doctor

# List connected devices and configured AVDs
cargo run --bin aura-cli -- devices
```
