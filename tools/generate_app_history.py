#!/usr/bin/env python3
"""
AURA OS — Authentic App History, Installed/Uninstalled History & Usage Simulator
==============================================================================
Populates the Android 14 Virtualization Platform (AURA OS) with an authentic,
statistically realistic mobile app ecosystem:
  1. Real Installed Apps (Social, Banking/UPI, Shopping, Entertainment, Mobility)
  2. Active Game Apps (BGMI, Free Fire MAX, Subway Surfers, Ludo King, Candy Crush, etc.)
  3. Real Uninstalled Histories in PackageManager (MATCH_UNINSTALLED_PACKAGES / pm -u)
  4. Authentic First-Install & Last-Update Timestamps over historical months
  5. Multi-Day UsageStatsManager Foreground Activity Events & App Launch Counts
  6. Shared Storage Directory Footprints (/sdcard/Android/data and residuals)
  7. Google Play Store Installer Provenance (installerPackageName=com.android.vending)
"""

import os
import sys
import time
import shutil
import random
import subprocess
from pathlib import Path

# Paths configuration
ANDROID_SDK = os.environ.get("ANDROID_HOME", os.path.expanduser("~/Library/Android/sdk"))
BUILD_TOOLS_DIR = os.path.join(ANDROID_SDK, "build-tools")
PLATFORMS_DIR = os.path.join(ANDROID_SDK, "platforms")
KEYSTORE_PATH = os.path.expanduser("~/.android/debug.keystore")
BUILD_CACHE_DIR = "/tmp/sec_app_cache"

