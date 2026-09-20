use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolchainInfo {
    pub sdk_root: Option<PathBuf>,
    pub adb_path: Option<PathBuf>,
    pub adb_version: Option<String>,
    pub emulator_path: Option<PathBuf>,
    pub emulator_version: Option<String>,
    pub jdk_path: Option<PathBuf>,
    pub jdk_version: Option<String>,
    pub installed_platforms: Vec<String>,
    pub installed_build_tools: Vec<String>,
    pub installed_avds: Vec<String>,
}

impl ToolchainInfo {
    pub fn fast_detect() -> Self {
        let sdk_root = Self::find_sdk_root();
        let adb_path = Self::find_adb_path_fast(&sdk_root);
        let emulator_path = Self::find_emulator_path_fast(&sdk_root);
        let jdk_path = Self::find_jdk_path_fast();

        let installed_platforms = Self::list_dir_names(sdk_root.as_ref().map(|p| p.join("platforms")));
        let installed_build_tools = Self::list_dir_names(sdk_root.as_ref().map(|p| p.join("build-tools")));
        let installed_avds = Vec::new();

        Self {
            sdk_root,
            adb_path,
            adb_version: None,
            emulator_path,
            emulator_version: None,
            jdk_path,
            jdk_version: None,
            installed_platforms,
            installed_build_tools,
            installed_avds,
        }
    }

    fn find_adb_path_fast(sdk_root: &Option<PathBuf>) -> Option<PathBuf> {
        let exe_name = if cfg!(target_os = "windows") { "adb.exe" } else { "adb" };
        if let Some(sdk) = sdk_root {
            let candidate = sdk.join("platform-tools").join(exe_name);
            if candidate.exists() {
                return Some(candidate);
            }
        }
        None
    }

    fn find_emulator_path_fast(sdk_root: &Option<PathBuf>) -> Option<PathBuf> {
        let exe_name = if cfg!(target_os = "windows") { "emulator.exe" } else { "emulator" };
        if let Some(sdk) = sdk_root {
            let candidate = sdk.join("emulator").join(exe_name);
            if candidate.exists() {
                return Some(candidate);
            }
        }
        None
    }

    fn find_jdk_path_fast() -> Option<PathBuf> {
        let java_exe = if cfg!(target_os = "windows") { "java.exe" } else { "java" };
        
        // Windows Android Studio JBR
        let jbr_win = PathBuf::from("C:\\Program Files\\Android\\Android Studio\\jbr\\bin").join(java_exe);
        if jbr_win.exists() {
            return Some(jbr_win);
        }

        // macOS Android Studio JBR
        let jbr_mac = PathBuf::from("/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin").join(java_exe);
        if jbr_mac.exists() {
            return Some(jbr_mac);
        }

        if let Ok(val) = std::env::var("JAVA_HOME") {
            let candidate = PathBuf::from(val).join("bin").join(java_exe);
            if candidate.exists() {
                return Some(candidate);
            }
        }

        let usr_bin = PathBuf::from("/usr/bin/java");
        if usr_bin.exists() {
            return Some(usr_bin);
        }

        None
    }

    pub fn detect() -> Self {
        let sdk_root = Self::find_sdk_root();
        let (adb_path, adb_version) = Self::find_adb(&sdk_root);
        let (emulator_path, emulator_version) = Self::find_emulator(&sdk_root);
        let (jdk_path, jdk_version) = Self::find_jdk();

        let installed_platforms = Self::list_dir_names(sdk_root.as_ref().map(|p| p.join("platforms")));
        let installed_build_tools = Self::list_dir_names(sdk_root.as_ref().map(|p| p.join("build-tools")));
        let installed_avds = Self::list_avds(emulator_path.as_ref());

        Self {
            sdk_root,
            adb_path,
            adb_version,
            emulator_path,
            emulator_version,
            jdk_path,
            jdk_version,
            installed_platforms,
            installed_build_tools,
            installed_avds,
        }
    }

