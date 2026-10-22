#!/usr/bin/env python3
"""
Patch power_profile.xml inside framework-res.apk and rro_product.apk within system.img
Sets:
- battery.capacity = 5000 (Samsung Galaxy S24 Ultra)
- screen.full = 150 (enables battery usage attribution list in Google Settings)
Preserves EXACT byte lengths and offsets down to the bit.
"""

import os
import zlib
import struct
import binascii

SYSDIR = "/Users/ayush/Library/Android/sdk/system-images/android-34/google_apis_playstore/arm64-v8a"
SYSTEM_IMG = os.path.join(SYSDIR, "system.img")

def patch_power_profile_in_zip(apk_bytes, expected_csize, orig_xml_marker=b'\x03\x030.1\x00'):
    entry_name = b'res/xml/power_profile.xml'
    # Find local header
    cur = 0
    lh_pos = -1
    while True:
        pos = apk_bytes.find(b'PK\x03\x04', cur)
        if pos == -1: break
        sig, ver, flags, comp, mtime, mdate, crc, csize, usize, nlen, elen = struct.unpack_from('<IHHHHHIIIHH', apk_bytes, pos)
        fn = apk_bytes[pos+30:pos+30+nlen]
        if fn == entry_name:
            lh_pos = pos
            data_start = pos + 30 + nlen + elen
            break
        cur = pos + 1
    
    if lh_pos == -1:
        raise ValueError(f"Could not find local header for {entry_name}")
    
    # Read compressed data
    raw_deflate = bytes(apk_bytes[data_start:data_start + expected_csize])
    orig_xml = zlib.decompress(raw_deflate, -zlib.MAX_WBITS)
    print(f"  Uncompressed XML length: {len(orig_xml)}")
    
    # Replace in string pool
    assert orig_xml_marker in orig_xml, "orig_xml_marker not found!"
    mod_xml = orig_xml.replace(orig_xml_marker, b'\x03\x03150\x00', 1)
    assert b'\x04\x041000\x00' in mod_xml, "1000 not found in XML!"
    mod_xml = mod_xml.replace(b'\x04\x041000\x00', b'\x04\x045000\x00', 1)
    assert len(mod_xml) == len(orig_xml), "Modified XML length mismatch!"
    
    # Recompress with level 9
    new_raw_deflate = zlib.compress(mod_xml, 9)[2:-4]
    assert len(new_raw_deflate) == expected_csize, f"Compressed size mismatch: {len(new_raw_deflate)} vs {expected_csize}"
    new_crc = binascii.crc32(mod_xml)
    
    # Update data in apk
    apk_bytes[data_start:data_start + expected_csize] = new_raw_deflate
    
    # Update Data Descriptor trailer CRC
    struct.pack_into('<I', apk_bytes, data_start + expected_csize + 4, new_crc)
    
    # Update Central Directory CRC
    cd_pos = apk_bytes.find(b'PK\x01\x02')
    while cd_pos != -1:
        cd_sig, cd_ver, cd_ver_req, cd_flags, cd_comp, cd_time, cd_date, cd_crc, cd_csize, cd_usize, cd_nlen, cd_elen, cd_clen = struct.unpack_from('<IHHHHHHIIIHHH', apk_bytes, cd_pos)
        cd_name = bytes(apk_bytes[cd_pos+46:cd_pos+46+cd_nlen])
        if cd_name == entry_name:
            struct.pack_into('<I', apk_bytes, cd_pos + 16, new_crc)
            print(f"  Updated Central Directory CRC: {hex(new_crc)}")
            break
        cd_pos = apk_bytes.find(b'PK\x01\x02', cd_pos + 46 + cd_nlen + cd_elen + cd_clen)
        
    return apk_bytes

def main():
    print(f"Reading {SYSTEM_IMG}...")
    with open(SYSTEM_IMG, "rb") as f:
        img_data = bytearray(f.read())
        
    # 1. Patch framework-res__auto_generated_rro_product.apk (size: 16868, csize: 1313)
    rro_offset = 2123407360
    rro_len = 16868
    rro_slice = bytearray(img_data[rro_offset:rro_offset + rro_len])
    assert bytes(rro_slice[:4]) == b'PK\x03\x04', "RRO header mismatch!"
    print("Patching framework-res__auto_generated_rro_product.apk in system.img...")
    patched_rro = patch_power_profile_in_zip(rro_slice, expected_csize=1313)
    img_data[rro_offset:rro_offset + rro_len] = patched_rro
    print("  ✅ RRO APK patched successfully!")

    # 2. Patch framework-res.apk (size: 34374835, csize: 1445)
    fw_offset = 384630784
    fw_len = 34374835
    fw_slice = bytearray(img_data[fw_offset:fw_offset + fw_len])
    assert bytes(fw_slice[:4]) == b'PK\x03\x04', "framework-res header mismatch!"
    print("Patching framework-res.apk in system.img...")
    patched_fw = patch_power_profile_in_zip(fw_slice, expected_csize=1445)
    img_data[fw_offset:fw_offset + fw_len] = patched_fw
    print("  ✅ framework-res.apk patched successfully!")

    print("Writing modified system.img...")
    with open(SYSTEM_IMG, "wb") as f:
        f.write(img_data)
    print("🎉 system.img successfully patched with Samsung S24 Ultra Power Profile!")

if __name__ == "__main__":
    main()
