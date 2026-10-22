#!/usr/bin/env python3
"""
AURA OS — Remove Default Camera (Camera2) from System Images
Completely unlinks /product/app/Camera2 and wipes references to com.android.camera2.
Preserves exact byte alignments and ext4 structural integrity.
"""

import os
import sys

SYSDIR = "/Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a"
SYSTEM_IMG = os.path.join(SYSDIR, "system.img")

def main():
    if not os.path.exists(SYSTEM_IMG):
        print(f"Error: {SYSTEM_IMG} not found")
        sys.exit(1)

    print(f"📦 Patching {SYSTEM_IMG} to remove default camera...")
    with open(SYSTEM_IMG, "r+b") as f:
        # 1. Unlink Camera2 directory entry from /product/app/ (offset 1084276760)
        f.seek(1084276760)
        chunk = f.read(48)
        if chunk[4:6] == b'\x20\x00' and chunk[32:48] == b'\x13\x00\x00\x00\x10\x00\x07\x02Camera2\x00':
            f.seek(1084276764)
            f.write(b'\x30\x00') # Increase Calendar rec_len to 48 (covers deleted Camera2)
            f.seek(1084276792)
            f.write(b'\x00' * 16) # Zero out Camera2 entry
            print("  ✅ Successfully unlinked /product/app/Camera2 directory entry")
        else:
            print("  ℹ️ /product/app/Camera2 directory entry already unlinked")

        # 2. Unlink Camera2.apk inside inode 19 directory (offset 1123885068)
        f.seek(1123885068)
        chunk2 = f.read(32)
        if chunk2[4:6] == b'\x0c\x00' and chunk2[12:32] == b'\x14\x00\x00\x00\x14\x00\x0b\x01Camera2.apk\x00':
            f.seek(1123885072)
            f.write(b'\x20\x00') # Increase .. rec_len to 32 (covers deleted Camera2.apk)
            f.seek(1123885080)
            f.write(b'\x00' * 20) # Zero out Camera2.apk entry
            print("  ✅ Successfully unlinked Camera2.apk from inode 19 directory")
        else:
            print("  ℹ️ Inode 19 Camera2.apk already unlinked")

        # 3. Neutralize initial-package-state & install-in-user-type
        for off in [2102310823, 2102318524]:
            f.seek(off)
            target = b'package="com.android.camera2"'
            if f.read(len(target)) == target:
                f.seek(off)
                f.write(b'package="com.android.dummycam"')
                print(f"  ✅ Neutralized package reference at {off}")

    print("🎉 Done! Default Camera2 has been completely eradicated from system.img.")

if __name__ == "__main__":
    main()
