use crate::accel::{AccelInfo, HypervisorType};
use crate::host::HostInfo;
use crate::toolchain::ToolchainInfo;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlatformStatusReport {
    pub host: HostInfo,
    pub accel: AccelInfo,
    pub toolchain: ToolchainInfo,
    pub is_ready_for_virtualization: bool,
    pub actionable_warnings: Vec<String>,
    pub actionable_errors: Vec<String>,
}

impl PlatformStatusReport {
    pub fn fast_detect() -> Self {
        let host = HostInfo::detect();
        let toolchain = ToolchainInfo::fast_detect();
        let accel = AccelInfo::detect(None);

        let is_ready = toolchain.sdk_root.is_some() && toolchain.adb_path.is_some() && toolchain.emulator_path.is_some();

        Self {
            host,
            accel,
            toolchain,
            is_ready_for_virtualization: is_ready,
            actionable_warnings: Vec::new(),
            actionable_errors: Vec::new(),
        }
    }

    pub fn generate() -> Self {
        let host = HostInfo::detect();
        let toolchain = ToolchainInfo::detect();
        let accel = AccelInfo::detect(toolchain.emulator_path.as_deref());

        let mut warnings = Vec::new();
        let mut errors = Vec::new();

        if toolchain.sdk_root.is_none() {
            errors.push("Android SDK root was not found. Please install Android Studio or set ANDROID_HOME environment variable.".to_string());
        }

        if toolchain.adb_path.is_none() {
            errors.push("Android Debug Bridge (adb.exe) was not found in Android SDK platform-tools.".to_string());
        }

        if toolchain.emulator_path.is_none() {
            errors.push("Android Emulator (emulator.exe) was not found in Android SDK emulator directory.".to_string());
        }

        if toolchain.jdk_path.is_none() {
            warnings.push("Java Development Kit (JDK) not detected in standard system locations.".to_string());
        }

        if accel.hypervisor == HypervisorType::None || !accel.is_enabled {
            warnings.push("Hardware virtualization acceleration (WHPX / KVM / HVF) is not enabled. Virtual machine execution may be slow.".to_string());
        }

        if toolchain.installed_avds.is_empty() {
            warnings.push("No Android Virtual Devices (AVD) are currently configured. Use Phase 2 setup commands to initialize an AURA OS image.".to_string());
        }

        let is_ready = errors.is_empty() && accel.is_enabled;

        Self {
            host,
            accel,
            toolchain,
            is_ready_for_virtualization: is_ready,
            actionable_warnings: warnings,
            actionable_errors: errors,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::host::HostOs;

    #[test]
    fn test_platform_status_report_generation() {
        let report = PlatformStatusReport::generate();
        if cfg!(target_os = "windows") {
            assert_eq!(report.host.os, HostOs::Windows);
        } else if cfg!(target_os = "macos") {
            assert_eq!(report.host.os, HostOs::MacOS);
        } else {
            assert_eq!(report.host.os, HostOs::Linux);
        }
    }
}