# Find latest build tools
def get_latest_build_tool(tool_name):
    if not os.path.exists(BUILD_TOOLS_DIR):
        raise FileNotFoundError(f"Android build tools not found at {BUILD_TOOLS_DIR}")
    versions = sorted(os.listdir(BUILD_TOOLS_DIR), reverse=True)
    for v in versions:
        candidate = os.path.join(BUILD_TOOLS_DIR, v, tool_name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(f"Tool {tool_name} not found in {BUILD_TOOLS_DIR}")

def get_android_jar():
    if not os.path.exists(PLATFORMS_DIR):
        raise FileNotFoundError(f"Android platforms directory not found at {PLATFORMS_DIR}")
    platforms = sorted([p for p in os.listdir(PLATFORMS_DIR) if p.startswith("android-")], reverse=True)
    for p in platforms:
        jar = os.path.join(PLATFORMS_DIR, p, "android.jar")
        if os.path.isfile(jar):
            return jar
    raise FileNotFoundError("android.jar not found in Android SDK platforms")

AAPT_BIN = get_latest_build_tool("aapt")
D8_BIN = get_latest_build_tool("d8")
APKSIGNER_BIN = get_latest_build_tool("apksigner")
ANDROID_JAR = get_android_jar()
JAVAC_BIN = "/opt/homebrew/opt/openjdk@17/bin/javac" if os.path.exists("/opt/homebrew/opt/openjdk@17/bin/javac") else shutil.which("javac")
ADB_BIN = "/opt/homebrew/bin/adb" if os.path.exists("/opt/homebrew/bin/adb") else shutil.which("adb")

# Curated App Database
APP_CATALOG = [
    # ==================== INSTALLED APPS (ACTIVE) ====================
    # --- Social & Messaging ---
    {
        "package": "com.whatsapp",
        "name": "WhatsApp",
        "version_name": "2.24.18.77",
        "version_code": 241877005,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 245,
        "update_days_ago": 6,
        "launches_per_day": 35,
        "daily_foreground_mins": 95,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_CONTACTS",
            "android.permission.WRITE_CONTACTS",
            "android.permission.CAMERA",
            "android.permission.RECORD_AUDIO",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.READ_PHONE_STATE",
            "android.permission.READ_MEDIA_IMAGES",
            "android.permission.READ_MEDIA_VIDEO",
            "android.permission.POST_NOTIFICATIONS",
            "android.permission.VIBRATE",
            "android.permission.WAKE_LOCK",
        ]
    },
    {
        "package": "com.instagram.android",
        "name": "Instagram",
        "version_name": "349.0.0.42.104",
        "version_code": 639840120,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 230,
        "update_days_ago": 12,
        "launches_per_day": 20,
        "daily_foreground_mins": 55,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.CAMERA",
            "android.permission.RECORD_AUDIO",
            "android.permission.READ_CONTACTS",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.READ_MEDIA_IMAGES",
            "android.permission.READ_MEDIA_VIDEO",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "org.telegram.messenger",
        "name": "Telegram",
        "version_name": "11.1.3",
        "version_code": 51929,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 195,
        "update_days_ago": 18,
        "launches_per_day": 12,
        "daily_foreground_mins": 30,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_CONTACTS",
            "android.permission.WRITE_CONTACTS",
            "android.permission.CAMERA",
            "android.permission.RECORD_AUDIO",
            "android.permission.READ_MEDIA_IMAGES",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.snapchat.android",
        "name": "Snapchat",
        "version_name": "13.9.0.51",
        "version_code": 113090051,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 160,
        "update_days_ago": 9,
        "launches_per_day": 15,
        "daily_foreground_mins": 35,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.CAMERA",
            "android.permission.RECORD_AUDIO",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.READ_CONTACTS",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.truecaller",
        "name": "Truecaller",
        "version_name": "14.28.6",
        "version_code": 142806,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 240,
        "update_days_ago": 15,
        "launches_per_day": 8,
        "daily_foreground_mins": 10,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_CONTACTS",
            "android.permission.WRITE_CONTACTS",
            "android.permission.READ_PHONE_STATE",
            "android.permission.READ_CALL_LOG",
            "android.permission.ANSWER_PHONE_CALLS",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.twitter.android",
        "name": "X",
        "version_name": "10.59.0-release.0",
        "version_code": 310590000,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 175,
        "update_days_ago": 21,
        "launches_per_day": 6,
        "daily_foreground_mins": 25,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_MEDIA_IMAGES",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    # --- Payments & Banking (UPI) ---
    {
        "package": "com.phonepe.app",
        "name": "PhonePe",
        "version_name": "24.09.12.0",
        "version_code": 941203,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 235,
        "update_days_ago": 14,
        "launches_per_day": 6,
        "daily_foreground_mins": 8,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_PHONE_STATE",
            "android.permission.READ_CONTACTS",
            "android.permission.CAMERA",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.RECEIVE_SMS",
            "android.permission.READ_SMS",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.google.android.apps.nbu.paisa.user",
        "name": "Google Pay",
        "version_name": "242.1.4",
        "version_code": 2420104,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 220,
        "update_days_ago": 25,
        "launches_per_day": 4,
        "daily_foreground_mins": 5,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_PHONE_STATE",
            "android.permission.READ_CONTACTS",
            "android.permission.CAMERA",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "net.one97.paytm",
        "name": "Paytm",
        "version_name": "10.60.0",
        "version_code": 1060000,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 190,
        "update_days_ago": 30,
        "launches_per_day": 3,
        "daily_foreground_mins": 6,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_PHONE_STATE",
            "android.permission.CAMERA",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.READ_CONTACTS",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.snapwork.hdfc",
        "name": "HDFC Bank MobileBanking",
        "version_name": "12.0.2",
        "version_code": 120200,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 200,
        "update_days_ago": 45,
        "launches_per_day": 2,
        "daily_foreground_mins": 4,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_PHONE_STATE",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    # --- Shopping & Food Delivery ---
    {
        "package": "com.flipkart.android",
        "name": "Flipkart",
        "version_name": "7.97",
        "version_code": 1479700,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 215,
        "update_days_ago": 16,
        "launches_per_day": 4,
        "daily_foreground_mins": 18,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.CAMERA",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "in.amazon.mShop.android.shopping",
        "name": "Amazon Shopping",
        "version_name": "28.18.0.300",
        "version_code": 28180300,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 210,
        "update_days_ago": 8,
        "launches_per_day": 3,
        "daily_foreground_mins": 15,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.CAMERA",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.application.zomato",
        "name": "Zomato",
        "version_name": "18.2.4",
        "version_code": 180204,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 185,
        "update_days_ago": 11,
        "launches_per_day": 3,
        "daily_foreground_mins": 12,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "in.swiggy.android",
        "name": "Swiggy",
        "version_name": "5.12.0",
        "version_code": 512000,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 180,
        "update_days_ago": 19,
        "launches_per_day": 2,
        "daily_foreground_mins": 10,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.grofers.customerapp",
        "name": "Blinkit",
        "version_name": "14.1.2",
        "version_code": 140102,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 140,
        "update_days_ago": 22,
        "launches_per_day": 2,
        "daily_foreground_mins": 8,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.myntra.android",
        "name": "Myntra",
        "version_name": "5.1.0",
        "version_code": 501000,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 165,
        "update_days_ago": 35,
        "launches_per_day": 1,
        "daily_foreground_mins": 10,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    # --- Entertainment & Travel ---
    {
        "package": "com.spotify.music",
        "name": "Spotify",
        "version_name": "8.9.74.568",
        "version_code": 98456812,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 205,
        "update_days_ago": 10,
        "launches_per_day": 6,
        "daily_foreground_mins": 45,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.WAKE_LOCK",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.jio.media.ondemand",
        "name": "JioCinema",
        "version_name": "24.09.20.1",
        "version_code": 2409201,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 150,
        "update_days_ago": 7,
        "launches_per_day": 2,
        "daily_foreground_mins": 40,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.WAKE_LOCK",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.ubercab",
        "name": "Uber",
        "version_name": "4.542.10001",
        "version_code": 1154210,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 170,
        "update_days_ago": 17,
        "launches_per_day": 2,
        "daily_foreground_mins": 7,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.olacabs.customer",
        "name": "Ola Cabs",
        "version_name": "6.3.2",
        "version_code": 63200,
        "is_game": False,
        "status": "INSTALLED",
        "install_days_ago": 160,
        "update_days_ago": 40,
        "launches_per_day": 1,
        "daily_foreground_mins": 5,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    # --- ACTIVE GAMES (is_game=True) ---
    {
        "package": "com.dts.freefiremax",
        "name": "Free Fire MAX",
        "version_name": "2.106.1",
        "version_code": 2019117006,
        "is_game": True,
        "status": "INSTALLED",
        "install_days_ago": 130,
        "update_days_ago": 20,
        "launches_per_day": 3,
        "daily_foreground_mins": 45,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.RECORD_AUDIO",
            "android.permission.WAKE_LOCK",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.kiloo.subwaysurf",
        "name": "Subway Surfers",
        "version_name": "3.32.0",
        "version_code": 332000,
        "is_game": True,
        "status": "INSTALLED",
        "install_days_ago": 155,
        "update_days_ago": 14,
        "launches_per_day": 4,
        "daily_foreground_mins": 25,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.ludo.king",
        "name": "Ludo King",
        "version_name": "8.0.0.264",
        "version_code": 264,
        "is_game": True,
        "status": "INSTALLED",
        "install_days_ago": 170,
        "update_days_ago": 28,
        "launches_per_day": 3,
        "daily_foreground_mins": 35,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.king.candycrushsaga",
        "name": "Candy Crush Saga",
        "version_name": "1.286.0.1",
        "version_code": 1286001,
        "is_game": True,
        "status": "INSTALLED",
        "install_days_ago": 145,
        "update_days_ago": 18,
        "launches_per_day": 2,
        "daily_foreground_mins": 20,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.miniclip.eightballpool",
        "name": "8 Ball Pool",
        "version_name": "56.0.2",
        "version_code": 560200,
        "is_game": True,
        "status": "INSTALLED",
        "install_days_ago": 115,
        "update_days_ago": 26,
        "launches_per_day": 2,
        "daily_foreground_mins": 25,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },
    {
        "package": "com.chess",
        "name": "Chess.com",
        "version_name": "4.6.14",
        "version_code": 4061400,
        "is_game": True,
        "status": "INSTALLED",
        "install_days_ago": 100,
        "update_days_ago": 15,
        "launches_per_day": 2,
        "daily_foreground_mins": 15,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.POST_NOTIFICATIONS",
        ]
    },

    # ==================== UNINSTALLED APPS (HISTORIES) ====================
    # --- Uninstalled Games (is_game=True) ---
    {
        "package": "com.imangi.templerun2",
        "name": "Temple Run 2",
        "version_name": "1.112.0",
        "version_code": 111200,
        "is_game": True,
        "status": "UNINSTALLED",
        "install_days_ago": 180,
        "uninstall_days_ago": 32,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
        ]
    },
    {
        "package": "com.fingersoft.hillclimb",
        "name": "Hill Climb Racing",
        "version_name": "1.62.1",
        "version_code": 162100,
        "is_game": True,
        "status": "UNINSTALLED",
        "install_days_ago": 190,
        "uninstall_days_ago": 45,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
        ]
    },
    {
        "package": "com.skgames.trafficrider",
        "name": "Traffic Rider",
        "version_name": "1.99",
        "version_code": 19900,
        "is_game": True,
        "status": "UNINSTALLED",
        "install_days_ago": 140,
        "uninstall_days_ago": 28,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
        ]
    },
    {
        "package": "com.halfbrick.fruitninjafree",
        "name": "Fruit Ninja",
        "version_name": "3.82.0",
        "version_code": 382000,
        "is_game": True,
        "status": "UNINSTALLED",
        "install_days_ago": 175,
        "uninstall_days_ago": 50,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
        ]
    },
    {
        "package": "com.nekki.shadowfight",
        "name": "Shadow Fight 2",
        "version_name": "2.37.0",
        "version_code": 237000,
        "is_game": True,
        "status": "UNINSTALLED",
        "install_days_ago": 165,
        "uninstall_days_ago": 38,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
        ]
    },
    {
        "package": "com.rovio.baba",
        "name": "Angry Birds 2",
        "version_name": "3.23.1",
        "version_code": 323010,
        "is_game": True,
        "status": "UNINSTALLED",
        "install_days_ago": 150,
        "uninstall_days_ago": 22,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_NETWORK_STATE",
            "android.permission.WAKE_LOCK",
        ]
    },
    # --- Uninstalled Fintech / Shopping / Dating Apps ---
    {
        "package": "com.dreamplug.androidapp",
        "name": "CRED",
        "version_name": "3.8.10",
        "version_code": 30810,
        "is_game": False,
        "status": "UNINSTALLED",
        "install_days_ago": 200,
        "uninstall_days_ago": 35,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_PHONE_STATE",
            "android.permission.ACCESS_FINE_LOCATION",
        ]
    },
    {
        "package": "com.cards.slice",
        "name": "Slice",
        "version_name": "11.2.0",
        "version_code": 112000,
        "is_game": False,
        "status": "UNINSTALLED",
        "install_days_ago": 160,
        "uninstall_days_ago": 40,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.READ_PHONE_STATE",
        ]
    },
    {
        "package": "com.naviapp",
        "name": "Navi",
        "version_name": "4.15.0",
        "version_code": 415000,
        "is_game": False,
        "status": "UNINSTALLED",
        "install_days_ago": 130,
        "uninstall_days_ago": 25,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.READ_PHONE_STATE",
        ]
    },
    {
        "package": "com.dunzo.user",
        "name": "Dunzo",
        "version_name": "4.41.0",
        "version_code": 441000,
        "is_game": False,
        "status": "UNINSTALLED",
        "install_days_ago": 170,
        "uninstall_days_ago": 60,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
        ]
    },
    {
        "package": "com.tinder",
        "name": "Tinder",
        "version_name": "15.18.0",
        "version_code": 15180000,
        "is_game": False,
        "status": "UNINSTALLED",
        "install_days_ago": 120,
        "uninstall_days_ago": 18,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.CAMERA",
        ]
    },
    {
        "package": "com.zeptoconsumerapp",
        "name": "Zepto",
        "version_name": "9.35.0",
        "version_code": 935000,
        "is_game": False,
        "status": "UNINSTALLED",
        "install_days_ago": 110,
        "uninstall_days_ago": 15,
        "permissions": [
            "android.permission.INTERNET",
            "android.permission.ACCESS_FINE_LOCATION",
        ]
    }
]

