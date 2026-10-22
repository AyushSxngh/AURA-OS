#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil

sys.path.insert(0, "/Users/ayush/Desktop/HEBB NETWORK/Emulator/tools")
from generate_app_history import APP_CATALOG, AAPT_BIN, D8_BIN, APKSIGNER_BIN, ANDROID_JAR, KEYSTORE_PATH

BUILD_CACHE = "/tmp/clean_apk_build"
shared_dex = f"{BUILD_CACHE}/dex/classes.dex"

installed_3p = subprocess.run(["adb", "shell", "pm", "list", "packages", "-3"], capture_output=True, text=True).stdout
installed_pkgs = set()
for line in installed_3p.splitlines():
    if line.startswith("package:"):
        installed_pkgs.add(line.split(":")[1].strip())

print(f"Total installed third-party packages: {len(installed_pkgs)}")

rebuilt_count = 0
for app in APP_CATALOG:
    pkg = app["package"]
    if pkg not in installed_pkgs:
        continue
    
    dump = subprocess.run(["adb", "shell", "dumpsys", "package", pkg], capture_output=True, text=True).stdout
    if "com.aura" not in dump:
        continue

    app_name = app["name"]
    print(f"Rebuilding & updating {app_name} ({pkg})...")
    app_dir = os.path.join(BUILD_CACHE, "apks", pkg)
    os.makedirs(app_dir, exist_ok=True)
    
    perms = app.get("permissions", [])
    if "android.permission.POST_NOTIFICATIONS" not in perms:
        perms.append("android.permission.POST_NOTIFICATIONS")
    perms_xml = "\n".join([f'    <uses-permission android:name="{p}" />' for p in perms])
    game_attrs = 'android:isGame="true" android:appCategory="game"' if app["is_game"] else ""

    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{pkg}"
    android:versionCode="{app['version_code']}"
    android:versionName="{app['version_name']}">
    <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="34" />
{perms_xml}
    <application android:label="{app_name}" {game_attrs} android:theme="@android:style/Theme.DeviceDefault.NoActionBar">
        <activity android:name="com.android.app.MainActivity" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>"""
    manifest_path = os.path.join(app_dir, "AndroidManifest.xml")
    with open(manifest_path, "w") as f:
        f.write(manifest)
        
    unsigned_apk = os.path.join(app_dir, "unsigned.apk")
    signed_apk = os.path.join(app_dir, f"{pkg}.apk")
    
    subprocess.run([AAPT_BIN, "package", "-F", unsigned_apk, "-M", manifest_path, "-I", ANDROID_JAR, "-f"], check=True, capture_output=True)
    subprocess.run(["zip", "-j", unsigned_apk, shared_dex], check=True, capture_output=True)
    subprocess.run([APKSIGNER_BIN, "sign", "--ks", KEYSTORE_PATH, "--ks-pass", "pass:android", "--out", signed_apk, unsigned_apk], check=True, capture_output=True)
    
    subprocess.run(["adb", "install", "-r", "-i", "com.android.vending", signed_apk], check=True, capture_output=True)
    subprocess.run(["adb", "shell", "pm", "grant", pkg, "android.permission.POST_NOTIFICATIONS"], capture_output=True)
    rebuilt_count += 1
    print(f"  -> Reinstalled {pkg} cleanly.")

print(f"Done! Rebuilt and cleaned {rebuilt_count} apps.")
