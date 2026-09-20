use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum GraphicsBackend {
    GfxStream,
    Host,
    SwiftShader,
    Angle,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum GuestAbi {
    X86_64,
    Arm64V8a,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VirtualDeviceConfig {
    pub name: String,
    pub ram_mb: u32,
    pub cpu_cores: u32,
    pub width: u32,
    pub height: u32,
    pub density_dpi: u32,
    pub disk_size_mb: u32,
    pub abi: GuestAbi,
    pub graphics_backend: GraphicsBackend,
    pub enable_camera: bool,
    pub enable_audio: bool,
}

impl Default for VirtualDeviceConfig {
    fn default() -> Self {
        let (name, abi) = if cfg!(target_arch = "aarch64") {
            ("AURA_OS_ARM64".to_string(), GuestAbi::Arm64V8a)
        } else {
            ("AURA_OS_x86_64".to_string(), GuestAbi::X86_64)
        };

        Self {
            name,
            ram_mb: 8192,
            cpu_cores: 6,
            width: 1920,
            height: 1080,
            density_dpi: 240,
            disk_size_mb: 32768,
            abi,
            graphics_backend: GraphicsBackend::Host,
            enable_camera: true,
            enable_audio: true,
        }
    }
}

impl VirtualDeviceConfig {
    pub fn validate(&self) -> Result<(), String> {
        if self.name.trim().is_empty() {
            return Err("Device name cannot be empty.".to_string());
        }
        if self.ram_mb < 1024 {
            return Err("RAM must be at least 1024 MB.".to_string());
        }
        if self.cpu_cores < 1 {
            return Err("CPU cores must be at least 1.".to_string());
        }
        if self.disk_size_mb < 4096 {
            return Err("Disk size must be at least 4096 MB.".to_string());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_device_config_default_and_validate() {
        let config = VirtualDeviceConfig::default();
        assert!(config.validate().is_ok());

        let invalid_config = VirtualDeviceConfig {
            ram_mb: 512,
            ..Default::default()
        };
        assert!(invalid_config.validate().is_err());
    }
}
