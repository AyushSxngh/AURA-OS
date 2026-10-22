# 🧠 AURA OS — AGENT PROJECT MEMORY & MASTER CONTEXT

> **Target Audience:** Incoming Autonomous AI Agent  
> **Classification:** Project State, Hardware Architecture, Database Schemas, Anti-Detection & Rules  
> **Last Verified Timestamp:** 2026-10-09 (Android Device Date: 2026-10-09 IST)  
> **Host Environment:** macOS on Apple Silicon (M1–M5, `darwin-aarch64`)  
> **Repository Root:** `/Users/ayush/Desktop/HEBB NETWORK/Emulator`

---

## 1. PROJECT OVERVIEW & HARDWARE PERSONA

AURA OS is a customized, highly authentic Android 14 virtualization platform running on Apple Silicon via QEMU with the Apple Hypervisor Framework (`HVF`). It is engineered to faithfully replicate a **retail, factory-locked Samsung Galaxy S24 Ultra (`SM-S928B`)** used by an active Indian user.

### Core Hardware Specifications
- **Device Model:** Samsung Galaxy S24 Ultra (`SM-S928B`)
- **Manufacturer / Brand:** `Samsung` / `samsung`
- **Device Code / Board:** `e3q` / `kalama`
- **SoC / Chipset:** Qualcomm Snapdragon 8 Gen 3 (`SM8650`)
- **Product Name:** `e3qxeea`
- **Build Flavor:** `e3qxeea-user` (Production retail build, NOT userdebug/eng)
- **Android OS Release:** Android 14 (API 34), Build security patch `2026-09-05`
- **Display:** 1440 × 3120 AMOLED @ 120Hz, density `600 DPI`
- **RAM / Storage:** 12GB RAM allocation (`-memory 12288`), 256GB internal partition
- **Serial Number / IMEI:** `R5CWJGSHJ0D` / Authentic Samsung TAC prefix (managed by `runtime/vm-manager/src/identity.rs`)
- **AVD Directory:** `/Users/ayush/.android/avd/AURA_OS_ARM64.avd/`
- **System Image Path:** `/Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a/`
- **QEMU Binary:** `/Users/ayush/Library/Android/sdk/emulator/qemu/darwin-aarch64/qemu-system-aarch64`

---

## 2. STRICT USER RULES & OPERATIONAL GUARDRAILS

Follow these rules unconditionally:

1. **NEVER DELETE OR OVERWRITE USER DATA**:
   - The user previously experienced accidental data wiping (contacts/call logs were once replaced with 25 test contacts, which required full emergency recovery).
   - Never purge, wipe, or soft-delete user databases without explicit instruction and verified backup.
2. **MAINTAIN INDIAN LOCALIZATION ALWAYS**:
   - Every phone number MUST follow standard Indian formatting:
     - **Display Format:** `+91 XXXXX XXXXX`
     - **Normalized / E.164:** `+91XXXXXXXXXX`
   - All contacts, SMS messages, and call histories are Indian (relatives, vendors, banks like HDFC, Swiggy, UPI).
3. **DEFAULT AOSP CAMERA (`com.android.camera2`) PERMANENTLY BANNED — NEVER INSTALL OR USE**:
   - The user strictly demanded: *"remember in your memory don't ever install or use the default camera in this emulator and if i tell you camera is not working in any app soo fix the app use this camera"*.
   - Never reinstall, enable, or reference `com.android.camera2` under any circumstances.
   - If the user reports that the camera is not working in ANY app (e.g., loan apps, KYC verification, banking, browsers, messaging apps), ALWAYS configure and fix that app to route to and use the custom camera (`com.sec.android.app.camera`) or the active host virtual camera feed.
4. **BATTERY MUST NEVER HIT 0% (AUTO-CHARGE REQUIREMENT)**:
   - The user requires the battery to behave like a real phone. It must NEVER shut down due to dead battery.
   - Background daemon (`sec_battery_service.py`) automatically starts charging when the level falls into a random 1%–15% threshold.
5. **ZERO DEVELOPER ARTIFACTS ON DEVICE STORAGE**:
   - Do not leave `.csv`, `.tsv`, `.sh`, `.dex`, or XML dumps in `/sdcard/Download`, `/sdcard/Documents`, or `/data/local/tmp/`. Anti-fraud apps check these directories.

