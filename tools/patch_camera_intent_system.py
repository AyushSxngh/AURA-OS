#!/usr/bin/env python3
"""
tools/patch_camera_intent_system.py
AURA OS — Permanent System Camera Intent Unification Patch
Relaxes the Android 11+ system-only constraint on ACTION_IMAGE_CAPTURE / ACTION_VIDEO_CAPTURE
by emptying the CAMERA_ACTIONS Set in ComputerEngine inside services.jar.

Result:
- MediaStore.ACTION_IMAGE_CAPTURE resolves natively to com.sec.android.app.camera.
- Third-party apps (Flutter image_picker, banking, KYC, loan apps) open com.sec.android.app.camera directly.
- Preserves exact byte alignments, DEX checksums, and ART oat/vdex headers.
"""

import os
import sys
import zlib
import hashlib
import struct
import subprocess
import time

SYSDIR = "/Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a"
SYSTEM_IMG = os.path.join(SYSDIR, "system.img")

CLASSES3_DEX_START = 0x1ed05e20
CLASSES3_DEX_SIZE  = 2208040
LOCAL_CRC_OFFSET   = 0x1ed05df4 + 14
CD_CRC_OFFSET      = 0x1ef28309 + 16
ODEX_CRC_OFFSET    = 0x1d2ec502 + len(b"mework/services.jar!classes3.dex")
VDEX_CRC_OFFSET    = 0x1daa003c + len(b"\xc8U\x0f\x91\xbe'dc")

TARGET_BYTECODE = b'\x1a\x01\x33\x1f\x1a\x02\x40\x1f\x6e\x30\xe8\x04\x10\x02\x1a\x01\x34\x1f\x6e\x30\xe8\x04\x10\x02\x1a\x01\x10\x1f\x1a\x02\x3f\x1f\x6e\x30\xe8\x04\x10\x02\x0e\x00'
REPLACEMENT_BYTECODE = b'\x0e\x00' + b'\x00' * 38

def apply_patch():
    print("=" * 80)
    print("  📸 AURA OS — PATCHING SERVICES.JAR FOR CAMERA INTENT ROUTING")
    print("=" * 80)

    if not os.path.exists(SYSTEM_IMG):
        print(f"Error: {SYSTEM_IMG} not found")
        sys.exit(1)

    with open(SYSTEM_IMG, "r+b") as f:
        # 1. Verify Local and CD CRC
        f.seek(LOCAL_CRC_OFFSET)
        orig_local_crc = f.read(4)
        f.seek(CD_CRC_OFFSET)
        orig_cd_crc = f.read(4)
        f.seek(ODEX_CRC_OFFSET)
        orig_odex_crc = f.read(4)
        f.seek(VDEX_CRC_OFFSET)
        orig_vdex_crc = f.read(4)

        print(f"[*] Original CRC32 in headers: {orig_local_crc.hex()}")
        assert orig_local_crc == orig_cd_crc == orig_odex_crc == orig_vdex_crc, "CRC inconsistency across headers!"

        # 2. Read classes3.dex
        f.seek(CLASSES3_DEX_START)
        dex = bytearray(f.read(CLASSES3_DEX_SIZE))
        assert dex[:8] == b"dex\n039\x00", "classes3.dex magic mismatch!"

        # 3. Locate target bytecode
        idx = dex.find(TARGET_BYTECODE)
        if idx == -1:
            if dex.find(REPLACEMENT_BYTECODE) != -1:
                print("  ℹ️ classes3.dex is already patched!")
                return
            raise RuntimeError("TARGET_BYTECODE not found in classes3.dex!")

        print(f"[*] Found TARGET_BYTECODE at dex offset {hex(idx)}")
        dex[idx:idx + len(REPLACEMENT_BYTECODE)] = REPLACEMENT_BYTECODE
        print(f"  ✅ Replaced 40 bytes with return-void + 19 nops")

        # 4. Recompute Checksums
        new_sha1 = hashlib.sha1(dex[32:]).digest()
        dex[12:32] = new_sha1

        new_adler = zlib.adler32(dex[12:]) & 0xffffffff
        dex[8:12] = new_adler.to_bytes(4, "little")

        new_crc = zlib.crc32(dex) & 0xffffffff
        new_crc_bytes = new_crc.to_bytes(4, "little")

        print(f"  ✅ New DEX SHA1: {new_sha1.hex()}")
        print(f"  ✅ New DEX Adler32: {hex(new_adler)}")
        print(f"  ✅ New ZIP/OAT CRC32: {hex(new_crc)}")

        # 5. Write back patched DEX
        f.seek(CLASSES3_DEX_START)
        f.write(dex)
        print(f"  ✅ Written patched classes3.dex to system.img at {hex(CLASSES3_DEX_START)}")

        # 6. Update all 4 CRC headers
        f.seek(LOCAL_CRC_OFFSET)
        f.write(new_crc_bytes)
        f.seek(CD_CRC_OFFSET)
        f.write(new_crc_bytes)
        f.seek(ODEX_CRC_OFFSET)
        f.write(new_crc_bytes)
        f.seek(VDEX_CRC_OFFSET)
        f.write(new_crc_bytes)
        print("  ✅ Synchronized CRC32 across ZIP Local, Central Directory, services.odex, and services.vdex")

    print("\n🎉 Patch successfully applied to system.img!")

if __name__ == "__main__":
    apply_patch()
