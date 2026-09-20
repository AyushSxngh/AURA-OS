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
