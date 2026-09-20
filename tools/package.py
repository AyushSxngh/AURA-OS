import os
import shutil
import zipfile

dist_dir = r"c:\Users\ayush\Desktop\EMULATOR\dist"
release_bin_dir = r"c:\Users\ayush\Desktop\EMULATOR\target\release"
package_folder = os.path.join(dist_dir, "AURA_OS_v1.0.0_windows_x86_64")

os.makedirs(package_folder, exist_ok=True)
bin_folder = os.path.join(package_folder, "bin")
docs_folder = os.path.join(package_folder, "docs")
os.makedirs(bin_folder, exist_ok=True)
os.makedirs(docs_folder, exist_ok=True)

# Copy Binaries
cli_exe = os.path.join(release_bin_dir, "aura-cli.exe")
gui_exe = os.path.join(release_bin_dir, "aura-gui.exe")

if os.path.exists(cli_exe):
    shutil.copy2(cli_exe, bin_folder)
    print(f"Copied aura-cli.exe ({os.path.getsize(cli_exe) / (1024*1024):.2f} MB)")

if os.path.exists(gui_exe):
    shutil.copy2(gui_exe, bin_folder)
    print(f"Copied aura-gui.exe ({os.path.getsize(gui_exe) / (1024*1024):.2f} MB)")

# Copy Documentation
for doc in ["ARCHITECTURE.md", "SETUP.md"]:
    src = os.path.join(r"c:\Users\ayush\Desktop\EMULATOR\docs", doc)
    if os.path.exists(src):
        shutil.copy2(src, docs_folder)

# Copy Assets
assets_src = r"c:\Users\ayush\Desktop\EMULATOR\launcher\ui\assets"
assets_dst = os.path.join(package_folder, "assets")
if os.path.exists(assets_src):
    shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)

# Create Launch Shortcuts/Scripts
run_gui_bat = os.path.join(package_folder, "Launch-AURA-OS.bat")
with open(run_gui_bat, "w") as f:
    f.write("@echo off\r\nstart \"\" \"%~dp0bin\\aura-gui.exe\"\r\n")

run_cli_bat = os.path.join(package_folder, "Launch-CLI.bat")
with open(run_cli_bat, "w") as f:
    f.write("@echo off\r\ncmd /k \"%~dp0bin\\aura-cli.exe help\"\r\n")

readme_path = os.path.join(package_folder, "README.txt")
with open(readme_path, "w") as f:
    f.write(
        "====================================================\r\n"
        "      AURA OS — Android Virtualization Platform     \r\n"
        "      Release v1.0.0 (Windows x86-64)               \r\n"
        "====================================================\r\n\r\n"
        "QUICK START:\r\n"
        "1. Double-click 'Launch-AURA-OS.bat' to launch the Native Desktop GUI.\r\n"
        "2. Double-click 'Launch-CLI.bat' for terminal-based operations.\r\n\r\n"
        "SYSTEM REQUIREMENTS:\r\n"
        "- Windows 10/11 64-bit\r\n"
        "- Windows Hypervisor Platform (WHPX) enabled\r\n"
        "- Android SDK with Platform-Tools and Emulator\r\n"
    )

# Create Zip Archive
zip_dest = os.path.join(dist_dir, "AURA_OS_v1.0.0_windows_x86_64.zip")
with zipfile.ZipFile(zip_dest, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(package_folder):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, package_folder)
            zf.write(full_path, rel_path)

print(f"Distribution package created at: {zip_dest}")
print(f"Archive Size: {os.path.getsize(zip_dest) / (1024*1024):.2f} MB")
