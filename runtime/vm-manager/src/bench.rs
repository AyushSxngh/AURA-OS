use aura_launcher_core::silent_command;
use std::time::Instant;
use crate::adb::AdbError;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BenchmarkReport {
    pub boot_status: bool,
    pub cpu_bogo_mips: Option<f64>,
    pub cpu_cores_guest: usize,
    pub total_memory_kb: u64,
    pub free_memory_kb: u64,
    pub app_launch_ms: Option<u64>,
    pub graphics_pipeline: String,
    pub raw_gfxinfo: String,
}

pub struct PerformanceProfiler {
    adb_path: std::path::PathBuf,
}

impl PerformanceProfiler {
    pub fn new(adb_path: std::path::PathBuf) -> Self {
        Self { adb_path }
    }

    /// Run full performance benchmark on the active virtual machine.
    pub fn run_benchmark(&self, device_serial: Option<&str>) -> Result<BenchmarkReport, AdbError> {
        // 1. Read /proc/cpuinfo
        let cpu_info = self.shell_exec(device_serial, "cat /proc/cpuinfo")?;
        let mut cpu_cores_guest = 0;
        let mut cpu_bogo_mips = None;

        for line in cpu_info.lines() {
            if line.starts_with("processor") {
                cpu_cores_guest += 1;
            }
            if line.to_lowercase().contains("bogomips") && cpu_bogo_mips.is_none() {
                if let Some(val_str) = line.split(':').nth(1) {
                    cpu_bogo_mips = val_str.trim().parse::<f64>().ok();
                }
            }
        }

        // 2. Read /proc/meminfo
        let mem_info = self.shell_exec(device_serial, "cat /proc/meminfo")?;
        let mut total_memory_kb = 0;
        let mut free_memory_kb = 0;

        for line in mem_info.lines() {
            if line.starts_with("MemTotal:") {
                if let Some(val) = line.split_whitespace().nth(1) {
                    total_memory_kb = val.parse::<u64>().unwrap_or(0);
                }
            } else if line.starts_with("MemAvailable:") || line.starts_with("MemFree:") {
                if free_memory_kb == 0 {
                    if let Some(val) = line.split_whitespace().nth(1) {
                        free_memory_kb = val.parse::<u64>().unwrap_or(0);
                    }
                }
            }
        }

        // 3. Measure app launch latency (using Settings app as baseline)
        let launch_start = Instant::now();
        let _ = self.shell_exec(device_serial, "am start -W -n com.android.settings/.Settings");
        let app_launch_ms = Some(launch_start.elapsed().as_millis() as u64);

        // 4. Query graphics pipeline
        let gfx_pipeline = self.shell_exec(device_serial, "getprop debug.hwui.renderer")
            .unwrap_or_else(|_| "skiagl".to_string())
            .trim()
            .to_string();

        // 5. Query dumpsys gfxinfo
        let raw_gfxinfo = self.shell_exec(device_serial, "dumpsys gfxinfo com.android.settings")
            .unwrap_or_else(|_| "No profile data".to_string());

        Ok(BenchmarkReport {
            boot_status: true,
            cpu_bogo_mips,
            cpu_cores_guest,
            total_memory_kb,
            free_memory_kb,
            app_launch_ms,
            graphics_pipeline: if gfx_pipeline.is_empty() { "skiagl (Vulkan/GL)".into() } else { gfx_pipeline },
            raw_gfxinfo,
        })
    }

    fn shell_exec(&self, device_serial: Option<&str>, shell_cmd: &str) -> Result<String, AdbError> {
        let mut cmd = silent_command(&self.adb_path);
        if let Some(serial) = device_serial {
            cmd.arg("-s").arg(serial);
        }
        cmd.arg("shell").arg(shell_cmd);

        let output = cmd.output().map_err(|e| AdbError::ExecutionFailed(e.to_string()))?;
        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).to_string())
        } else {
            Err(AdbError::CommandError(String::from_utf8_lossy(&output.stderr).to_string()))
        }
    }
}
