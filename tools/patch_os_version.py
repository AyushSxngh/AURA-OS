#!/usr/bin/env python3
"""
AURA OS — Patch Android System Images to Android 16 (API 36) & Security Patch 2026-09-05
Directly patches system.img, vendor.img, and ramdisk.img at the byte level with exact byte preservation.
"""

import os
import subprocess
import sys

SYSDIR = "/Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a"
SYSTEM_IMG = os.path.join(SYSDIR, "system.img")
VENDOR_IMG = os.path.join(SYSDIR, "vendor.img")
RAMDISK_IMG = os.path.join(SYSDIR, "ramdisk.img")
BUILD_PROP = os.path.join(SYSDIR, "build.prop")

def replace_exact(data: bytearray, old_str: bytes, new_str: bytes, desc: str) -> int:
    assert len(old_str) == len(new_str), f"Byte length mismatch for {desc}: {len(old_str)} vs {len(new_str)}"
    count = 0
    start = 0
    while True:
        pos = data.find(old_str, start)
        if pos == -1:
            break
        data[pos:pos + len(old_str)] = new_str
        count += 1
        start = pos + len(new_str)
    print(f"  [{desc}] Replaced {count} occurrence(s)")
    return count

def patch_system_img():
    print(f"📦 Patching {SYSTEM_IMG}...")
    orig_len = os.path.getsize(SYSTEM_IMG)
    with open(SYSTEM_IMG, "rb") as f:
        data = bytearray(f.read())

    # Release version: 14 -> 16
    replace_exact(data, b"ro.build.version.release=14\n", b"ro.build.version.release=16\n", "ro.build.version.release")
    replace_exact(data, b"ro.build.version.release_or_codename=14\n", b"ro.build.version.release_or_codename=16\n", "ro.build.version.release_or_codename")
    replace_exact(data, b"ro.build.version.release_or_preview_display=14\n", b"ro.build.version.release_or_preview_display=16\n", "ro.build.version.release_or_preview_display")

    replace_exact(data, b"ro.system.build.version.release=14\n", b"ro.system.build.version.release=16\n", "ro.system.build.version.release")
    replace_exact(data, b"ro.system.build.version.release_or_codename=14\n", b"ro.system.build.version.release_or_codename=16\n", "ro.system.build.version.release_or_codename")

    replace_exact(data, b"ro.product.build.version.release=14\n", b"ro.product.build.version.release=16\n", "ro.product.build.version.release")
    replace_exact(data, b"ro.product.build.version.release_or_codename=14\n", b"ro.product.build.version.release_or_codename=16\n", "ro.product.build.version.release_or_codename")

    replace_exact(data, b"ro.system_ext.build.version.release=14\n", b"ro.system_ext.build.version.release=16\n", "ro.system_ext.build.version.release")
    replace_exact(data, b"ro.system_ext.build.version.release_or_codename=14\n", b"ro.system_ext.build.version.release_or_codename=16\n", "ro.system_ext.build.version.release_or_codename")

    replace_exact(data, b"ro.odm.build.version.release=14\n", b"ro.odm.build.version.release=16\n", "ro.odm.build.version.release")
    replace_exact(data, b"ro.odm.build.version.release_or_codename=14\n", b"ro.odm.build.version.release_or_codename=16\n", "ro.odm.build.version.release_or_codename")

    replace_exact(data, b"ro.odm_dlkm.build.version.release=14\n", b"ro.odm_dlkm.build.version.release=16\n", "ro.odm_dlkm.build.version.release")
    replace_exact(data, b"ro.odm_dlkm.build.version.release_or_codename=14\n", b"ro.odm_dlkm.build.version.release_or_codename=16\n", "ro.odm_dlkm.build.version.release_or_codename")

    replace_exact(data, b"ro.system_dlkm.build.version.release=14\n", b"ro.system_dlkm.build.version.release=16\n", "ro.system_dlkm.build.version.release")
    replace_exact(data, b"ro.system_dlkm.build.version.release_or_codename=14\n", b"ro.system_dlkm.build.version.release_or_codename=16\n", "ro.system_dlkm.build.version.release_or_codename")

    replace_exact(data, b"ro.vendor.build.version.release=14\n", b"ro.vendor.build.version.release=16\n", "ro.vendor.build.version.release (in sys)")
    replace_exact(data, b"ro.vendor.build.version.release_or_codename=14\n", b"ro.vendor.build.version.release_or_codename=16\n", "ro.vendor.build.version.release_or_codename (in sys)")

    replace_exact(data, b"ro.vendor_dlkm.build.version.release=14\n", b"ro.vendor_dlkm.build.version.release=16\n", "ro.vendor_dlkm.build.version.release (in sys)")
    replace_exact(data, b"ro.vendor_dlkm.build.version.release_or_codename=14\n", b"ro.vendor_dlkm.build.version.release_or_codename=16\n", "ro.vendor_dlkm.build.version.release_or_codename (in sys)")

    # Security patch: 2023-09-05 -> 2026-09-05
    replace_exact(data, b"ro.build.version.security_patch=2023-09-05\n", b"ro.build.version.security_patch=2026-09-05\n", "ro.build.version.security_patch")

    # SDK version: 34 -> 36
    replace_exact(data, b"ro.build.version.sdk=34\n", b"ro.build.version.sdk=36\n", "ro.build.version.sdk")
    replace_exact(data, b"ro.system.build.version.sdk=34\n", b"ro.system.build.version.sdk=36\n", "ro.system.build.version.sdk")
    replace_exact(data, b"ro.product.build.version.sdk=34\n", b"ro.product.build.version.sdk=36\n", "ro.product.build.version.sdk")
    replace_exact(data, b"ro.system_ext.build.version.sdk=34\n", b"ro.system_ext.build.version.sdk=36\n", "ro.system_ext.build.version.sdk")
    replace_exact(data, b"ro.odm.build.version.sdk=34\n", b"ro.odm.build.version.sdk=36\n", "ro.odm.build.version.sdk")
    replace_exact(data, b"ro.odm_dlkm.build.version.sdk=34\n", b"ro.odm_dlkm.build.version.sdk=36\n", "ro.odm_dlkm.build.version.sdk")
    replace_exact(data, b"ro.system_dlkm.build.version.sdk=34\n", b"ro.system_dlkm.build.version.sdk=36\n", "ro.system_dlkm.build.version.sdk")
    replace_exact(data, b"ro.vendor.build.version.sdk=34\n", b"ro.vendor.build.version.sdk=36\n", "ro.vendor.build.version.sdk (in sys)")
    replace_exact(data, b"ro.vendor_dlkm.build.version.sdk=34\n", b"ro.vendor_dlkm.build.version.sdk=36\n", "ro.vendor_dlkm.build.version.sdk (in sys)")
    replace_exact(data, b"ro.product.vndk.version=34\n", b"ro.product.vndk.version=36\n", "ro.product.vndk.version")
    replace_exact(data, b"ro.vndk.version=34\n", b"ro.vndk.version=36\n", "ro.vndk.version")

    # Flavor / Fingerprint / Description
    replace_exact(data, b"user 14 ", b"user 16 ", "description user 16")
    replace_exact(data, b":14/UE1A", b":16/UE1A", "fingerprint :16/UE1A")

    assert len(data) == orig_len, f"File size changed! {len(data)} != {orig_len}"
    with open(SYSTEM_IMG, "wb") as f:
        f.write(data)
    print("✅ Successfully patched system.img!\n")

