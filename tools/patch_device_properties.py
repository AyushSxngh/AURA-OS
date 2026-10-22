#!/usr/bin/env python3
"""
AURA OS — Patch Android System Images to Samsung Galaxy S24 Ultra
Patches ro.product.* properties across all partition build.props inside system.img and vendor.img.
All replacements preserve EXACT byte lengths down to the byte using comment padding.
"""

import os
import re
import sys

SYSDIR = "/Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a"
SYSTEM_IMG = os.path.join(SYSDIR, "system.img")
VENDOR_IMG = os.path.join(SYSDIR, "vendor.img")
BUILD_PROP = os.path.join(SYSDIR, "build.prop")

def patch_partition_block(part, orig_block):
    orig_len = len(orig_block)
    # Model is technical model number SM-S928B across all partitions (Play Store shows Samsung SM-S928B)
    model_val = "SM-S928B"
    lines = [
        f"ro.product.{part}.brand=samsung",
        f"ro.product.{part}.device=e3q",
        f"ro.product.{part}.manufacturer=Samsung",
        f"ro.product.{part}.model={model_val}",
        f"ro.product.{part}.name=e3qxeea",
    ]
    new_text = "\n".join(lines) + "\n"
    diff = orig_len - len(new_text)
    if diff < 0:
        raise ValueError(f"New text for {part} is longer than original ({len(new_text)} > {orig_len})")
    if diff > 0:
        pad = "#" + ("=" * (diff - 2)) + "\n"
        new_text += pad
    assert len(new_text) == orig_len, f"Length mismatch for {part}: {len(new_text)} vs {orig_len}"
    return new_text.encode("utf-8")

def patch_file(filepath):
    print(f"📦 Patching {os.path.basename(filepath)}...")
    with open(filepath, "rb") as f:
        data = bytearray(f.read())

    count = 0
    # Pattern for standard 5-line block
    pattern = re.compile(
        rb"ro\.product\.([a-z_]+)\.brand=[^\r\n]+\r?\n"
        rb"ro\.product\.[a-z_]+\.device=[^\r\n]+\r?\n"
        rb"ro\.product\.[a-z_]+\.manufacturer=[^\r\n]+\r?\n"
        rb"ro\.product\.[a-z_]+\.model=[^\r\n]+\r?\n"
        rb"ro\.product\.[a-z_]+\.name=[^\r\n]+\r?\n"
    )

    for m in pattern.finditer(bytes(data)):
        part_name = m.group(1).decode("utf-8")
        orig_bytes = m.group(0)
        start, end = m.start(), m.end()
        new_bytes = patch_partition_block(part_name, orig_bytes.decode("utf-8", errors="ignore"))
        data[start:end] = new_bytes
        count += 1
        print(f"  ✅ Patched partition '{part_name}' at offset {start} (exact {len(new_bytes)} bytes)")

        # Safely patch OS version and security patch strictly within this partition's build.prop block
        chunk_end = min(len(data), end + 3500)
        chunk = bytes(data[end:chunk_end])
        new_chunk = chunk
        for old_str, new_str in [
            (b"version.release=14\n", b"version.release=16\n"),
            (b"version.release_or_codename=14\n", b"version.release_or_codename=16\n"),
            (b"version.release_or_preview_display=14\n", b"version.release_or_preview_display=16\n"),
            (b"version.security_patch=2023-09-05\n", b"version.security_patch=2026-09-05\n"),
            (b"user 14 ", b"user 16 "),
        ]:
            if old_str in new_chunk:
                assert len(old_str) == len(new_str)
                new_chunk = new_chunk.replace(old_str, new_str)
                print(f"     -> Patched {old_str.strip().decode()} in partition '{part_name}'")
        data[end:chunk_end] = new_chunk

    # Also patch ro.soc.manufacturer and ro.soc.model if present (exact length preservation)
    if b"ro.soc.manufacturer=AOSP\n" in data:
        data = bytearray(bytes(data).replace(b"ro.soc.manufacturer=AOSP\n", b"ro.soc.manufacturer=QCOM\n"))
        print("  ✅ Patched ro.soc.manufacturer=AOSP -> QCOM")
    if b"ro.soc.model=ranchu\n" in data:
        data = bytearray(bytes(data).replace(b"ro.soc.model=ranchu\n", b"ro.soc.model=SM8650\n"))
        print("  ✅ Patched ro.soc.model=ranchu -> SM8650")

    if count > 0 or b"ro.soc." in data:
        with open(filepath, "wb") as f:
            f.write(data)
        print(f"🎉 Successfully patched {os.path.basename(filepath)}!\n")
    else:
        print(f"⚠️ No matching blocks found in {os.path.basename(filepath)}.\n")

def patch_host_build_prop(filepath):
    print(f"📝 Updating host {os.path.basename(filepath)}...")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace key lines
    replacements = {
        "ro.product.system.brand=google": "ro.product.system.brand=samsung",
        "ro.product.system.device=generic": "ro.product.system.device=e3q",
        "ro.product.system.manufacturer=Google": "ro.product.system.manufacturer=Samsung",
        "ro.product.system.model=mainline": "ro.product.system.model=SM-S928B",
        "ro.product.system.model=Galaxy S24 Ultra": "ro.product.system.model=SM-S928B",
        "ro.product.model=Galaxy S24 Ultra": "ro.product.model=SM-S928B",
        "ro.product.system.name=mainline": "ro.product.system.name=e3qxeea",
        "ro.build.flavor=sdk_gphone64_arm64-user": "ro.build.flavor=e3qxeea-user",
        "ro.build.product=emu64a": "ro.build.product=e3q",
        "ro.build.version.release=14": "ro.build.version.release=16",
        "ro.system.build.version.release=14": "ro.system.build.version.release=16",
        "ro.build.version.release_or_codename=14": "ro.build.version.release_or_codename=16",
        "ro.system.build.version.release_or_codename=14": "ro.system.build.version.release_or_codename=16",
        "ro.build.version.release_or_preview_display=14": "ro.build.version.release_or_preview_display=16",
        "ro.build.version.security_patch=2023-09-05": "ro.build.version.security_patch=2026-09-05",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)

    # Append top-level product properties if not present
    if "ro.product.model=" not in content:
        content += "\n# Samsung Galaxy S24 Ultra Overrides\n"
        content += "ro.product.model=SM-S928B\n"
        content += "ro.product.brand=samsung\n"
        content += "ro.product.manufacturer=Samsung\n"
        content += "ro.product.device=e3q\n"
        content += "ro.product.name=e3qxeea\n"
        content += "ro.warranty_bit=0\n"
        content += "ro.boot.warranty_bit=0\n"
        content += "ro.boot.flash.locked=1\n"
        content += "ro.boot.verifiedbootstate=green\n"
        content += "ro.boot.vbmeta.device_state=locked\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ Host build.prop updated!\n")

def main():
    patch_host_build_prop(BUILD_PROP)
    patch_file(VENDOR_IMG)
    patch_file(SYSTEM_IMG)
    print("✨ All system images patched to Samsung Galaxy S24 Ultra (SM-S928B) successfully!")

if __name__ == "__main__":
    main()
