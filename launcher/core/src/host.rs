use serde::{Deserialize, Serialize};
use sysinfo::System;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum HostOs {
    Windows,
    MacOS,
    Linux,
    Unknown(String),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum HostArch {
    X86_64,
    AArch64,
    Unknown(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HostInfo {
    pub os: HostOs,
    pub os_version: String,
    pub arch: HostArch,
    pub cpu_brand: String,
    pub logical_cores: usize,
    pub physical_cores: Option<usize>,
    pub total_memory_mb: u64,
    pub available_memory_mb: u64,
}

impl HostInfo {
    pub fn detect() -> Self {
        let os = if cfg!(target_os = "windows") {
            HostOs::Windows
        } else if cfg!(target_os = "macos") {
            HostOs::MacOS
        } else if cfg!(target_os = "linux") {
            HostOs::Linux
        } else {
            HostOs::Unknown(std::env::consts::OS.to_string())
        };

        let arch = if cfg!(target_arch = "x86_64") {
            HostArch::X86_64
        } else if cfg!(target_arch = "aarch64") {
            HostArch::AArch64
        } else {
            HostArch::Unknown(std::env::consts::ARCH.to_string())
        };

        let sys = System::new_with_specifics(
            sysinfo::RefreshKind::new()
                .with_cpu(sysinfo::CpuRefreshKind::everything())
                .with_memory(sysinfo::MemoryRefreshKind::everything()),
        );

        let cpu_brand = sys
            .cpus()
            .first()
            .map(|c| c.brand().trim().to_string())
            .unwrap_or_else(|| "Unknown CPU".to_string());

        let logical_cores = sys.cpus().len();
        let physical_cores = sys.physical_core_count();

        let total_memory_mb = sys.total_memory() / (1024 * 1024);
        let available_memory_mb = sys.available_memory() / (1024 * 1024);

        let os_version = System::os_version().unwrap_or_else(|| "Unknown OS Version".to_string());

        Self {
            os,
            os_version,
            arch,
            cpu_brand,
            logical_cores,
            physical_cores,
            total_memory_mb,
            available_memory_mb,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_host_info_detection() {
        let info = HostInfo::detect();
        assert_ne!(info.os, HostOs::Unknown("".to_string()));
        assert_ne!(info.arch, HostArch::Unknown("".to_string()));
        assert!(info.logical_cores > 0);
        assert!(info.total_memory_mb > 0);
    }
}