def run_adb(cmd_args, check=True):
    full_cmd = [ADB_BIN, "-s", "emulator-5554"] + cmd_args
    return subprocess.run(full_cmd, capture_output=True, text=True, check=check)

def compile_shared_dex():
    """Compiles a single, fast self-finishing Activity DEX that is shared across all APKs."""
    os.makedirs(f"{BUILD_CACHE_DIR}/src/com/android/app", exist_ok=True)
    os.makedirs(f"{BUILD_CACHE_DIR}/bin", exist_ok=True)
    os.makedirs(f"{BUILD_CACHE_DIR}/dex", exist_ok=True)

    activity_src = """package com.android.app;
import android.app.Activity;
import android.os.Bundle;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        finish();
    }
}
"""
    java_file = f"{BUILD_CACHE_DIR}/src/com/android/app/MainActivity.java"
    with open(java_file, "w") as f:
        f.write(activity_src)

    subprocess.run([JAVAC_BIN, "-cp", ANDROID_JAR, "-d", f"{BUILD_CACHE_DIR}/bin", java_file], check=True)
    subprocess.run([D8_BIN, "--lib", ANDROID_JAR, "--output", f"{BUILD_CACHE_DIR}/dex", f"{BUILD_CACHE_DIR}/bin/com/android/app/MainActivity.class"], check=True)
    return f"{BUILD_CACHE_DIR}/dex/classes.dex"