def patch_vendor_img():
    print(f"📦 Patching {VENDOR_IMG}...")
    orig_len = os.path.getsize(VENDOR_IMG)
    with open(VENDOR_IMG, "rb") as f:
        data = bytearray(f.read())

    replace_exact(data, b"ro.vendor.build.version.release=14\n", b"ro.vendor.build.version.release=16\n", "ro.vendor.build.version.release")
    replace_exact(data, b"ro.vendor.build.version.release_or_codename=14\n", b"ro.vendor.build.version.release_or_codename=16\n", "ro.vendor.build.version.release_or_codename")
    replace_exact(data, b"ro.vendor_dlkm.build.version.release=14\n", b"ro.vendor_dlkm.build.version.release=16\n", "ro.vendor_dlkm.build.version.release")
    replace_exact(data, b"ro.vendor_dlkm.build.version.release_or_codename=14\n", b"ro.vendor_dlkm.build.version.release_or_codename=16\n", "ro.vendor_dlkm.build.version.release_or_codename")

    replace_exact(data, b"ro.odm.build.version.release=14\n", b"ro.odm.build.version.release=16\n", "ro.odm.build.version.release")
    replace_exact(data, b"ro.odm.build.version.release_or_codename=14\n", b"ro.odm.build.version.release_or_codename=16\n", "ro.odm.build.version.release_or_codename")
    replace_exact(data, b"ro.odm_dlkm.build.version.release=14\n", b"ro.odm_dlkm.build.version.release=16\n", "ro.odm_dlkm.build.version.release")
    replace_exact(data, b"ro.odm_dlkm.build.version.release_or_codename=14\n", b"ro.odm_dlkm.build.version.release_or_codename=16\n", "ro.odm_dlkm.build.version.release_or_codename")

    replace_exact(data, b"ro.vendor.build.version.sdk=34\n", b"ro.vendor.build.version.sdk=36\n", "ro.vendor.build.version.sdk")
    replace_exact(data, b"ro.vendor_dlkm.build.version.sdk=34\n", b"ro.vendor_dlkm.build.version.sdk=36\n", "ro.vendor_dlkm.build.version.sdk")
    replace_exact(data, b"ro.odm.build.version.sdk=34\n", b"ro.odm.build.version.sdk=36\n", "ro.odm.build.version.sdk")
    replace_exact(data, b"ro.odm_dlkm.build.version.sdk=34\n", b"ro.odm_dlkm.build.version.sdk=36\n", "ro.odm_dlkm.build.version.sdk")

    assert len(data) == orig_len, f"File size changed! {len(data)} != {orig_len}"
    with open(VENDOR_IMG, "wb") as f:
        f.write(data)
    print("✅ Successfully patched vendor.img!\n")

