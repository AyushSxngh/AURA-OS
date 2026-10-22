#!/usr/bin/env python3
"""
AURA OS — Patch Build.HARDWARE and Build.BOARD to Qualcomm / Samsung Galaxy S24 Ultra.
1. Patches framework.jar classes3.dex inside system.img:
   - Redirects Build.HARDWARE property lookup from 'ro.hardware' to 'ro.hdware.q'
   - Updates DEX Adler32 and SHA-1 checksums
   - Updates ZIP local and central directory CRC32
2. Injects ro.hdware.q=qcom into /system/build.prop inside system.img
3. Patches ro.product.board=goldfish_arm64 to pineapple in system.img and vendor.img
All replacements preserve EXACT byte lengths.
"""

import os
import zlib
import hashlib
import struct

SYSDIR = "/Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a"
SYSTEM_IMG = os.path.join(SYSDIR, "system.img")
VENDOR_IMG = os.path.join(SYSDIR, "vendor.img")
HOST_BUILD_PROP = os.path.join(SYSDIR, "build.prop")

def patch_framework_jar(system_img_path):
    print("📦 Patching classes3.dex in framework.jar inside system.img...")
    with open(system_img_path, "r+b") as f:
        # Locate framework.jar
        f.seek(0x18fb6000)
        jar_head = f.read(100)
        assert jar_head[:4] == b"PK\x03\x04", "framework.jar not found at 0x18fb6000!"

        # Read classes3.dex from system.img
        dex_offset = 0x1a15e76c
        dex_size = 10274796
        f.seek(dex_offset)
        dex_data = bytearray(f.read(dex_size))
        assert dex_data[:8] == b"dex\n039\x00", "classes3.dex magic mismatch!"

        # Locate string ro.hardware\0 or ro.hdware.q\0
        target = b"ro.hardware\x00"
        str_idx = dex_data.find(target)
        if str_idx == -1 and b"ro.hdware.q\x00" in dex_data:
            print("  ℹ️ classes3.dex already patched to ro.hdware.q!")
            return
        assert str_idx == 0x8794c3, f"Unexpected ro.hardware offset: {hex(str_idx)}"

        # Replace with ro.hdware.q\0 (exact 12 bytes)
        replacement = b"ro.hdware.q\x00"
        dex_data[str_idx:str_idx + len(replacement)] = replacement
        print(f"  ✅ Replaced ro.hardware with ro.hdware.q at offset {hex(str_idx)}")

        # Recompute SHA-1 (offset 12 to 32 covers bytes 32 to end)
        new_sha1 = hashlib.sha1(dex_data[32:]).digest()
        dex_data[12:32] = new_sha1

        # Recompute Adler-32 (offset 8 to 12 covers bytes 12 to end)
        new_adler = zlib.adler32(dex_data[12:]) & 0xffffffff
        dex_data[8:12] = new_adler.to_bytes(4, "little")
        print(f"  ✅ Recomputed DEX Adler32 ({hex(new_adler)}) and SHA1")

        # Recompute CRC32 for ZIP
        new_crc = zlib.crc32(dex_data) & 0xffffffff
        print(f"  ✅ New ZIP CRC32: {hex(new_crc)}")

        # Write back classes3.dex data
        f.seek(dex_offset)
        f.write(dex_data)

        # Update Local Header CRC32 (in-jar offset 0x11a874e)
        local_crc_offset = 0x18fb6000 + 0x11a874e
        f.seek(local_crc_offset)
        f.write(new_crc.to_bytes(4, "little"))

        # Update Central Directory CRC32 (in-jar offset 0x262864e)
        cd_crc_offset = 0x18fb6000 + 0x262864e
        f.seek(cd_crc_offset)
        f.write(new_crc.to_bytes(4, "little"))
        print(f"  ✅ Updated ZIP local & central directory CRC32 headers")

def patch_system_build_prop(system_img_path):
    print("📝 Injecting ro.hdware.q=qcom into /system/build.prop inside system.img...")
    with open(system_img_path, "r+b") as f:
        f.seek(0x100e109f)
        prop_data = f.read(5000)

        target = b"###################\n# end of file\n"
        idx = prop_data.find(target)
        assert idx != -1, "Target banner before '# end of file' not found in build.prop!"

        # Replace 20 bytes '###################\n' with 'ro.hdware.q=qcom\n#==\n'
        abs_offset = 0x100e109f + idx
        f.seek(abs_offset)
        replacement = b"ro.hdware.q=qcom\n#=\n"
        assert len(replacement) == 20, f"Length {len(replacement)} != 20"
        f.write(replacement)
        print(f"  ✅ Injected ro.hdware.q=qcom at system.img offset {hex(abs_offset)}")

def patch_board_properties(system_img_path, vendor_img_path):
    print("🎯 Patching ro.product.board=goldfish_arm64 -> pineapple...")
    target = b"ro.product.board=goldfish_arm64\n"
    replacement = b"ro.product.board=pineapple\n#===\n"
    assert len(target) == len(replacement)

    for img_path in [system_img_path, vendor_img_path]:
        with open(img_path, "r+b") as f:
            data = f.read()
            idx = data.find(target)
            if idx != -1:
                f.seek(idx)
                f.write(replacement)
                print(f"  ✅ Patched {os.path.basename(img_path)} at offset {hex(idx)}")
            else:
                print(f"  ⚠️ Target not found in {os.path.basename(img_path)} (already patched?)")

def patch_host_build_prop(host_prop_path):
    print("📋 Updating host build.prop...")
    with open(host_prop_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "ro.hdware.q=" not in content:
        content += "\nro.hdware.q=qcom\n"
    if "ro.product.board=goldfish_arm64" in content:
        content = content.replace("ro.product.board=goldfish_arm64", "ro.product.board=pineapple")

    with open(host_prop_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  ✅ Host build.prop updated")

def main():
    print("🚀 Applying AURA OS Qualcomm & Samsung S24 Ultra hardware patches...")
    patch_framework_jar(SYSTEM_IMG)
    patch_system_build_prop(SYSTEM_IMG)
    patch_board_properties(SYSTEM_IMG, VENDOR_IMG)
    patch_host_build_prop(HOST_BUILD_PROP)
    print("🎉 All patches applied cleanly!")

if __name__ == "__main__":
    main()
