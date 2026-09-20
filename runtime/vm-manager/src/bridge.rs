use aura_launcher_core::silent_command;
use std::path::Path;
use crate::adb::AdbError;

pub struct GuestBridge {
    adb_path: std::path::PathBuf,
}

impl GuestBridge {
    pub fn new(adb_path: std::path::PathBuf) -> Self {
        Self { adb_path }
    }

    /// Push a local host file or folder to the guest Android filesystem.
    pub fn push_file(&self, device_serial: Option<&str>, host_path: &Path, guest_path: &str) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("push").arg(host_path).arg(guest_path);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    /// Pull a guest Android file to the local host filesystem.
    pub fn pull_file(&self, device_serial: Option<&str>, guest_path: &str, host_path: &Path) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("pull").arg(guest_path).arg(host_path);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    /// Send text from the host clipboard directly into the guest Android focus element.
    pub fn send_text(&self, device_serial: Option<&str>, text: &str) -> Result<(), AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        // Escape spaces for ADB input text
        let escaped = text.replace(' ', "%s");
        cmd.arg("shell").arg("input").arg("text").arg(&escaped);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    /// Send hardware key events (e.g. Back, Home, Volume, Power) to the guest.
    pub fn send_key_event(&self, device_serial: Option<&str>, keycode: u32) -> Result<(), AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("shell").arg("input").arg("keyevent").arg(keycode.to_string());

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    /// Capture an instant screenshot of the Android screen and save it to the host.
    pub fn capture_screenshot(&self, device_serial: Option<&str>, host_output_path: &Path) -> Result<(), AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("exec-out").arg("screencap").arg("-p");

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            std::fs::write(host_output_path, &output.stdout)
                .map_err(|e| AdbError::ExecutionFailed(format!("Failed to write screenshot file: {}", e)))?;
            Ok(())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }

    /// Capture an instant screenshot as raw PNG bytes.
    pub fn capture_screenshot_bytes(&self, device_serial: Option<&str>) -> Result<Vec<u8>, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("exec-out").arg("screencap").arg("-p");

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(output.stdout)
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }
}