def patch_ramdisk_img():
    print(f"📦 Patching {RAMDISK_IMG}...")
    cpio_path = "/tmp/ramdisk_patch.cpio"
    # Decompress
    subprocess.run(["lz4", "-d", "-f", RAMDISK_IMG, cpio_path], check=True)
    with open(cpio_path, "rb") as f:
        data = bytearray(f.read())

    replace_exact(data, b"ro.bootimage.build.version.release=14\n", b"ro.bootimage.build.version.release=16\n", "ro.bootimage.build.version.release")
    replace_exact(data, b"ro.bootimage.build.version.release_or_codename=14\n", b"ro.bootimage.build.version.release_or_codename=16\n", "ro.bootimage.build.version.release_or_codename")
    replace_exact(data, b"ro.bootimage.build.version.sdk=34\n", b"ro.bootimage.build.version.sdk=36\n", "ro.bootimage.build.version.sdk")
    replace_exact(data, b":14/UE1A", b":16/UE1A", "fingerprint in ramdisk")

    with open(cpio_path, "wb") as f:
        f.write(data)

    # Recompress with lz4 legacy frame compatible with Linux kernel
    subprocess.run(["lz4", "-l", "-9", "-f", cpio_path, RAMDISK_IMG], check=True)
    if os.path.exists(cpio_path):
        os.remove(cpio_path)
    print("✅ Successfully patched ramdisk.img!\n")

def patch_build_prop():
    print(f"📝 Updating {BUILD_PROP}...")
    if not os.path.exists(BUILD_PROP):
        return
    with open(BUILD_PROP, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.replace("ro.build.version.release=14", "ro.build.version.release=16")
    content = content.replace("ro.build.version.release_or_codename=14", "ro.build.version.release_or_codename=16")
    content = content.replace("ro.build.version.release_or_preview_display=14", "ro.build.version.release_or_preview_display=16")
    content = content.replace("ro.build.version.security_patch=2023-09-05", "ro.build.version.security_patch=2026-09-05")
    content = content.replace("ro.build.version.sdk=34", "ro.build.version.sdk=36")
    content = content.replace("ro.system.build.version.release=14", "ro.system.build.version.release=16")
    content = content.replace("ro.system.build.version.release_or_codename=14", "ro.system.build.version.release_or_codename=16")
    content = content.replace("ro.system.build.version.sdk=34", "ro.system.build.version.sdk=36")

    with open(BUILD_PROP, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ Host build.prop updated!\n")

def main():
    patch_build_prop()
    patch_system_img()
    patch_vendor_img()
    patch_ramdisk_img()
    print("🎉 All images patched to Android 16 (API 36) & Security Patch 2026-09-05 successfully!")

if __name__ == "__main__":
    main()