def build_single_apk(app_info, shared_dex):
    pkg = app_info["package"]
    app_dir = os.path.join(BUILD_CACHE_DIR, "apks", pkg)
    os.makedirs(app_dir, exist_ok=True)

    perms_xml = "\n".join([f'    <uses-permission android:name="{p}" />' for p in app_info.get("permissions", [])])
    game_attrs = 'android:isGame="true" android:appCategory="game"' if app_info["is_game"] else ""

    manifest = f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{pkg}"
    android:versionCode="{app_info['version_code']}"
    android:versionName="{app_info['version_name']}">
    <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="34" />
{perms_xml}
    <application android:label="{app_info['name']}" {game_attrs} android:theme="@android:style/Theme.Translucent.NoTitleBar">
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

    return signed_apk

def get_installed_packages():
    res = run_adb(["shell", "pm", "list", "packages", "-3"], check=False)
    pkgs = set()
    for line in res.stdout.splitlines():
        if line.startswith("package:"):
            pkgs.add(line.split(":")[1].strip())
    return pkgs

def get_all_known_packages():
    res = run_adb(["shell", "pm", "list", "packages", "-u", "-3"], check=False)
    pkgs = set()
    for line in res.stdout.splitlines():
        if line.startswith("package:"):
            pkgs.add(line.split(":")[1].strip())
    return pkgs

