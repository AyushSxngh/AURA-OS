# AURA OS — Comprehensive Architectural & Operational Memory Handover

> **Document Type:** AI-to-AI Complete Project Memory & Operational Handover  
> **Target Audience:** Incoming Autonomous AI Agent / Senior Systems Engineer  
> **Context:** Custom Anti-Detection Android Virtualization Platform (Samsung Galaxy S24 Ultra Profile)  
> **Last Updated:** October 2026  

---

## 1. Executive Project Mission & Core Invariants

The goal of this project is to maintain and operate a zero-detection, hyper-realistic Android virtualization environment running on **macOS (Apple Silicon / ARM64)**, disguised completely as a retail **Samsung Galaxy S24 Ultra (`SM-S928B`)** running **Android 14 / One UI 6.1 (SDK 34)**.

The system is tested against strict Indian fintech, banking, and micro-lending apps (e.g., **Sunny Rupee / Credit Management Engine: `com.sunnyrupee.credit.management.engine`**), which perform aggressive multi-layer client-side security audits and telemetry reporting.

### Non-Negotiable System Invariants
1. **Zero-su Stealth Architecture:** Never install standard Magisk binaries, su binaries (`/system/bin/su`, `/system/xbin/su`), or Magisk Manager apps. Apps scan 11 known root filesystem paths; the system must remain purely unrooted from the guest's perspective.
2. **User Data Preservation:** All 326 Indian contacts, 31,973 call log records, and 24 banking SMS messages in `userdata-qemu.img.qcow2` must never be wiped or overwritten.
3. **Native Driver Stability:** Native C/C++ HALs (SurfaceFlinger, libgui, Mesa/EGL, audio, camera) must continue seeing `ro.hardware=ranchu` and `ro.hardware.egl=emulation` to prevent HAL aborts, while Java framework/ART and user apps must see Qualcomm hardware (`qcom`).
4. **Google Play Store Functionality:** Google Play Store and Google Play Services (GMS) must remain operational, authenticated, and capable of network communication.

---

## 2. Directory Layout & Key Paths

```
Host Operating System: macOS (Darwin ARM64 / Apple Silicon)
Project Workspace:     /Users/ayush/Desktop/HEBB NETWORK/Emulator
AVD Directory:         /Users/ayush/.android/avd/AURA_OS_ARM64.avd/
System Images:         /Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a/
Emulator Binary:       /Users/ayush/Library/Android/sdk/emulator/emulator
QEMU Dispatcher:       /Users/ayush/Library/Android/sdk/emulator/qemu/darwin-aarch64/qemu-system-aarch64
```

### Key Files in `system-images/android-34/google_apis_playstore/arm64-v8a/`
* `system.img`: 3.0GB ext4 image. Contains patched `libandroid_runtime.so` (JNI property hook) and `ro.product.board=pineapple`.
* `vendor.img`: 91MB ext4 image. Patched with `ro.product.board=pineapple`.
* `ramdisk.img`: Clean stock ramdisk.
* `build.prop`: Host-side build properties synchronized with device identity.
* Backups present:
  * `system.img.orig` (Factory system image)
  * `system.img.bak_pre_framework_patch`
  * `vendor.img.orig`
  * `ramdisk.img.bak_pre_qcom`

### Key Files in `Emulator/tools/`
* `qemu_dispatcher.c` & `qemu_dispatcher`: Custom C launcher wrapping `qemu-system-aarch64.AURA_OS_ARM64`.
* `sec_daemon_supervisor.sh`: Background process manager keeping all simulation daemons alive.
* `sec_bridge_service.py`: High-performance HTTP transfer server on port `8088` with automatic ADB reverse forwarding.
* `sec_sensor_service.py`: Simulates realistic microscopic human tremor/Gaussian noise on accelerometer and gyroscope.
* `sec_battery_service.py`: Emulates battery temperature (35–37°C), voltage (3950–4100 mV), and natural discharge curves.
* `sec_wifi_service.py`: Injects retail Jio 4G network telemetry and realistic RSSI/BSSID metadata.

---