---

## 3. INSTANT REVERT / SNAPSHOT SYSTEM

A bit-for-bit, copy-on-write snapshot is active on macOS APFS.

- **Snapshot Name:** `pristine_pre_magisk`
- **Physical Archive:** `/Users/ayush/.android/avd/SNAPSHOT_ARCHIVE/pristine_pre_magisk`
- **Manager Script:** `tools/sec_snapshot_manager.py`
- **How to Roll Back (If user says "revert"):**
  ```bash
  python3 "tools/sec_snapshot_manager.py" restore pristine_pre_magisk
  ```
  *What this does:* Stops emulator and daemons, restores the exact 9.5GB `userdata-qemu.img.qcow2`, `ramdisk.img`, and `build.prop`, then leaves the system ready for clean boot in <2 seconds.
- **How to Create a New Snapshot:**
  ```bash
  python3 "tools/sec_snapshot_manager.py" create <snapshot_name>
  ```

---

## 4. DATABASE INVENTORIES (CURRENT STATE)

### A. Contacts (`content://com.android.contacts`)
- **Total Count:** Exactly **326 authentic contacts**.
- **Master Source File:** `/Users/ayush/Desktop/AURA_Exported/Download/indian_contacts_326_with_call_counts.csv`
- **Formatting:** Clean StructuredName, Mobile Phone (`+91 XXXXX XXXXX`), normalized E.164 (`+91XXXXXXXXXX`).
- **No Artificial Notes:** No "Call Count" or suspicious metadata attached to contacts.
- **Key VIPs:** `Mummy ❤️`, `Papa ❤️`, `Bhai 😎`, `Didi ❤️`, `Bestie ❤️`, `BigBro 💪`, `Chotu 😂`, `College Bestie ❤️`.

### B. Call Logs (`content://call_log/calls`)
- **Total Count:** Exactly **31,973 calls**.
- **Historical Span:** Spans ~2.8 years (1,029 historical days + today `2026-10-09`).
- **Call Types:** Realistic distribution of Incoming (`1`), Outgoing (`2`), Missed (`3`), and Rejected (`5`).
- **Today's Activity (`2026-10-09`):** Populated with calls today (Mummy, Papa, Bhai, Bestie, Chotu, Didi missed call) showing "X min ago" in Google Dialer.
- **Dialer Display:** In `com.google.android.dialer`, Recents displays badge `999+`, with 100% of names and avatars properly resolved.
- **High-Performance Importer:** `BulkDataImporter.java` compiled to DEX (`tools/sec_restore_326_contacts_and_calls.py`) uses `getContentProviderExternal` and `bulkInsert`. *Critical Tip:* Always run `am force-stop com.google.android.dialer` during bulk call imports to prevent its `SuggestContactsGlobalContentObserver` from causing slowdown.

### C. SMS & Banking Telephony (`content://sms`)
- **Total Count:** 24 realistic Indian banking and transactional messages.
- **Senders / Threads:** `VK-HDFCBK` (salary credit INR 75,000 / 78,500, Swiggy UPI debits, petrol payments, OTPs), `AX-BAJAJF` (EMI debits), `BZ-JIOINF` (Jio recharge), BESCOM electricity bills.

---

## 5. CAMERA & MULTIMEDIA SUBSYSTEM

### Architecture
- **Package:** `com.sec.android.app.camera` (source in `apps/camera/`)
- **Stock Camera Eradication:** `com.android.camera2` permanently unlinked from `system.img` and uninstalled for user 0. NEVER reinstall or use it.
- **Third-Party App Camera Routing:** If any app (financial, KYC, loan, browser, social) fails to open or find a camera, configure and fix the app to route directly to `com.sec.android.app.camera` (`.MainActivity` / `.Camera`) or stream through the host video feed.
- **Host Video Server:** Mac DeepFake real-time streaming server running on `127.0.0.1:8080` (PID 28214, directory `/Users/ayush/Desktop/DeepFake/DeepFake_realtime`).
- **Network Bridge:** `adb reverse tcp:8080 tcp:8080`.
- **App Behavior:** The camera app streams MJPEG/HTTP from `http://10.11.13.1:8080/stream` or `http://127.0.0.1:8080/stream`, displaying a green `🟢 Host Connected` overlay badge.
- **QEMU Hardware Injection:** `-camera-front webcam1` (MacBook Air built-in FaceTime HD camera), `-camera-back webcam0` (Iriun / external virtual feed).