def set_device_time(epoch_ms):
    run_adb(["shell", "cmd", "alarm", "set-time", str(epoch_ms)], check=True)

def populate_filesystem_remnants():
    """Creates authentic app data directories and remnants on /sdcard/."""
    print("📁 Creating realistic filesystem directories & cache remnants...")
    dirs_to_create = [
        "/sdcard/Android/data/com.whatsapp/cache",
        "/sdcard/Android/data/com.whatsapp/files",
        "/sdcard/WhatsApp/Media/WhatsApp Images/Sent",
        "/sdcard/WhatsApp/Media/WhatsApp Documents",
        "/sdcard/WhatsApp/Media/WhatsApp Audio",
        "/sdcard/Android/data/com.instagram.android/cache",
        "/sdcard/Android/data/com.pubg.imobile/files/UE4Game/ShadowTrackerExtra/Saved",
        "/sdcard/Android/data/com.dts.freefiremax/files",
        "/sdcard/Android/data/com.kiloo.subwaysurf/files",
        "/sdcard/Android/data/com.ludo.king/cache",
        "/sdcard/Android/data/com.spotify.music/cache",
        "/sdcard/Android/data/com.phonepe.app/cache",
        # Uninstalled app residual directories (simulates normal uninstallation leftovers)
        "/sdcard/Android/data/com.imangi.templerun2/cache",
        "/sdcard/Android/data/com.fingersoft.hillclimb/cache",
        "/sdcard/Android/data/com.rovio.baba/cache",
        "/sdcard/Android/data/com.dreamplug.androidapp/cache",
        "/sdcard/Android/data/com.cards.slice/cache",
    ]
    for d in dirs_to_create:
        run_adb(["shell", "mkdir", "-p", d], check=False)

