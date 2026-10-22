use aura_launcher_core::silent_command;
use std::path::PathBuf;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum AdbError {
    #[error("ADB binary not found")]
    NotFound,
    #[error("Command execution failed: {0}")]
    ExecutionFailed(String),
    #[error("ADB command error: {0}")]
    CommandError(String),
    #[error("Timeout waiting for boot completion")]
    BootTimeout,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdbDevice {
    pub serial: String,
    pub state: String,
}

pub struct AuraAdbClient {
    adb_path: PathBuf,
}

impl AuraAdbClient {
    pub fn new(adb_path: PathBuf) -> Self {
        Self { adb_path }
    }

    pub fn version(&self) -> Result<String, AdbError> {
        let output = silent_command(&self.adb_path)
            .arg("version")
            .output()
            .map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;

        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    pub fn list_devices(&self) -> Result<Vec<AdbDevice>, AdbError> {
        let output = silent_command(&self.adb_path)
            .arg("devices")
            .output()
            .map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;

        if !output.status.success() {
            return Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()));
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        let mut devices = Vec::new();

        for line in stdout.lines().skip(1) {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if parts.len() >= 2 {
                devices.push(AdbDevice {
                    serial: parts[0].to_string(),
                    state: parts[1].to_string(),
                });
            }
        }

        Ok(devices)
    }

    pub fn is_boot_completed(&self, device_serial: Option<&str>) -> bool {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("shell").arg("getprop").arg("sys.boot_completed");

        if let Ok(output) = cmd.output() {
            if output.status.success() {
                let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
                return stdout == "1";
            }
        }
        false
    }

    pub fn stop_emulator(&self, device_serial: Option<&str>) -> Result<(), AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("emu").arg("kill");

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(())
        } else {
            // Fallback: If ADB is offline or disabled, attempt graceful kill via console port
            if let Some(serial) = device_serial {
                if let Some(port_str) = serial.strip_prefix("emulator-") {
                    if let Ok(port) = port_str.parse::<u16>() {
                        if let Ok(mut stream) = std::net::TcpStream::connect_timeout(
                            &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
                            std::time::Duration::from_millis(300),
                        ) {
                            use std::io::{Read, Write};
                            let mut buf = [0u8; 1024];
                            let _ = stream.read(&mut buf);
                            if let Ok(home) = std::env::var("USERPROFILE").or_else(|_| std::env::var("HOME")) {
                                let token_file = std::path::PathBuf::from(home).join(".emulator_console_auth_token");
                                if let Ok(token) = std::fs::read_to_string(token_file) {
                                    let _ = stream.write_all(format!("auth {}\n", token.trim()).as_bytes());
                                    let _ = stream.read(&mut buf);
                                }
                            }
                            let _ = stream.write_all(b"kill\n");
                            return Ok(());
                        }
                    }
                }
            }
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    pub fn install_apk(&self, device_serial: Option<&str>, apk_path: &std::path::Path) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("install").arg("-r").arg(apk_path);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        if output.status.success() && stdout.contains("Success") {
            Ok(stdout.trim().to_string())
        } else {
            Err(AdbError::CommandError(format!("{}\n{}", stdout, stderr)))
        }
    }

    pub fn push_file(&self, device_serial: Option<&str>, local_path: &std::path::Path, remote_path: &str) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("push").arg(local_path).arg(remote_path);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        if output.status.success() {
            Ok(stdout.trim().to_string())
        } else {
            Err(AdbError::CommandError(format!("{}\n{}", stdout, stderr)))
        }
    }

    pub fn pull_file(&self, device_serial: Option<&str>, remote_path: &str, local_path: &std::path::Path) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("pull").arg(remote_path).arg(local_path);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        if output.status.success() {
            Ok(stdout.trim().to_string())
        } else {
            Err(AdbError::CommandError(format!("{}\n{}", stdout, stderr)))
        }
    }

    pub fn list_remote_images(&self, device_serial: Option<&str>) -> Result<Vec<String>, AdbError> {
        let cmd = "find /sdcard/Pictures /sdcard/DCIM /sdcard/Download -type f \\( -name '*.jpg' -o -name '*.png' -o -name '*.jpeg' -o -name '*.webp' \\) 2>/dev/null";
        let out = self.shell_command(device_serial, cmd)?;
        let files = out.lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
        Ok(files)
    }

    pub fn uninstall_apk(&self, device_serial: Option<&str>, package_name: &str) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("uninstall").arg(package_name);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);

        if output.status.success() && stdout.contains("Success") {
            Ok(stdout.trim().to_string())
        } else {
            Err(AdbError::CommandError(format!("{}\n{}", stdout, stderr)))
        }
    }

    pub fn list_packages(&self, device_serial: Option<&str>) -> Result<Vec<String>, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("shell").arg("pm").arg("list").arg("packages");

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if !output.status.success() {
            return Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()));
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        let pkgs = stdout
            .lines()
            .filter_map(|line| line.strip_prefix("package:").map(|s| s.trim().to_string()))
            .collect();
        Ok(pkgs)
    }

    pub fn shell_command(&self, device_serial: Option<&str>, command: &str) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("shell");
        for arg in command.split_whitespace() {
            cmd.arg(arg);
        }

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).to_string())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    pub fn raw_shell(&self, device_serial: Option<&str>, command: &str) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("shell").arg(command);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).to_string())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    pub fn get_apk_paths(&self, device_serial: Option<&str>, package_name: &str) -> Result<Vec<String>, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("shell").arg("pm").arg("path").arg(package_name);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if !output.status.success() {
            return Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()));
        }

        let stdout = String::from_utf8_lossy(&output.stdout);
        let paths: Vec<String> = stdout
            .lines()
            .filter_map(|line| line.strip_prefix("package:").map(|s| s.trim().to_string()))
            .filter(|s| !s.is_empty())
            .collect();

        if paths.is_empty() {
            return Err(AdbError::CommandError(format!("Package '{}' not found or has no APK installed", package_name)));
        }

        Ok(paths)
    }

    pub fn export_apk(&self, device_serial: Option<&str>, package_name: &str, local_dest: &std::path::Path) -> Result<PathBuf, AdbError> {
        let paths = self.get_apk_paths(device_serial, package_name)?;
        let apk_remote = paths.iter().find(|p| p.ends_with("base.apk")).unwrap_or(&paths[0]);

        let apk_clean_name = if package_name.ends_with(".apk") {
            package_name.to_string()
        } else {
            format!("{}.apk", package_name)
        };

        let final_dest = if local_dest.is_dir() || local_dest.extension().is_none() {
            let _ = std::fs::create_dir_all(local_dest);
            local_dest.join(&apk_clean_name)
        } else {
            if let Some(parent) = local_dest.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            local_dest.to_path_buf()
        };

        self.pull_file(device_serial, apk_remote, &final_dest)?;
        Ok(final_dest)
    }

    pub fn export_file(&self, device_serial: Option<&str>, remote_path: &str, local_dest: &std::path::Path) -> Result<PathBuf, AdbError> {
        let file_name = std::path::Path::new(remote_path)
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();

        let final_dest = if local_dest.is_dir() || local_dest.extension().is_none() {
            let _ = std::fs::create_dir_all(local_dest);
            if file_name.is_empty() {
                local_dest.to_path_buf()
            } else {
                local_dest.join(&file_name)
            }
        } else {
            if let Some(parent) = local_dest.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            local_dest.to_path_buf()
        };

        self.pull_file(device_serial, remote_path, &final_dest)?;
        Ok(final_dest)
    }

    pub fn list_remote_directory_files(&self, device_serial: Option<&str>, remote_dir: &str) -> Result<Vec<String>, AdbError> {
        let cmd = format!("find {} -maxdepth 2 -type f 2>/dev/null", remote_dir);
        let out = self.raw_shell(device_serial, &cmd)?;
        let files = out.lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
        Ok(files)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aura_launcher_core::ToolchainInfo;

    #[test]
    fn test_adb_client_instantiation() {
        let tc = ToolchainInfo::detect();
        if let Some(adb_path) = tc.adb_path {
            let client = AuraAdbClient::new(adb_path);
            let ver = client.version();
            assert!(ver.is_ok());
            assert!(ver.unwrap().contains("Android Debug Bridge"));

            let devices = client.list_devices();
            assert!(devices.is_ok());
        }
    }
}
