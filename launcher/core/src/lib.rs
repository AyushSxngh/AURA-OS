pub mod accel;
pub mod config;
pub mod host;
pub mod status;
pub mod toolchain;

pub use accel::{AccelInfo, HypervisorType};
pub use config::{GraphicsBackend, GuestAbi, VirtualDeviceConfig};
pub use host::{HostArch, HostInfo, HostOs};
pub use status::PlatformStatusReport;
pub use toolchain::ToolchainInfo;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

/// Creates a `std::process::Command` configured with CREATE_NO_WINDOW on Windows
/// so that background utility executions do not flash or spawn console windows.
pub fn silent_command<P: AsRef<std::ffi::OsStr>>(program: P) -> std::process::Command {
    #[allow(unused_mut)]
    let mut cmd = std::process::Command::new(program);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    cmd
}