def simulate_app_usage(real_now_ms):
    """Simulates realistic daily and weekly usage across installed apps."""
    print("⚡ Simulating realistic UsageStatsManager events across historical dates...")
    active_apps = [a for a in APP_CATALOG if a["status"] == "INSTALLED"]

    # Sample days: 14 days ago, 7 days ago, 3 days ago, 1 day ago, today
    historical_days = [14, 7, 3, 1, 0]

    for days_ago in historical_days:
        # Base timestamp for this day (around 10:00 AM to 8:00 PM)
        day_base_ms = real_now_ms - (days_ago * 86400 * 1000)
        
        # Pick 8-12 apps used on this day
        daily_sample = random.sample(active_apps, min(len(active_apps), random.randint(10, 16)))
        
        for app in daily_sample:
            pkg = app["package"]
            # Spread launches across the day
            launch_time = day_base_ms + random.randint(3600 * 9, 3600 * 20) * 1000
            set_device_time(launch_time)
            
            # Start activity (translucent, closes immediately in 50ms)
            run_adb(["shell", "am", "start", "-n", f"{pkg}/com.android.app.MainActivity"], check=False)
            time.sleep(0.08)

    # Enforce extra gaming activity for Battlegrounds Mobile India (BGMI)
    for g_days in [6, 4, 2, 0]:
        g_time = real_now_ms - (g_days * 86400 * 1000) + (19 * 3600 * 1000)
        set_device_time(g_time)
        run_adb(["shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", "com.pubg.imobile"], check=False)
        time.sleep(0.1)
        run_adb(["shell", "am", "start", "-c", "android.intent.category.HOME", "-a", "android.intent.action.MAIN"], check=False)

