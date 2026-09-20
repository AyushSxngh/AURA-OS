use aura_launcher_core::{silent_command, VirtualDeviceConfig};
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::process::Child;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum EmulatorError {
    #[error("Emulator binary not found at '{0}'")]
    NotFound(PathBuf),
    #[error("AVD '{0}' not found")]
    AvdNotFound(String),
    #[error("Failed to execute command: {0}")]
    ExecutionFailed(String),
    #[error("AVD creation failed: {0}")]
    CreationFailed(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VmBootState {
    Stopped,
    Booting,
    Running,
    Error(String),
}

pub struct AuraVmManager {
    emulator_path: PathBuf,
    sdk_root: Option<PathBuf>,
}

impl AuraVmManager {
    pub fn new(emulator_path: PathBuf, sdk_root: Option<PathBuf>) -> Self {
        Self { emulator_path, sdk_root }
    }

    pub fn sdk_root(&self) -> Option<&PathBuf> {
        self.sdk_root.as_ref()
    }

    pub fn list_avds(&self) -> Result<Vec<String>, EmulatorError> {
        let output = silent_command(&self.emulator_path)
            .arg("-list-avds")
            .output()
            .map_err(|e| EmulatorError::ExecutionFailed(e.to_string()))?;

        if output.status.success() {
            let stdout = String::from_utf8_lossy(&output.stdout);
            Ok(stdout.lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect())
        } else {
            Err(EmulatorError::ExecutionFailed(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    pub fn get_avd_storage_dir(&self) -> PathBuf {
        if let Ok(custom) = std::env::var("ANDROID_AVD_HOME") {
            let p = PathBuf::from(custom);
            if p.exists() || fs::create_dir_all(&p).is_ok() {
                return p;
            }
        }
        // Prefer Local Disk D: for massive storage (180+ GB free)
        let drive_d = PathBuf::from(r"D:\AURA_OS_DATA\avd");
        if std::path::Path::new(r"D:\").exists() {
            let _ = fs::create_dir_all(&drive_d);
            return drive_d;
        }
        let home = std::env::var("USERPROFILE")
            .or_else(|_| std::env::var("HOME"))
            .unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".android").join("avd")
    }

    pub fn avd_exists(&self, avd_name: &str) -> bool {
        match self.list_avds() {
            Ok(avds) => avds.iter().any(|name| name.to_lowercase() == avd_name.to_lowercase()),
            Err(_) => false,
        }
    }

    pub fn create_avd(&self, name: &str, package: &str) -> Result<(), EmulatorError> {
        let avd_root = self.get_avd_storage_dir();
        if !avd_root.exists() {
            fs::create_dir_all(&avd_root)
                .map_err(|e| EmulatorError::CreationFailed(format!("Failed to create AVD root: {}", e)))?;
        }

        let avd_dir = avd_root.join(format!("{}.avd", name));
        fs::create_dir_all(&avd_dir)
            .map_err(|e| EmulatorError::CreationFailed(format!("Failed to create AVD dir: {}", e)))?;

        let ini_content = format!(
            "avd.ini.encoding=UTF-8\npath={}\npath.rel=avd\\{}.avd\ntarget=android-34\n",
            avd_dir.display(),
            name
        );

        // Write ini to storage directory
        let ini_path = avd_root.join(format!("{}.ini", name));
        let mut ini_file = fs::File::create(&ini_path)
            .map_err(|e| EmulatorError::CreationFailed(format!("Failed to write {}.ini: {}", name, e)))?;
        let _ = ini_file.write_all(ini_content.as_bytes());

        // Also write ini to %USERPROFILE%\.android\avd so default emulator command finds it
        if let Ok(home) = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")) {
            let user_avd_root = PathBuf::from(home).join(".android").join("avd");
            if user_avd_root.exists() || fs::create_dir_all(&user_avd_root).is_ok() {
                let user_ini_path = user_avd_root.join(format!("{}.ini", name));
                if let Ok(mut f) = fs::File::create(&user_ini_path) {
                    let _ = f.write_all(ini_content.as_bytes());
                }
            }
        }

        // Try avdmanager if available
        if let Some(sdk_root) = &self.sdk_root {
            let exe_name = if cfg!(target_os = "windows") { "avdmanager.bat" } else { "avdmanager" };
            let avdmanager = sdk_root.join("cmdline-tools").join("latest").join("bin").join(exe_name);

            if avdmanager.exists() {
                let mut cmd = silent_command(&avdmanager);
                if cfg!(target_os = "windows") {
                    let jbr_path = r"C:\Program Files\Android\Android Studio\jbr";
                    if PathBuf::from(jbr_path).exists() {
                        cmd.env("JAVA_HOME", jbr_path);
                    }
                }
                if let Ok(mut child) = cmd
                    .arg("create")
                    .arg("avd")
                    .arg("-n")
                    .arg(name)
                    .arg("-k")
                    .arg(package)
                    .arg("--force")
                    .stdin(std::process::Stdio::piped())
                    .spawn()
                {
                    if let Some(mut stdin) = child.stdin.take() {
                        let _ = stdin.write_all(b"no\n");
                    }
                    let _ = child.wait();
                }
            }
        }

        Ok(())
    }

    pub fn configure_avd_ini(&self, avd_name: &str, config: &VirtualDeviceConfig) -> Result<(), EmulatorError> {
        let avd_root = self.get_avd_storage_dir();
        let avd_dir = avd_root.join(format!("{}.avd", avd_name));
        
        if !avd_dir.exists() {
            fs::create_dir_all(&avd_dir)
                .map_err(|e| EmulatorError::CreationFailed(format!("Failed to create AVD directory: {}", e)))?;
        }

        let is_arm = config.abi == aura_launcher_core::GuestAbi::Arm64V8a || cfg!(target_arch = "aarch64");
        let (abi_type, cpu_arch, arch_dir) = if is_arm {
            ("arm64-v8a", "arm64", "arm64-v8a")
        } else {
            ("x86_64", "x86_64", "x86_64")
        };

        // Check whether google_apis_playstore or google_apis exists for this architecture
        let (sysdir, tag_id, tag_display, has_playstore) = if let Some(sdk) = &self.sdk_root {
            let playstore_path = sdk.join("system-images").join("android-34").join("google_apis_playstore").join(arch_dir);
            let google_apis_path = sdk.join("system-images").join("android-34").join("google_apis").join(arch_dir);

            if playstore_path.exists() {
                let mut p = playstore_path.display().to_string();
                if !p.ends_with(std::path::MAIN_SEPARATOR) {
                    p.push(std::path::MAIN_SEPARATOR);
                }
                (p, "google_apis_playstore", "Google Play", true)
            } else if google_apis_path.exists() {
                let mut p = google_apis_path.display().to_string();
                if !p.ends_with(std::path::MAIN_SEPARATOR) {
                    p.push(std::path::MAIN_SEPARATOR);
                }
                (p, "google_apis", "Google APIs", false)
            } else {
                let rel = format!("system-images{}android-34{}google_apis_playstore{}{}",
                    std::path::MAIN_SEPARATOR, std::path::MAIN_SEPARATOR,
                    std::path::MAIN_SEPARATOR, std::path::MAIN_SEPARATOR);
                (format!("{}{}", sdk.display(), std::path::MAIN_SEPARATOR) + &rel, "google_apis_playstore", "Google Play", true)
            }
        } else {
            (String::new(), "google_apis_playstore", "Google Play", true)
        };

        let config_ini_path = avd_dir.join("config.ini");
        let ini_content = format!(
            "AvdId={name}
PlayStore.enabled={playstore}
abi.type={abi_type}
avd.ini.displayname={name}
avd.ini.encoding=UTF-8
disk.dataPartition.size={disk}M
fastboot.chosenSnapshotFile=
fastboot.forceChosenSnapshotBoot=no
fastboot.forceFastBoot=yes
fastboot.forceSnapshotBoot=no
hw.accelerometer=yes
hw.audioInput=yes
hw.audioOutput=yes
hw.battery=yes
hw.camera.back=webcam0
hw.camera.front=webcam0
hw.cpu.arch={cpu_arch}
hw.cpu.ncore={cores}
hw.dPad=no
hw.device.manufacturer=AURA OS Platform
hw.device.name=aura_desktop
hw.gps=yes
hw.gpu.enabled=yes
hw.gpu.mode=host
hw.initialOrientation=Landscape
hw.keyboard=yes
hw.lcd.density={dpi}
hw.lcd.height={height}
hw.lcd.width={width}
hw.lcd.vsync=120
hw.mainKeys=no
hw.ramSize={ram}
hw.sdCard=yes
hw.sensors.orientation=yes
hw.sensors.proximity=yes
hw.trackBall=no
image.sysdir.1={sysdir}
runtime.network.latency=none
runtime.network.speed=full
showDeviceFrame=no
skin.dynamic=yes
skin.name=1920x1080
tag.display={tag_display}
tag.id={tag_id}
vm.heapSize=1024
",
            name = avd_name,
            playstore = if has_playstore { "true" } else { "false" },
            abi_type = abi_type,
            cpu_arch = cpu_arch,
            disk = config.disk_size_mb,
            cores = config.cpu_cores,
            dpi = config.density_dpi,
            height = config.height,
            width = config.width,
            ram = config.ram_mb,
            sysdir = sysdir,
            tag_display = tag_display,
            tag_id = tag_id,
        );

        let mut file = fs::File::create(&config_ini_path)
            .map_err(|e| EmulatorError::CreationFailed(format!("Failed to write config.ini: {}", e)))?;
        file.write_all(ini_content.as_bytes())
            .map_err(|e| EmulatorError::CreationFailed(format!("Failed to save config.ini: {}", e)))?;

        Ok(())
    }

    pub fn build_launch_args(&self, config: &VirtualDeviceConfig) -> Vec<String> {
        let mut args = vec![
            "-avd".to_string(),
            config.name.clone(),
            "-memory".to_string(),
            config.ram_mb.to_string(),
            "-cores".to_string(),
            config.cpu_cores.to_string(),
            "-accel".to_string(),
            "auto".to_string(),
            "-vsync-rate".to_string(),
            "120".to_string(),
        ];

        args.push("-gpu".to_string());
        args.push("host".to_string());

        if config.enable_camera {
            args.push("-camera-back".to_string());
            args.push("webcam0".to_string());
        }

        args
    }

    pub fn start_vm(&self, config: &VirtualDeviceConfig) -> Result<Child, EmulatorError> {
        self.start_vm_with_port(config, None)
    }

    pub fn start_vm_with_port(&self, config: &VirtualDeviceConfig, port: Option<u16>) -> Result<Child, EmulatorError> {
        if !self.avd_exists(&config.name) {
            return Err(EmulatorError::AvdNotFound(config.name.clone()));
        }

        let mut args = self.build_launch_args(config);
        if let Some(p) = port {
            args.push("-port".to_string());
            args.push(p.to_string());
        }

        let avd_dir = self.get_avd_storage_dir();
        std::process::Command::new(&self.emulator_path)
            .args(&args)
            .env("ANDROID_AVD_HOME", &avd_dir)
            .spawn()
            .map_err(|e| EmulatorError::ExecutionFailed(format!("Failed to spawn emulator process: {}", e)))
    }

    pub fn delete_avd(&self, avd_name: &str) -> Result<(), EmulatorError> {
        let storage_root = self.get_avd_storage_dir();
        let s_ini = storage_root.join(format!("{}.ini", avd_name));
        let s_dir = storage_root.join(format!("{}.avd", avd_name));
        if s_ini.exists() {
            let _ = fs::remove_file(s_ini);
        }
        if s_dir.exists() {
            let _ = fs::remove_dir_all(s_dir);
        }

        if let Ok(home) = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")) {
            let user_root = PathBuf::from(home).join(".android").join("avd");
            let u_ini = user_root.join(format!("{}.ini", avd_name));
            let u_dir = user_root.join(format!("{}.avd", avd_name));
            if u_ini.exists() {
                let _ = fs::remove_file(u_ini);
            }
            if u_dir.exists() {
                let _ = fs::remove_dir_all(u_dir);
            }
        }
        Ok(())
    }

    pub fn clone_avd(&self, _src_name: &str, new_name: &str) -> Result<(), EmulatorError> {
        let mut config = VirtualDeviceConfig::default();
        config.name = new_name.to_string();
        let is_arm = cfg!(target_arch = "aarch64") || config.abi == aura_launcher_core::GuestAbi::Arm64V8a;
        let arch_str = if is_arm { "arm64-v8a" } else { "x86_64" };

        let pkg = if let Some(sdk) = &self.sdk_root {
            if sdk.join("system-images").join("android-34").join("google_apis_playstore").join(arch_str).exists() {
                format!("system-images;android-34;google_apis_playstore;{}", arch_str)
            } else if sdk.join("system-images").join("android-34").join("google_apis").join(arch_str).exists() {
                format!("system-images;android-34;google_apis;{}", arch_str)
            } else {
                format!("system-images;android-34;google_apis_playstore;{}", arch_str)
            }
        } else {
            format!("system-images;android-34;google_apis_playstore;{}", arch_str)
        };
        self.create_avd(new_name, &pkg)?;
        self.configure_avd_ini(new_name, &config)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aura_launcher_core::ToolchainInfo;

    #[test]
    fn test_emulator_manager_build_args() {
        let tc = ToolchainInfo::detect();
        if let Some(emu_path) = tc.emulator_path {
            let manager = AuraVmManager::new(emu_path, tc.sdk_root);
            let config = VirtualDeviceConfig::default();
            let args = manager.build_launch_args(&config);
            assert!(args.contains(&"-avd".to_string()));
            assert!(args.contains(&"AURA_OS_x86_64".to_string()));
            assert!(args.contains(&"-camera-back".to_string()));
        }
    }
}