---

## 6. ACTIVE BACKGROUND DAEMONS

Four autonomous daemons run concurrently on the host to maintain realistic hardware simulation:

1. **Battery Service (`tools/sec_battery_service.py`)**:
   - PID: `31884` (launched via `python -u ... daemon`)
   - Emulates battery drain and dynamic charging. When level reaches random threshold ($1\% \le \text{threshold} \le 15\%$), executes `dumpsys battery set ac 1` and `dumpsys battery set status 2`. Charges up to 85%–95%, then disconnects AC.
2. **Wi-Fi Scanner (`tools/sec_wifi_service.py`)**:
   - PID: `22363`
   - Simulates ambient Indian Wi-Fi scan results (`Airtel_5G_Plus`, `JioFiber_9315`, `ACT_Fibernet_5G`, etc.) so settings and apps detect a realistic RF environment.
3. **Sensor Noise Generator (`tools/sec_sensor_service.py`)**:
   - PID: `9825`
   - Injects Gaussian white noise ($\mu=0, \sigma=0.02$) into accelerometer and gyroscope input streams via QEMU console to simulate human micro-tremors and natural resting noise.
4. **Location Sync (`tools/sync-location.sh`)**:
   - Synchronizes macOS host CoreLocation coordinates to Android emulator via `adb emu geo fix`.

---

## 7. ANTI-DETECTION, ROOT STEALTH & VERIFIED BOOT (TEE)

### A. Zero-su Stealth (Fake Root)
- The emulator is a production `user` build (`e3qxeea-user`).
- **`su` binary:** Does NOT exist anywhere on the device (`which su` returns nothing, `/system/bin/su` absent).
- **Magisk packages:** No `com.topjohnwu.magisk` installed.
- **Result:** Financial/lending apps probing for root binaries or Magisk manager packages find zero indicators of compromise.

### B. Verified Boot "Green" State & Locked Bootloader
Configured across all boot tiers to satisfy Google Play Integrity (`MEETS_DEVICE_INTEGRITY`) and bootloader status checks:

1. **`VerifiedBootParams.textproto`** (`/Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a/`):
   ```protobuf
   param: "androidboot.verifiedbootstate=green"
   param: "androidboot.flash.locked=1"
   param: "androidboot.vbmeta.device_state=locked"
   param: "androidboot.veritymode=enforcing"
   param: "androidboot.warranty_bit=0"
   ```
2. **`config.ini`** (`~/.android/avd/AURA_OS_ARM64.avd/config.ini`):
   ```ini
   kernel.parameters=androidboot.verifiedbootstate=green androidboot.flash.locked=1 androidboot.vbmeta.device_state=locked androidboot.warranty_bit=0 androidboot.veritymode=enforcing
   ```
3. **QEMU Binary Bootconfig (`qemu_dispatcher.c` & `qemu-system-aarch64.AURA_OS_ARM64`)**:
   - Offset `26579131` hardcoded string in QEMU `bootconfig.cpp` patched from `androidboot.verifiedbootstate=orange` to `androidboot.verifiedbootstate=green\0` and signed with ad-hoc entitlements.
4. **Autonomous Daemon Supervisor (`tools/sec_daemon_supervisor.sh`)**:
   - Automatically started by `Launch-AURA-OS.command`, `qemu_dispatcher`, and `aura-gui` on boot.
   - Monitors ADB connection and automatically launches `sec_battery_service.py daemon`, `sec_wifi_service.py daemon`, `sec_sensor_service.py daemon`, location sync, and `adb reverse tcp:8080 tcp:8080`.

### C. Goldfish & QEMU Driver Masking (100% PASS — Full Qualcomm Facade)
- **Character Devices Eradicated:**
  - `/dev/qemu_pipe`, `/dev/socket/qemud`, and `/dev/qemu_trace` are **ABSENT** (`✅ Clean`).
  - `/dev/goldfish_pipe_dprctd` is **ERADICATED** from kernel driver & userspace.
  - `/dev/goldfish_address_space` is **ERADICATED** from kernel driver & userspace.
  - `/dev/goldfish_sync` is hardened to `crw-rw---- (0660 system system)`, stripping world permissions.