def run_app_history_pipeline():
    print("==================================================================")
    print("    🚀 AURA OS — Authentic Mobile Ecosystem & App History        ")
    print("==================================================================")

    # 1. Verify ADB connection
    state = run_adb(["get-state"], check=False).stdout.strip()
    if state != "device":
        print(f"❌ Error: Android emulator (emulator-5554) is not online. State: {state}")
        sys.exit(1)
    print("✅ Android emulator connected and responsive.")

    # 2. Capture real current time to restore at the end
    real_time_ms = int(time.time() * 1000)
    print(f"🕒 Captured Host Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(real_time_ms / 1000))}")

    try:
        # 3. Compile shared DEX
        print("🔨 Compiling high-speed shared Activity DEX...")
        shared_dex = compile_shared_dex()

        installed_pkgs = get_installed_packages()
        all_known_pkgs = get_all_known_packages()

        installed_count = 0
        uninstalled_count = 0
        games_count = 0

        # 4. Process all apps
        total_apps = len(APP_CATALOG)
        for i, app in enumerate(APP_CATALOG, 1):
            pkg = app["package"]
            name = app["name"]
            status = app["status"]
            is_game = app["is_game"]
            if is_game:
                games_count += 1

            # Skip building if already properly installed (unless it's an uninstalled target that is currently installed)
            if status == "INSTALLED" and pkg in installed_pkgs:
                print(f"[{i}/{total_apps}] ⏩ {name} ({pkg}) is already installed.")
                installed_count += 1
                continue

            # Build APK
            apk_path = build_single_apk(app, shared_dex)

            # Calculate authentic firstInstallTime
            install_time_ms = real_time_ms - (app["install_days_ago"] * 86400 * 1000) + random.randint(10000, 50000)
            set_device_time(install_time_ms)

            # Install with Google Play Store as provenance installer
            run_adb(["install", "-r", "-i", "com.android.vending", apk_path], check=True)

            if status == "INSTALLED":
                # Apply lastUpdateTime if recent update simulated
                if "update_days_ago" in app:
                    update_time_ms = real_time_ms - (app["update_days_ago"] * 86400 * 1000) + random.randint(1000, 5000)
                    set_device_time(update_time_ms)
                    # Trigger update timestamp via reinstall
                    run_adb(["install", "-r", "-i", "com.android.vending", apk_path], check=True)

                tag = "🎮 [Game]" if is_game else "📱 [App]"
                print(f"[{i}/{total_apps}] ✅ Installed {tag} {name} (Install Date: {app['install_days_ago']}d ago)")
                installed_count += 1

            elif status == "UNINSTALLED":
                # Uninstall at uninstall_days_ago with -k flag so it persists in uninstalled history
                uninstall_time_ms = real_time_ms - (app["uninstall_days_ago"] * 86400 * 1000) + random.randint(1000, 5000)
                set_device_time(uninstall_time_ms)
                run_adb(["shell", "pm", "uninstall", "-k", pkg], check=True)
                tag = "🎮 [Game History]" if is_game else "📱 [App History]"
                print(f"[{i}/{total_apps}] 🗑️  Uninstalled {tag} {name} (Installed: {app['install_days_ago']}d ago, Uninstalled: {app['uninstall_days_ago']}d ago)")
                uninstalled_count += 1

        # 5. Simulate multi-day usage for UsageStatsManager
        simulate_app_usage(real_time_ms)

        # 6. Populate filesystem remnants
        populate_filesystem_remnants()

        # 7. Print summary statistics
        print("\n" + "=" * 66)
        print("✨ APP HISTORY & ECOSYSTEM GENERATION COMPLETE!")
        print("=" * 66)
        print(f"  • Total Active Installed Apps:     {installed_count}")
        print(f"  • Total Uninstalled App Histories: {uninstalled_count}")
        print(f"  • Total Game Applications:         {games_count}")
        print(f"  • Play Store Provenance:           com.android.vending (100%)")
        print(f"  • Multi-Day UsageStats Events:     Simulated across 14+ days")
        print("=" * 66 + "\n")

    finally:
        # ALWAYS restore real host clock
        print("🕒 Restoring exact system clock to real time...")
        set_device_time(real_time_ms)
        date_res = run_adb(["shell", "date"], check=False).stdout.strip()
        print(f"✅ Device System Clock Restored: {date_res}")

def verify_app_history():
    print("\n🔍 --- AUDIT / VERIFICATION OF DEVICE APP HISTORIES ---")
    res_inst = run_adb(["shell", "pm", "list", "packages", "-3"], check=False).stdout
    res_all = run_adb(["shell", "pm", "list", "packages", "-u", "-3"], check=False).stdout
    
    inst_pkgs = set(l.split(":")[1].strip() for l in res_inst.splitlines() if l.startswith("package:"))
    all_pkgs = set(l.split(":")[1].strip() for l in res_all.splitlines() if l.startswith("package:"))
    uninst_pkgs = all_pkgs - inst_pkgs

    print(f"📊 Currently Installed Third-Party Packages: {len(inst_pkgs)}")
    print(f"📊 Historical Uninstalled Packages (pm -u):   {len(uninst_pkgs)}")

    print("\n📦 Active Installed Apps Sample:")
    for p in sorted(list(inst_pkgs))[:10]:
        print(f"   • {p}")
    if len(inst_pkgs) > 10:
        print(f"   ... and {len(inst_pkgs) - 10} more.")

    print("\n🗑️ Uninstalled App Histories (MATCH_UNINSTALLED_PACKAGES):")
    for p in sorted(list(uninst_pkgs)):
        print(f"   • {p}")

    print("\n🕹️ Inspecting Game Flags (isGameApp):")
    for app in APP_CATALOG:
        if app["is_game"]:
            status_sym = "✅ Active" if app["package"] in inst_pkgs else "🗑️ Uninstalled History"
            print(f"   • {app['name']} ({app['package']}) -> {status_sym}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify_app_history()
    else:
        run_app_history_pipeline()
        verify_app_history()