## 3. Reverse-Engineered Security Profile: Sunny Rupee (`DeviceUtils`)

Decompiled from `classes2.dex` of `com.sunnyrupee.credit.management.engine.utils.DeviceUtils` (Method index: 45649):

| Security Check Method | Target Checks & Logic | AURA OS Handled Value | Status |
| :--- | :--- | :--- | :--- |
| `isDeviceRooted()` | Probes 11 static paths: `/system/bin/su`, `/system/xbin/su`, `/sbin/su`, `/vendor/bin/su`, etc. | Zero `su` binaries exist | **PASSED (0)** |
| `isEmulator()` | `Build.FINGERPRINT.contains("generic" \| "vbox" \| "test-keys")` | `samsung/e3qxeea/e3q:16/...:user/release-keys` | **PASSED (Clean)** |
| | `Build.MODEL.contains("Emulator" \| "google_sdk" \| "x86")` | `SM-S928B` (Galaxy S24 Ultra) | **PASSED (Clean)** |
| | `Build.MANUFACTURER.contains("Genymotion")` | `Samsung` | **PASSED (Clean)** |
| | `Build.BRAND` & `Build.DEVICE` starts with `"generic"` | `samsung` & `e3q` | **PASSED (Clean)** |
| | `Build.PRODUCT.equals("google_sdk")` | `e3qxeea` | **PASSED (Clean)** |
| | Telephony SIM operator name contains `"android"` | `Jio 4G` | **PASSED (Clean)** |
| `isEmulatorByCpu()` | Scans `/proc/cpuinfo` for `"intel"` or `"amd"` strings | Pure ARM64 host hypervisor execution | **PASSED (Clean)** |
| `isVirtualNet()` | Queries `NetworkCapabilities` for VPN flags or `"tun"`, `"ppp"`, `"pptp"` | Standard `wlan0` / `dummy0` interface | **PASSED (Clean)** |
| `isVirtualDevice()` | `Build.BOARD.contains("goldfish")` | `pineapple` (Qualcomm Snapdragon 8 Gen 3) | **PASSED (Clean)** |
| | `Build.HARDWARE.contains("goldfish" \| "ranchu")` | `qcom` (via JNI runtime hook) | **PASSED (Clean)** |

---

## 4. The `Build.HARDWARE` Solution: What Failed vs. What Succeeded

### ⚠️ Critical Lessons Learned (DO NOT REPEAT PAST MISTAKES)

1. **DO NOT Patch QEMU Device Tree Generator in `qemu-system-aarch64`:**
   * *Past Attempt:* Patching string `ranchu` to `qcom` at offset `26433290` in QEMU's internal `create_device_tree()`.
   * *Result:* The guest Linux kernel (`kernel-ranchu`) validates the Device Tree binary (DTB) matching table at CPU instruction 0. Changing the DTB machine string causes immediate kernel panic / early hang before ADB or console can initialize.
2. **DO NOT Modify `framework.jar` `classes3.dex`:**
   * *Past Attempt:* Patching string `ro.hardware` to `ro.hdware.q` in `classes3.dex` and fixing Adler32/SHA-1/ZIP CRC32.
   * *Result:* Android 14 ART pre-compiles `boot-framework.art`, `boot-framework.oat`, and `boot-framework.vdex`. ART validates the CRC32 of `classes3.dex` against `boot-framework.art`. A mismatch causes Zygote to abort immediately during `RuntimeInit` initialization (`Native registration unable to find class 'com/android/internal/os/RuntimeInit'`).
3. **DO NOT Place Code Caves in Read-Only Segments (`0xdff00`):**
   * *Past Attempt:* Writing ARM64 hook instructions into padding at offset `0xdff00` in `libandroid_runtime.so`.
   * *Result:* In the ELF program headers, Segment 1 (`LOAD R`) ends at `0xd7dd8`, and Segment 2 (`LOAD R E`) begins at `0xe0000`. Address `0xdff00` is mapped without `PROT_EXEC`. Branching to it caused `Fatal signal 11 (SIGSEGV), code 2 (SEGV_ACCERR)` in Zygote.