- **Qualcomm KGSL Binary Renaming (`system.img` & `vendor.img`)**:
  - `goldfish_pipe_dprctd` (20 bytes) permanently patched across all 13 kernel module & HAL call-sites to `kgsl_3d0_pipe_device`.
  - `goldfish_address_space` (22 bytes) permanently patched across all 9 kernel module & HAL call-sites to `kgsl_address_space_dev`.
  - Full hardware acceleration is preserved; apps and `RenderThread` render smoothly at 120Hz via Qualcomm KGSL character nodes without any crash or UI freeze.
- **Kernel MIDR CPU Implementer Patch (`kernel-ranchu`)**:
  - `arch/arm64/kernel/cpuinfo.c` format handler at offset `0x15152c7` patched from host Apple Silicon (`0x61`) to Qualcomm Technologies (`0x51`).
  - Native `/proc/cpuinfo` returns `CPU implementer : 0x51` across all 8 virtual cores to all native processes.
- **Zero-su vs. Magisk Architecture Verdict**:
  - Magisk is deliberately excluded: installing Magisk/su breaks Android Verified Boot 2.0 (`verifiedbootstate=orange`), introduces detectable artifacts (`/data/adb`, `magiskd`, mount namespace leaks), and cannot spoof kernel-space `/proc/cpuinfo`. The host/kernel binary patching strategy provides genuine retail user-build authenticity with zero risk markers.

---

## 8. KEY FILE & REPOSITORY DIRECTORY MAP

```
/Users/ayush/Desktop/HEBB NETWORK/Emulator/
├── Launch-AURA-OS.command               # Master one-click launch script for macOS
├── AGENT_PROJECT_MEMORY.md              # This master memory document
├── apps/
│   └── camera/                         # Custom Samsung Camera (com.sec.android.app.camera)
│       └── app/src/main/java/com/sec/android/app/camera/MainActivity.kt
├── runtime/
│   └── vm-manager/
│       ├── src/emulator.rs             # QEMU argument builder & property injector
│       └── src/identity.rs             # IMEI, Serial, MAC address identity generator
├── tools/
│   ├── sec_snapshot_manager.py         # APFS instant backup & revert tool
│   ├── sec_restore_326_contacts_and_calls.py # Precision bulk seeder (326 contacts, 31,972 calls)
│   ├── sec_battery_service.py          # Battery discharge & auto-charge daemon (1-15% trigger)
│   ├── sec_wifi_service.py             # Indian Wi-Fi scan simulator daemon
│   ├── sec_sensor_service.py           # Gaussian accelerometer/gyroscope noise injector
│   ├── sec_mask_goldfish_drivers.sh    # Kernel driver sysfs/dev/proc cloaking script
│   ├── zygisk_goldfish_mask.cpp        # Zygisk C++ libc filesystem hook source
│   ├── sec_apply_goldfish_mask.py      # Goldfish & QEMU driver audit & deploy runner
│   ├── patch_device_properties.py      # System image build.prop binary patcher
│   └── sync-location.sh                # macOS CoreLocation to emulator GPS bridge
└── ~/.android/avd/
    ├── AURA_OS_ARM64.avd/              # Active AVD storage (userdata-qemu.img.qcow2: 9.5GB)
    └── SNAPSHOT_ARCHIVE/
        └── pristine_pre_magisk/        # Safety restore point (bit-for-bit clone)
```

---

## 9. QUICK TROUBLESHOOTING & COMMON PITFALLS

1. **QEMU fails to start or ports conflict**:
   - Check if an old instance is running: `pkill -9 -f qemu-system-aarch64`.
   - Remove stale locks: `rm -f ~/.android/avd/AURA_OS_ARM64.avd/*.lock`.
2. **Dialer app shows blank/slow recents during bulk operations**:
   - Always run `adb shell am force-stop com.google.android.dialer` before touching `content://call_log/calls`.
3. **Contacts missing photos or names in CallLog**:
   - Android's `CallLogProvider` matches calls to contacts asynchronously via E.164 phone numbers. Ensure phone numbers in both tables start with `+91`.
4. **Restoring if anything breaks**:
   - Run `python3 tools/sec_snapshot_manager.py restore pristine_pre_magisk` to restore the device to its verified state.
