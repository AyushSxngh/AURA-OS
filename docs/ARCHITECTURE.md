# AURA OS — Platform Architecture Document

AURA OS is a custom Android virtualization platform designed for low-latency desktop execution, broad APK compatibility, modularity, and custom Android guest user experiences.

---

## 1. High-Level Architecture Overview

```text
+-----------------------------------------------------------------------+
|                         AURA Desktop Launcher                         |
|  (Cross-platform Desktop UI / CLI Engine — Rust & Native Integrations)|
+-----------------------------------++----------------------------------+
                                    ||
                                    \/
+-----------------------------------------------------------------------+
|                         AURA Runtime Core                             |
|  +---------------------------+   +---------------------------------+  |
|  |   AuraVmManager (QEMU/Emu)|   |   AuraAdbClient (ADB Bridge)    |  |
|  +---------------------------+   +---------------------------------+  |
+-----------------------------------++----------------------------------+
                                    ||
                                    \/
+-----------------------------------------------------------------------+
|                    Hardware Virtualization Hypervisor                 |
|  - Windows (x86-64): WHPX (Windows Hypervisor Platform)               |
|  - macOS (Apple Silicon): HVF (Hypervisor.framework)                  |
|  - Linux (x86-64/ARM64): KVM (Kernel Virtual Machine)                 |
+-----------------------------------++----------------------------------+
                                    ||
                                    \/
+-----------------------------------------------------------------------+
|                   Custom AOSP System Guest Image                      |
|  - AURA Custom System Framework & Resource Overlays                   |
|  - Custom System Apps (Launcher, Camera, Gallery, Settings)           |
+-----------------------------------------------------------------------+
```

---

## 2. Core Subsystems

### 2.1 Launcher (`launcher/`)
* **`launcher/core`**: Native Rust library responsible for platform detection, hardware acceleration capability checks, toolchain resolution (Android SDK, ADB, JDK), and device profile management.
* **`launcher/windows`**: Windows-specific integrations (win32 API wrappers, WHPX detection, desktop windowing).
* **`launcher/macos`**: macOS-specific HVF and Metal graphics integrations.
* **`launcher/ui`**: Desktop GUI and CLI control engine (`aura-cli`).

### 2.2 Runtime (`runtime/`)
* **`runtime/vm-manager`**: Controls QEMU / Android Emulator process launch, graphics pipeline flags (`gfxstream`, `host`, `swiftshader`), boot state polling, and graceful termination.
* **`runtime/device-config`**: Hardware resource profiles (RAM, CPU cores, screen resolution, ABI target, storage).
* **`runtime/adb`**: Direct Rust binding for ADB commands (`install`, `uninstall`, `devices`, `shell`).

### 2.3 Android Guest Image (`android/`) & Applications (`apps/`)
* **`android/aosp-config`**: Custom AOSP system build targets and product configurations.
* **`android/overlays`**: AOSP framework resource overlays for customized system visual identity.
* **`apps/`**: Custom Kotlin APKs for CameraX/Camera2 photo/video capture, Gallery, Custom Desktop Launcher, and System Settings.