    fn find_sdk_root() -> Option<PathBuf> {
        if let Ok(val) = std::env::var("ANDROID_HOME") {
            let p = PathBuf::from(val);
            if p.exists() {
                return Some(p);
            }
        }
        if let Ok(val) = std::env::var("ANDROID_SDK_ROOT") {
            let p = PathBuf::from(val);
            if p.exists() {
                return Some(p);
            }
        }
        if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
            let p = PathBuf::from(local_app_data).join("Android").join("Sdk");
            if p.exists() {
                return Some(p);
            }
        }
        if let Ok(home) = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")) {
            // macOS default SDK path
            let mac_path = PathBuf::from(&home).join("Library").join("Android").join("sdk");
            if mac_path.exists() {
                return Some(mac_path);
            }
            // Linux default SDK path
            let linux_path = PathBuf::from(&home).join("Android").join("Sdk");
            if linux_path.exists() {
                return Some(linux_path);
            }
            // Windows default fallback
            let win_path = PathBuf::from(&home).join("AppData").join("Local").join("Android").join("Sdk");
            if win_path.exists() {
                return Some(win_path);
            }
        }
        None
    }

    fn find_adb(sdk_root: &Option<PathBuf>) -> (Option<PathBuf>, Option<String>) {
        let exe_name = if cfg!(target_os = "windows") { "adb.exe" } else { "adb" };
        let mut adb_bin = None;

        if let Some(sdk) = sdk_root {
            let candidate = sdk.join("platform-tools").join(exe_name);
            if candidate.exists() {
                adb_bin = Some(candidate);
            }
        }

        if adb_bin.is_none() {
            if let Ok(output) = crate::silent_command(exe_name).arg("version").output() {
                if output.status.success() {
                    adb_bin = Some(PathBuf::from(exe_name));
                }
            }
        }

        let mut version = None;
        if let Some(ref path) = adb_bin {
            if let Ok(output) = crate::silent_command(path).arg("version").output() {
                let stdout = String::from_utf8_lossy(&output.stdout);
                if let Some(line) = stdout.lines().next() {
                    version = Some(line.trim().to_string());
                }
            }
        }

        (adb_bin, version)
    }

    fn find_emulator(sdk_root: &Option<PathBuf>) -> (Option<PathBuf>, Option<String>) {
        let exe_name = if cfg!(target_os = "windows") { "emulator.exe" } else { "emulator" };
        let mut emu_bin = None;

        if let Some(sdk) = sdk_root {
            let candidate = sdk.join("emulator").join(exe_name);
            if candidate.exists() {
                emu_bin = Some(candidate);
            }
        }

        let mut version = None;
        if let Some(ref path) = emu_bin {
            if let Ok(output) = crate::silent_command(path).arg("-version").output() {
                let stdout = String::from_utf8_lossy(&output.stdout);
                if let Some(line) = stdout.lines().next() {
                    version = Some(line.trim().to_string());
                }
            }
        }

        (emu_bin, version)
    }

    fn find_jdk() -> (Option<PathBuf>, Option<String>) {
        let java_exe = if cfg!(target_os = "windows") { "java.exe" } else { "java" };
        
        // Check Windows Android Studio JBR path
        let jbr_win = PathBuf::from("C:\\Program Files\\Android\\Android Studio\\jbr\\bin").join(java_exe);
        if jbr_win.exists() {
            let ver = Self::get_java_version(&jbr_win);
            return (Some(jbr_win), ver);
        }

        // Check macOS Android Studio JBR path
        let jbr_mac = PathBuf::from("/Applications/Android Studio.app/Contents/jbr/Contents/Home/bin").join(java_exe);
        if jbr_mac.exists() {
            let ver = Self::get_java_version(&jbr_mac);
            return (Some(jbr_mac), ver);
        }

        // Check JAVA_HOME
        if let Ok(val) = std::env::var("JAVA_HOME") {
            let candidate = PathBuf::from(val).join("bin").join(java_exe);
            if candidate.exists() {
                let ver = Self::get_java_version(&candidate);
                return (Some(candidate), ver);
            }
        }

        // Check system java
        let usr_bin = PathBuf::from("/usr/bin/java");
        if usr_bin.exists() {
            let ver = Self::get_java_version(&usr_bin);
            return (Some(usr_bin), ver);
        }

        (None, None)
    }

    fn get_java_version(path: &Path) -> Option<String> {
        if let Ok(output) = crate::silent_command(path).arg("-version").output() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            if let Some(line) = stderr.lines().next() {
                return Some(line.trim().to_string());
            }
        }
        None
    }

    fn list_dir_names(dir: Option<PathBuf>) -> Vec<String> {
        let mut res = Vec::new();
        if let Some(d) = dir {
            if let Ok(entries) = std::fs::read_dir(d) {
                for entry in entries.flatten() {
                    if let Ok(name) = entry.file_name().into_string() {
                        res.push(name);
                    }
                }
            }
        }
        res
    }

    fn list_avds(emulator_path: Option<&PathBuf>) -> Vec<String> {
        if let Some(path) = emulator_path {
            if let Ok(output) = crate::silent_command(path).arg("-list-avds").output() {
                let stdout = String::from_utf8_lossy(&output.stdout);
                return stdout.lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
            }
        }
        Vec::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_toolchain_detection() {
        let tc = ToolchainInfo::detect();
        assert!(tc.sdk_root.is_some(), "Android SDK root should be found");
        assert!(tc.adb_path.is_some(), "ADB path should be found");
        assert!(tc.emulator_path.is_some(), "Emulator path should be found");
        assert!(tc.jdk_path.is_some(), "JDK path should be found");
    }
}