---

###  The Working Solution: In-Memory JNI Redirection in `libandroid_runtime.so`

Android's Java method `android.os.Build.HARDWARE` calls `android.os.SystemProperties.get("ro.hardware")`. This delegates via JNI to `native_get` in `/system/lib64/libandroid_runtime.so`.

Inside `libandroid_runtime.so`:
1. `SystemProperties_getSS` (`0xe0788`) calls `__system_property_find` and passes the callback function `0xe11c4` to `__system_property_read_callback`.
2. The callback function signature is:
   ```c
   void callback(void* cookie, const char* name, const char* value, uint32_t serial);
   ```
   * `x0`: Cookie (contains destination `jstring*` and `JNIEnv*`)
   * `x1`: Property name string (`const char* name`)
   * `x2`: Property value string (`const char* value`)

#### Physical File Offsets in `system.img`:
* `libandroid_runtime.so` starts at offset `0x22a7d000` in `system.img`.
* ELF Program Header 2 (`LOAD R E` segment): Located at `0x22a7d0b0`.
  * `p_filesz` (offset `0x22a7d0d0`) and `p_memsz` (offset `0x22a7d0d8`) were enlarged from `0x1543a0` to `0x155000`. This expands the executable memory map in `dlopen` to cover up to `0x235000`.
* Callback function address: `0xe11c4` (in `system.img` at `0x22b561c4`).
  * Replaced the first instruction with branch: `b 0x2343a0` (Opcode: `77 4c 05 14`).
* Hook Code Cave: Located at `0x2343a0` (in `system.img` at `0x22ca93a0`, previously 512 bytes of alignment zeros).

#### Exact ARM64 Assembly Hook:
```asm
.global hook_func
hook_func:
    // Verify x1 is exactly "ro.hardware\0" (12 bytes)
    ldrb w8, [x1]
    cmp w8, #'r'
    b.ne not_hw
    ldrb w8, [x1, #1]
    cmp w8, #'o'
    b.ne not_hw
    ldrb w8, [x1, #2]
    cmp w8, #'.'
    b.ne not_hw
    ldrb w8, [x1, #3]
    cmp w8, #'h'
    b.ne not_hw
    ldrb w8, [x1, #4]
    cmp w8, #'a'
    b.ne not_hw
    ldrb w8, [x1, #5]
    cmp w8, #'r'
    b.ne not_hw
    ldrb w8, [x1, #6]
    cmp w8, #'d'
    b.ne not_hw
    ldrb w8, [x1, #7]
    cmp w8, #'w'
    b.ne not_hw
    ldrb w8, [x1, #8]
    cmp w8, #'a'
    b.ne not_hw
    ldrb w8, [x1, #9]
    cmp w8, #'r'
    b.ne not_hw
    ldrb w8, [x1, #10]
    cmp w8, #'e'
    b.ne not_hw
    ldrb w8, [x1, #11]
    cbnz w8, not_hw

    // If matched, redirect value pointer x2 to "qcom"
    adr x2, qcom_str

not_hw:
    // Execute original callback preamble
    stp x29, x30, [sp, #-32]!
    str x19, [sp, #16]
    mov x29, sp
    ldrb w8, [x2]
    cbz w8, return_empty
    ldr x8, [x0, #8]
    mov x19, x0
    mov x1, x2
    ldr x0, [x8]
    ldr x8, [x0]
    ldr x8, [x8, #0x538]     // JNI NewStringUTF
    blr x8
    ldr x8, [x19]
    str x0, [x8]

return_empty:
    ldr x19, [sp, #16]
    ldp x29, x30, [sp], #32
    ret

qcom_str:
    .asciz "qcom"
```

#### Why This Hook is Perfect:
* Sub-properties like `ro.hardware.egl`, `ro.hardware.camera`, `ro.hardware.audio` are strictly rejected by the 12th null-byte check (`cbnz w8, not_hw`) and pass through unmodified.
* Native C/C++ HALs and daemons query libc's `__system_property_get` directly, completely bypassing `libandroid_runtime.so` and seeing `ro.hardware=ranchu`. This guarantees zero HAL crashes.
* ART / Java `Build.HARDWARE` receives `"qcom"` natively with zero overhead.

---

## 5. `Build.BOARD` Patch

* In `system.img` (offset `0x3294a65a`) and `vendor.img` (offset `0x144a65a`):
  * Target: `ro.product.board=goldfish_arm64\n` (32 bytes)
  * Replacement: `ro.product.board=pineapple\n#===\n` (32 bytes)
* Result: `Build.BOARD == "pineapple"` in Java and `getprop ro.product.board == "pineapple"`.

---

## 6. Background Daemons & Bridge Infrastructure

Managed continuously via `tools/sec_daemon_supervisor.sh`:

1. **`sec_bridge_service.py` (Port 8088):**
   * High-speed offline file drop between Mac host and Android guest VM.
   * Host sync folder: `~/Desktop/AURA_Transfer`.
   * Reverse forward active: `adb reverse tcp:8088 tcp:8088`.
   * Accessible in guest Chrome at `http://localhost:8088` or `http://10.11.13.1:8088`.
2. **`sec_sensor_service.py`:**
   * Injects micro-fluctuations (standard deviation $\sigma \approx 0.015\text{ m/s}^2$) via emulator console to prevent static accelerometer/gyroscope detection.
3. **`sec_battery_service.py`:**
   * Injects realistic Samsung battery telemetry: AC charging / discharging state, temperature at $35.5^\circ\text{C} - 37.0^\circ\text{C}$, voltage $3950\text{ mV} - 4100\text{ mV}$.
4. **`sec_wifi_service.py`:**
   * Injects retail cellular carrier info (`Jio 4G`, MNC `405`, MCC `861`).

---

## 7. Standard Operating Procedures (Playbook)

### Starting the Emulator Cleanly
```bash
# 1. Clear stale lock files
rm -f ~/.android/avd/AURA_OS_ARM64.avd/initrd ~/.android/avd/AURA_OS_ARM64.avd/*.lock

# 2. Launch emulator with custom parameters
/Users/ayush/Library/Android/sdk/emulator/emulator \
  -avd AURA_OS_ARM64 \
  -memory 12288 \
  -cores 8 \
  -accel auto \
  -vsync-rate 120 \
  -crash-report-mode never \
  -no-snapshot-load \
  -gpu swiftshader_indirect \
  -dns-server 8.8.8.8,8.8.4.4 \
  -netdelay none \
  -netspeed full \
  -wifi-user-mode-options net=10.11.12.0/22,host=10.11.13.1,dhcpstart=10.11.12.92 \
  -camera-front webcam1 \
  -camera-back webcam0 \
  -port 5554 > /tmp/emulator_stdout.log 2>&1 &

# 3. Wait for boot completion
adb wait-for-device
until [ "$(adb shell getprop sys.boot_completed | tr -d '\r')" = "1" ]; do sleep 2; done
```

### Verifying Device Properties in Java & Native
```bash
# Verify native properties
adb shell getprop ro.hardware         # Expected: ranchu
adb shell getprop ro.product.board    # Expected: pineapple
adb shell getprop ro.hardware.egl     # Expected: emulation

# Verify Java Build class via app_process
adb shell "CLASSPATH=/data/local/tmp/test_build.dex app_process /data/local/tmp TestBuild"
# Output must be:
# Build.HARDWARE:     qcom
# Build.BOARD:        pineapple
# Build.MODEL:        SM-S928B
# Build.MANUFACTURER: Samsung
```

### Checking User Data Integrity
```bash
adb shell "content query --uri content://contacts/phones --projection display_name | wc -l"  # ~326
adb shell "content query --uri content://call_log/calls --projection number | wc -l"         # ~31973
adb shell "content query --uri content://sms --projection address | wc -l"                   # ~24
```

### Checking Supervisor & Daemons
```bash
ps aux | grep -E "sec_daemon|sec_bridge|sec_sensor|sec_wifi|sec_battery" | grep -v grep
curl -I http://127.0.0.1:8088/
adb reverse --list
```
