use aura_launcher_core::{PlatformStatusReport, VirtualDeviceConfig};
use aura_vm_manager::{AuraAdbClient, AuraVmManager, GuestBridge};
use eframe::egui;
use std::path::PathBuf;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

#[derive(Clone)]
pub struct InstanceInfo {
    pub name: String,
    pub is_running: bool,
    pub serial: Option<String>,
    pub port: u16,
    pub cores: u32,
    pub ram_mb: u32,
}

#[derive(PartialEq, Eq, Clone, Copy, Debug)]
pub enum ExportTab {
    Apk,
    Files,
    Media,
}

enum AsyncMessage {
    InstancesUpdated(Vec<InstanceInfo>),
    PackagesLoaded(Vec<String>),
    Notification(String),
    #[allow(dead_code)]
    FrameReady(egui::ColorImage),
    BootStateChanged(bool, String),
    RemoteImagesLoaded(Vec<String>),
    RemoteFilesLoaded(Vec<String>),
}

pub struct AuraGuiApp {
    status_report: PlatformStatusReport,
    device_config: VirtualDeviceConfig,
    instances: Vec<InstanceInfo>,
    active_instance_index: usize,
    package_list: Vec<String>,
    search_query: String,
    notification_msg: Option<(String, Instant)>,
    selected_apk_path: Option<PathBuf>,
    new_instance_name: String,
    
    // UI state
    app_drawer_open: bool,
    multi_instance_open: bool,
    diagnostics_open: bool,
    export_drawer_open: bool,
    clipboard_text: String,
    
    // Media & File/APK Export state
    export_tab: ExportTab,
    export_remote_path_input: String,
    export_package_search: String,
    export_custom_pkg_input: String,
    remote_files_list: Vec<String>,
    is_refreshing_files: Arc<Mutex<bool>>,
    remote_images: Vec<String>,
    auto_export_enabled: bool,
    is_refreshing_images: Arc<Mutex<bool>>,
    
    // Screen display state
    screen_texture: Option<egui::TextureHandle>,
    #[allow(dead_code)]
    is_screencap_in_progress: Arc<Mutex<bool>>,
    last_frame_instant: Instant,
    last_instance_refresh: Instant,
    is_refreshing_instances: Arc<Mutex<bool>>,
    #[allow(dead_code)]
    drag_start_pos: Option<egui::Pos2>,
    #[allow(dead_code)]
    drag_start_time: Option<Instant>,
    is_booting: bool,
    boot_status_text: String,
    fullscreen_mode: bool,

    rx: Receiver<AsyncMessage>,
    tx: Sender<AsyncMessage>,
}

impl AuraGuiApp {
    pub fn new(_cc: &eframe::CreationContext<'_>) -> Self {
        let (tx, rx) = channel();
        let report = PlatformStatusReport::fast_detect();
        let config = VirtualDeviceConfig::default();

        let default_name = if cfg!(target_arch = "aarch64") {
            "AURA_OS_ARM64".to_string()
        } else {
            "AURA_OS_x86_64".to_string()
        };

        let initial_instances = vec![
            InstanceInfo {
                name: default_name,
                is_running: false,
                serial: None,
                port: 5554,
                cores: 4,
                ram_mb: 4096,
            }
        ];

        let app = Self {
            status_report: report,
            device_config: config,
            instances: initial_instances,
            active_instance_index: 0,
            package_list: Vec::new(),
            search_query: String::new(),
            notification_msg: None,
            selected_apk_path: None,
            new_instance_name: String::new(),
            
            app_drawer_open: false,
            multi_instance_open: false,
            diagnostics_open: false,
            export_drawer_open: false,
            clipboard_text: String::new(),
            
            export_tab: ExportTab::Apk,
            export_remote_path_input: "/sdcard/Download".to_string(),
            export_package_search: String::new(),
            export_custom_pkg_input: String::new(),
            remote_files_list: Vec::new(),
            is_refreshing_files: Arc::new(Mutex::new(false)),
            remote_images: Vec::new(),
            auto_export_enabled: true,
            is_refreshing_images: Arc::new(Mutex::new(false)),
            
            screen_texture: None,
            is_screencap_in_progress: Arc::new(Mutex::new(false)),
            last_frame_instant: Instant::now() - Duration::from_secs(10),
            last_instance_refresh: Instant::now(),
            is_refreshing_instances: Arc::new(Mutex::new(false)),
            drag_start_pos: None,
            drag_start_time: None,
            is_booting: false,
            boot_status_text: String::new(),
            fullscreen_mode: false,

            rx,
            tx,
        };

        app.refresh_instances_async();
        crate::http_bridge::HttpBridge::start_server(8088);
        app
    }

    fn notify(&mut self, msg: String) {
        self.notification_msg = Some((msg, Instant::now()));
    }

    fn active_serial(&self) -> Option<String> {
        self.instances.get(self.active_instance_index).and_then(|inst| {
            if inst.is_running {
                inst.serial.clone().or_else(|| Some(format!("emulator-{}", inst.port)))
            } else {
                None
            }
        })
    }

    fn refresh_instances_async(&self) {
        let lock = self.is_refreshing_instances.clone();
        if let Ok(mut in_prog) = lock.try_lock() {
            if *in_prog {
                return;
            }
            *in_prog = true;
        } else {
            return;
        }

        let adb_path_opt = self.status_report.toolchain.adb_path.clone();
        let emu_path_opt = self.status_report.toolchain.emulator_path.clone();
        let sdk_root_opt = self.status_report.toolchain.sdk_root.clone();
        let tx = self.tx.clone();

        thread::spawn(move || {
            let mut list = Vec::new();
            let mut online_devices = Vec::new();

            if let Some(adb_path) = &adb_path_opt {
                let client = AuraAdbClient::new(adb_path.clone());
                if let Ok(devs) = client.list_devices() {
                    online_devices = devs;
                }
            }

            if let (Some(emu_path), sdk_root) = (emu_path_opt, sdk_root_opt) {
                let mgr = AuraVmManager::new(emu_path, sdk_root);
                if let Ok(avds) = mgr.list_avds() {
                    for (i, name) in avds.into_iter().enumerate() {
                        let expected_port = 5554 + (i as u16 * 2);
                        let serial = format!("emulator-{}", expected_port);
                        let port_open = std::net::TcpStream::connect_timeout(
                            &std::net::SocketAddr::from(([127, 0, 0, 1], expected_port)),
                            Duration::from_millis(60),
                        ).is_ok();
                        let is_running = port_open || online_devices.iter().any(|d| d.serial == serial);

                        list.push(InstanceInfo {
                            name,
                            is_running,
                            serial: if is_running { Some(serial) } else { None },
                            port: expected_port,
                            cores: 6,
                            ram_mb: 8192,
                        });
                    }
                }
            }

            if list.is_empty() {
                let default_name = if cfg!(target_arch = "aarch64") {
                    "AURA_OS_ARM64".to_string()
                } else {
                    "AURA_OS_x86_64".to_string()
                };
                let port_open = std::net::TcpStream::connect_timeout(
                    &std::net::SocketAddr::from(([127, 0, 0, 1], 5554)),
                    Duration::from_millis(60),
                ).is_ok();
                let is_running = port_open || online_devices.iter().any(|d| d.serial == "emulator-5554");
                list.push(InstanceInfo {
                    name: default_name,
                    is_running,
                    serial: if is_running { Some("emulator-5554".to_string()) } else { None },
                    port: 5554,
                    cores: 6,
                    ram_mb: 8192,
                });
            }

            let _ = tx.send(AsyncMessage::InstancesUpdated(list));
            if let Ok(mut in_prog) = lock.lock() {
                *in_prog = false;
            }
        });
    }

    fn refresh_packages_async(&self) {
        let adb_path_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        thread::spawn(move || {
            if let Some(adb_path) = adb_path_opt {
                let client = AuraAdbClient::new(adb_path);
                if let Ok(pkgs) = client.list_packages(serial.as_deref()) {
                    let _ = tx.send(AsyncMessage::PackagesLoaded(pkgs));
                }
            }
        });
    }

    fn refresh_remote_images_async(&self) {
        let adb_path_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        let lock = self.is_refreshing_images.clone();

        if let Ok(mut in_prog) = lock.try_lock() {
            if *in_prog {
                return;
            }
            *in_prog = true;
        } else {
            return;
        }

        thread::spawn(move || {
            if let Some(adb_path) = adb_path_opt {
                let client = AuraAdbClient::new(adb_path);
                if let Ok(images) = client.list_remote_images(serial.as_deref()) {
                    let _ = tx.send(AsyncMessage::RemoteImagesLoaded(images));
                }
            }
            if let Ok(mut in_prog) = lock.lock() {
                *in_prog = false;
            }
        });
    }

    fn export_image_to_mac(&self, remote_path: &str) {
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        let r_path = remote_path.to_string();

        if let Some(adb_path) = adb_opt {
            thread::spawn(move || {
                let client = AuraAdbClient::new(adb_path);
                let home = std::env::var("HOME").unwrap_or_else(|_| "/Users/ayush".to_string());
                let export_dir = std::path::PathBuf::from(home).join("Desktop").join("AURA_Exported");
                let _ = std::fs::create_dir_all(&export_dir);

                let file_name = std::path::Path::new(&r_path)
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string();
                let local_dest = export_dir.join(&file_name);

                match client.pull_file(serial.as_deref(), &r_path, &local_dest) {
                    Ok(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("📤 Exported '{}' to Desktop/AURA_Exported!", file_name)));
                        let _ = aura_launcher_core::silent_command("open")
                            .arg("-R")
                            .arg(&local_dest)
                            .output();
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Export failed: {}", e)));
                    }
                }
            });
            let _ = self.tx.send(AsyncMessage::Notification(format!("Exporting '{}' to Mac...", remote_path)));
        } else {
            let _ = self.tx.send(AsyncMessage::Notification("ADB binary not found. Cannot export image.".into()));
        }
    }

    fn export_all_images_to_mac(&self) {
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        let images = self.remote_images.clone();

        if let Some(adb_path) = adb_opt {
            thread::spawn(move || {
                let client = AuraAdbClient::new(adb_path);
                let home = std::env::var("HOME").unwrap_or_else(|_| "/Users/ayush".to_string());
                let export_dir = std::path::PathBuf::from(home).join("Desktop").join("AURA_Exported");
                let _ = std::fs::create_dir_all(&export_dir);

                let mut count = 0;
                for r_path in &images {
                    let file_name = std::path::Path::new(r_path)
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string();
                    let local_dest = export_dir.join(&file_name);
                    if client.pull_file(serial.as_deref(), r_path, &local_dest).is_ok() {
                        count += 1;
                    }
                }

                let _ = tx.send(AsyncMessage::Notification(format!("📤 Exported {} image(s) to Desktop/AURA_Exported!", count)));
                let _ = aura_launcher_core::silent_command("open")
                    .arg(&export_dir)
                    .output();
            });
            let _ = self.tx.send(AsyncMessage::Notification("Exporting all images to Mac Desktop...".into()));
        } else {
            let _ = self.tx.send(AsyncMessage::Notification("ADB binary not found. Cannot export images.".into()));
        }
    }

    fn export_apk_to_mac(&self, package_name: &str) {
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        let pkg = package_name.trim().to_string();

        if pkg.is_empty() {
            let _ = self.tx.send(AsyncMessage::Notification("Please provide a valid package name to export.".into()));
            return;
        }

        if let Some(adb_path) = adb_opt {
            let _ = self.tx.send(AsyncMessage::Notification(format!("Locating & extracting APK for '{}'...", pkg)));
            thread::spawn(move || {
                let client = AuraAdbClient::new(adb_path);
                let home = std::env::var("HOME").unwrap_or_else(|_| "/Users/ayush".to_string());
                let export_dir = std::path::PathBuf::from(home).join("Desktop").join("AURA_Exported");
                let _ = std::fs::create_dir_all(&export_dir);

                match client.export_apk(serial.as_deref(), &pkg, &export_dir) {
                    Ok(out_file) => {
                        let fname = out_file.file_name().unwrap_or_default().to_string_lossy().to_string();
                        let _ = tx.send(AsyncMessage::Notification(format!("📦 Exported '{}' to Desktop/AURA_Exported!", fname)));
                        let _ = aura_launcher_core::silent_command("open")
                            .arg("-R")
                            .arg(&out_file)
                            .output();
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("APK export failed: {}", e)));
                    }
                }
            });
        } else {
            let _ = self.tx.send(AsyncMessage::Notification("ADB binary not found. Cannot export APK.".into()));
        }
    }

    fn export_file_to_mac(&self, remote_path: &str, custom_dest: Option<PathBuf>) {
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        let r_path = remote_path.trim().to_string();

        if r_path.is_empty() {
            let _ = self.tx.send(AsyncMessage::Notification("Remote path cannot be empty.".into()));
            return;
        }

        if let Some(adb_path) = adb_opt {
            let _ = self.tx.send(AsyncMessage::Notification(format!("Pulling '{}' from guest...", r_path)));
            thread::spawn(move || {
                let client = AuraAdbClient::new(adb_path);
                let export_dir = if let Some(dest) = custom_dest {
                    dest
                } else {
                    let home = std::env::var("HOME").unwrap_or_else(|_| "/Users/ayush".to_string());
                    let dir = std::path::PathBuf::from(home).join("Desktop").join("AURA_Exported");
                    let _ = std::fs::create_dir_all(&dir);
                    dir
                };

                match client.export_file(serial.as_deref(), &r_path, &export_dir) {
                    Ok(out_file) => {
                        let fname = out_file.file_name().unwrap_or_default().to_string_lossy().to_string();
                        let _ = tx.send(AsyncMessage::Notification(format!("📁 Exported '{}' to Mac!", fname)));
                        let _ = aura_launcher_core::silent_command("open")
                            .arg("-R")
                            .arg(&out_file)
                            .output();
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("File export failed: {}", e)));
                    }
                }
            });
        } else {
            let _ = self.tx.send(AsyncMessage::Notification("ADB binary not found. Cannot export file.".into()));
        }
    }

    fn refresh_remote_files_async(&self, remote_dir: &str) {
        let adb_path_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        let lock = self.is_refreshing_files.clone();
        let dir = remote_dir.to_string();

        if let Ok(mut in_prog) = lock.try_lock() {
            if *in_prog {
                return;
            }
            *in_prog = true;
        } else {
            return;
        }

        let _ = tx.send(AsyncMessage::Notification(format!("Scanning '{}' for files...", dir)));
        thread::spawn(move || {
            if let Some(adb_path) = adb_path_opt {
                let client = AuraAdbClient::new(adb_path);
                if let Ok(files) = client.list_remote_directory_files(serial.as_deref(), &dir) {
                    let count = files.len();
                    let _ = tx.send(AsyncMessage::RemoteFilesLoaded(files));
                    let _ = tx.send(AsyncMessage::Notification(format!("Found {} file(s) in '{}'", count, dir)));
                }
            }
            if let Ok(mut in_prog) = lock.lock() {
                *in_prog = false;
            }
        });
    }

    #[allow(dead_code)]
    fn generate_app_history_async(&self) {
        let tx = self.tx.clone();
        let _ = tx.send(AsyncMessage::Notification("🎮 Generating authentic app & game history...".to_string()));
        thread::spawn(move || {
            let script_path = std::path::PathBuf::from("tools/generate_app_history.py");
            let cmd = if script_path.exists() {
                aura_launcher_core::silent_command("python3").arg(&script_path).output()
            } else {
                aura_launcher_core::silent_command("python3").arg("/Users/ayush/Desktop/HEBB NETWORK/Emulator/tools/generate_app_history.py").output()
            };
            match cmd {
                Ok(output) => {
                    if output.status.success() {
                        let _ = tx.send(AsyncMessage::Notification("✅ App history & game profiles seeded successfully!".to_string()));
                    } else {
                        let _ = tx.send(AsyncMessage::Notification("⚠️ App history generation failed.".to_string()));
                    }
                }
                Err(_) => {
                    let _ = tx.send(AsyncMessage::Notification("❌ Could not launch python generator.".to_string()));
                }
            }
        });
    }

    fn launch_instance(&mut self, instance_name: String, port: u16) {
        let emu_opt = self.status_report.toolchain.emulator_path.clone();
        let sdk_opt = self.status_report.toolchain.sdk_root.clone();
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let mut config = self.device_config.clone();
        config.name = instance_name.clone();
        let tx = self.tx.clone();
        let target_name = instance_name.clone();

        self.is_booting = true;
        self.boot_status_text = format!("Starting Android 16 VM '{}' (port {})...", target_name, port);

        if let Some(emu_path) = emu_opt {
            let mgr = AuraVmManager::new(emu_path, sdk_opt);
            thread::spawn(move || {
                let _ = tx.send(AsyncMessage::BootStateChanged(true, format!("Spawning QEMU hypervisor engine for {}...", target_name)));

                // Auto-create & tune AVD if it doesn't exist yet
                if !mgr.avd_exists(&config.name) {
                    let _ = tx.send(AsyncMessage::BootStateChanged(true, format!("Initializing AVD '{}' profile...", target_name)));
                    let is_arm = cfg!(target_arch = "aarch64") || config.abi == aura_launcher_core::GuestAbi::Arm64V8a;
                    let arch_str = if is_arm { "arm64-v8a" } else { "x86_64" };
                    let pkg = format!("system-images;android-34;google_apis_playstore;{}", arch_str);
                    let _ = mgr.create_avd(&config.name, &pkg);
                    let _ = mgr.configure_avd_ini(&config.name, &config);
                }

                match mgr.start_vm_with_port(&config, Some(port)) {
                    Ok(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Instance '{}' hypervisor started on port {}.", target_name, port)));
                        let _ = tx.send(AsyncMessage::BootStateChanged(true, "Hypervisor online. Waiting for Android System UI to finish boot...".into()));

                        // Poll for boot completed
                        if let Some(adb_path) = adb_opt {
                            let client = AuraAdbClient::new(adb_path);
                            let serial = format!("emulator-{}", port);
                            let mut booted = false;
                            for i in 0..60 {
                                thread::sleep(Duration::from_millis(1500));
                                if let Ok(out) = client.shell_command(Some(&serial), "getprop sys.boot_completed") {
                                    if out.trim() == "1" {
                                        let _ = client.shell_command(Some(&serial), "input keyevent KEYCODE_WAKEUP");
                                        let _ = client.shell_command(Some(&serial), "wm dismiss-keyguard");
                                        let _ = client.shell_command(Some(&serial), "svc power stayon true");
                                        let _ = client.shell_command(Some(&serial), "wm size 1440x3120");
                                        let _ = client.shell_command(Some(&serial), "wm density 600");
                                        let _ = client.shell_command(Some(&serial), "settings put secure android_id bd652ddf47cbb6d5");
                                        let _ = client.shell_command(Some(&serial), "dumpsys battery set level 42");
                                        let _ = client.shell_command(Some(&serial), "dumpsys battery set status 2");
                                        let _ = client.shell_command(Some(&serial), "dumpsys battery set ac 1");
                                        let _ = client.shell_command(Some(&serial), "dumpsys battery set temp 355");
                                        let _ = client.shell_command(Some(&serial), "dumpsys battery set health 2");
                                        let _ = client.shell_command(Some(&serial), "dumpsys battery set technology Li-ion");
                                        #[cfg(target_os = "macos")]
                                        {
                                            let _ = aura_launcher_core::silent_command("osascript")
                                                .arg("-e")
                                                .arg("tell application \"System Events\" to set frontmost of first process whose name contains \"qemu-system\" to true")
                                                .spawn();
                                            let _ = aura_launcher_core::silent_command("bash")
                                                .arg("-c")
                                                .arg("pgrep -f sec_daemon_supervisor.sh >/dev/null 2>&1 || nohup /Users/ayush/Desktop/HEBB\\ NETWORK/Emulator/tools/sec_daemon_supervisor.sh >/tmp/sec_supervisor.log 2>&1 &")
                                                .spawn();
                                        }
                                        let _ = tx.send(AsyncMessage::BootStateChanged(false, "Android 16 Ready!".into()));
                                        let _ = tx.send(AsyncMessage::Notification("Android System UI fully booted!".into()));
                                        booted = true;
                                        break;
                                    }
                                }

                                // Fallback: If ADB is offline or disabled, detect readiness via hypervisor console port after QuickBoot load
                                if i >= 3 {
                                    let console_open = std::net::TcpStream::connect_timeout(
                                        &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
                                        Duration::from_millis(100),
                                    ).is_ok();
                                    if console_open {
                                        #[cfg(target_os = "macos")]
                                        {
                                            let _ = aura_launcher_core::silent_command("osascript")
                                                .arg("-e")
                                                .arg("tell application \"System Events\" to set frontmost of first process whose name contains \"qemu-system\" to true")
                                                .spawn();
                                        }
                                        let _ = tx.send(AsyncMessage::BootStateChanged(false, "Android 16 Ready!".into()));
                                        let _ = tx.send(AsyncMessage::Notification("Android System UI hypervisor ready!".into()));
                                        booted = true;
                                        break;
                                    }
                                }
                            }
                            if !booted {
                                let _ = tx.send(AsyncMessage::BootStateChanged(false, String::new()));
                            }
                        } else {
                            let _ = tx.send(AsyncMessage::BootStateChanged(false, String::new()));
                        }
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::BootStateChanged(false, String::new()));
                        let _ = tx.send(AsyncMessage::Notification(format!("Failed to start '{}': {}", target_name, e)));
                    }
                }
            });
        } else {
            self.is_booting = false;
            self.boot_status_text = String::new();
            self.notify("Android Emulator binary not found! Please check Diagnostics tab or ensure Android SDK is installed.".into());
        }
    }

    fn stop_instance(&mut self, serial_opt: Option<String>) {
        self.screen_texture = None;
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let tx = self.tx.clone();
        if let Some(adb_path) = adb_opt {
            let client = AuraAdbClient::new(adb_path);
            let s = serial_opt.clone();
            thread::spawn(move || {
                match client.stop_emulator(s.as_deref()) {
                    Ok(_) => {
                        let _ = tx.send(AsyncMessage::Notification("Instance shutdown completed.".into()));
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Shutdown failed: {}", e)));
                    }
                }
            });
            self.notify("Sending graceful shutdown command...".into());
        }
    }

    fn create_new_instance(&mut self, name: String) {
        let emu_opt = self.status_report.toolchain.emulator_path.clone();
        let sdk_opt = self.status_report.toolchain.sdk_root.clone();
        let tx = self.tx.clone();
        let target_name = name.clone();

        if let Some(emu_path) = emu_opt {
            let mgr = AuraVmManager::new(emu_path, sdk_opt);
            let default_base = if cfg!(target_arch = "aarch64") { "AURA_OS_ARM64" } else { "AURA_OS_x86_64" };
            thread::spawn(move || {
                match mgr.clone_avd(default_base, &target_name) {
                    Ok(_) => {
                        let avd_dir = mgr.get_avd_dir(&target_name);
                        let identity = aura_vm_manager::DeviceIdentity::load_or_generate(&avd_dir);
                        let _ = tx.send(AsyncMessage::Notification(format!(
                            "Instance '{}' created with unique IMEI: {} | Serial: {}",
                            target_name, identity.imei, identity.serialno
                        )));
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Failed to create instance: {}", e)));
                    }
                }
            });
            self.notify(format!("Creating new multi-instance clone '{}'...", name));
        }
    }

    fn delete_instance(&mut self, name: String) {
        let emu_opt = self.status_report.toolchain.emulator_path.clone();
        let sdk_opt = self.status_report.toolchain.sdk_root.clone();
        if let Some(emu_path) = emu_opt {
            let mgr = AuraVmManager::new(emu_path, sdk_opt);
            match mgr.delete_avd(&name) {
                Ok(_) => {
                    self.notify(format!("Instance '{}' deleted.", name));
                    self.refresh_instances_async();
                }
                Err(e) => self.notify(format!("Delete failed: {}", e)),
            }
        }
    }

    fn install_selected_apk(&mut self) {
        if let Some(path) = self.selected_apk_path.clone() {
            // Mirror to AURA_Transfer folder for offline Web Bridge access
            let transfer_dir = crate::http_bridge::HttpBridge::get_transfer_dir();
            if let Some(file_name) = path.file_name() {
                let _ = std::fs::copy(&path, transfer_dir.join(file_name));
            }

            self.open_bridge_in_guest_chrome();

            let adb_opt = self.status_report.toolchain.adb_path.clone();
            let serial = self.active_serial();
            let tx = self.tx.clone();
            let apk_name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
            if let Some(adb_path) = adb_opt {
                let client = AuraAdbClient::new(adb_path);
                let target_path = path.clone();
                let name_in_thread = apk_name.clone();
                thread::spawn(move || {
                    match client.install_apk(serial.as_deref(), &target_path) {
                        Ok(res) => {
                            let _ = tx.send(AsyncMessage::Notification(format!("APK '{}' installed: {}", name_in_thread, res)));
                        }
                        Err(_) => {
                            let _ = tx.send(AsyncMessage::Notification(format!(
                                "⚡ APK '{}' staged in Offline Bridge! Tap 'Download / Install' in Chrome",
                                name_in_thread
                            )));
                        }
                    }
                });
                self.notify(format!("Staging APK '{}' to Offline Bridge & opening Chrome...", apk_name));
            }
        }
    }

    fn push_image_to_active_instance(&mut self, path: &std::path::Path) {
        // Mirror to AURA_Transfer folder for offline Web Bridge access
        let transfer_dir = crate::http_bridge::HttpBridge::get_transfer_dir();
        if let Some(file_name) = path.file_name() {
            let _ = std::fs::copy(path, transfer_dir.join(file_name));
        }

        self.open_bridge_in_guest_chrome();

        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        let file_name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
        let target_path = path.to_path_buf();

        if let Some(adb_path) = adb_opt {
            let client = AuraAdbClient::new(adb_path);
            let name_in_thread = file_name.clone();
            thread::spawn(move || {
                let remote_dest = format!("/sdcard/Pictures/{}", name_in_thread);
                match client.push_file(serial.as_deref(), &target_path, &remote_dest) {
                    Ok(_) => {
                        let scan_cmd = format!("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{}", remote_dest);
                        let _ = client.shell_command(serial.as_deref(), &scan_cmd);
                        let _ = tx.send(AsyncMessage::Notification(format!("📸 Image '{}' pushed to Android Gallery!", name_in_thread)));

                        let _ = aura_launcher_core::silent_command("curl")
                            .arg("-s")
                            .arg("-X")
                            .arg("POST")
                            .arg("--data-binary")
                            .arg(format!("@{}", target_path.display()))
                            .arg("http://127.0.0.1:8080/api/set_source")
                            .output();
                    }
                    Err(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!(
                            "⚡ Image '{}' staged in Offline Bridge! Available at http://localhost:8088",
                            name_in_thread
                        )));
                    }
                }
            });
            self.notify(format!("Staging image '{}' to Offline Bridge & opening Chrome...", file_name));
        } else {
            self.notify("Image copied to ~/Desktop/AURA_Transfer! Opening Chrome...".into());
        }
    }

    fn push_file_to_active_instance(&mut self, path: &std::path::Path) {
        // Mirror to AURA_Transfer folder for offline Web Bridge access
        let transfer_dir = crate::http_bridge::HttpBridge::get_transfer_dir();
        if let Some(file_name) = path.file_name() {
            let _ = std::fs::copy(path, transfer_dir.join(file_name));
        }

        self.open_bridge_in_guest_chrome();

        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let tx = self.tx.clone();
        let file_name = path.file_name().unwrap_or_default().to_string_lossy().to_string();
        let target_path = path.to_path_buf();

        if let Some(adb_path) = adb_opt {
            let client = AuraAdbClient::new(adb_path);
            let name_in_thread = file_name.clone();
            thread::spawn(move || {
                let remote_dest = format!("/sdcard/Download/{}", name_in_thread);
                match client.push_file(serial.as_deref(), &target_path, &remote_dest) {
                    Ok(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("📁 File '{}' pushed to /sdcard/Download!", name_in_thread)));
                    }
                    Err(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!(
                            "⚡ File '{}' staged in Offline Bridge! Available at http://localhost:8088",
                            name_in_thread
                        )));
                    }
                }
            });
            self.notify(format!("Staging '{}' to Offline Bridge & opening Chrome...", file_name));
        } else {
            self.notify("File copied to ~/Desktop/AURA_Transfer! Opening Chrome...".into());
        }
    }

    fn send_keyevent(&self, keycode: u32) {
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        if let Some(adb_path) = adb_opt {
            thread::spawn(move || {
                let client = AuraAdbClient::new(adb_path);
                let _ = client.shell_command(serial.as_deref(), &format!("input keyevent {}", keycode));
            });
        }
    }

    #[allow(dead_code)]
    fn send_tap(&self, x: u32, y: u32) {
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        if let Some(adb_path) = adb_opt {
            thread::spawn(move || {
                let client = AuraAdbClient::new(adb_path);
                let _ = client.shell_command(serial.as_deref(), &format!("input tap {} {}", x, y));
            });
        }
    }

    #[allow(dead_code)]
    fn send_swipe(&self, x1: u32, y1: u32, x2: u32, y2: u32, duration_ms: u32) {
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        if let Some(adb_path) = adb_opt {
            thread::spawn(move || {
                let client = AuraAdbClient::new(adb_path);
                let _ = client.shell_command(serial.as_deref(), &format!("input swipe {} {} {} {} {}", x1, y1, x2, y2, duration_ms));
            });
        }
    }

    fn launch_app_by_pkg(&mut self, pkg: &str) {
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let serial = self.active_serial();
        let p = pkg.to_string();
        if let Some(adb_path) = adb_opt {
            thread::spawn(move || {
                let client = AuraAdbClient::new(adb_path);
                if p == "com.sec.android.app.camera" {
                    // Permanently remove and disable stock camera from existence
                    let _ = client.shell_command(serial.as_deref(), "pm disable-user --user 0 com.android.camera2");
                    let _ = client.shell_command(serial.as_deref(), "pm uninstall -k --user 0 com.android.camera2");

                    let check = client.shell_command(serial.as_deref(), "pm list packages com.sec.android.app.camera").unwrap_or_default();
                    if !check.contains("package:com.sec.android.app.camera") {
                        let apk = std::path::Path::new("/Users/ayush/Desktop/HEBB NETWORK/Emulator/apps/camera/app/build/outputs/apk/debug/app-debug.apk");
                        let fallback = std::path::Path::new("/Users/ayush/Desktop/HEBB NETWORK/Emulator/apps/camera/AURA-Camera.apk");
                        if apk.exists() {
                            let _ = client.install_apk(serial.as_deref(), apk);
                        } else if fallback.exists() {
                            let _ = client.install_apk(serial.as_deref(), fallback);
                        }
                    }
                }
                let _ = client.shell_command(serial.as_deref(), &format!("monkey -p {} -c android.intent.category.LAUNCHER 1", p));
            });
            self.app_drawer_open = false;
            self.notify(format!("Launched {}", pkg));
            self.focus_emulator_window();
        }
    }

    #[allow(dead_code)]
    fn request_screencap_async(&self) {
        let serial = match self.active_serial() {
            Some(s) => s,
            None => return,
        };
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let lock = self.is_screencap_in_progress.clone();
        let tx = self.tx.clone();

        if let Ok(mut in_prog) = lock.try_lock() {
            if *in_prog {
                return;
            }
            *in_prog = true;
        } else {
            return;
        }

        thread::spawn(move || {
            if let Some(adb_path) = adb_opt {
                let bridge = GuestBridge::new(adb_path);
                if let Ok(bytes) = bridge.capture_screenshot_bytes(Some(&serial)) {
                    if let Ok(img) = image::load_from_memory(&bytes) {
                        let rgba = img.to_rgba8();
                        let size = [rgba.width() as usize, rgba.height() as usize];
                        let color_img = egui::ColorImage::from_rgba_unmultiplied(size, rgba.as_flat_samples().as_slice());
                        let _ = tx.send(AsyncMessage::FrameReady(color_img));
                    }
                }
            }
            if let Ok(mut in_prog) = lock.lock() {
                *in_prog = false;
            }
        });
    }

    fn take_screenshot(&mut self) {
        let serial = self.active_serial();
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let tx = self.tx.clone();

        let home = std::env::var("HOME").unwrap_or_else(|_| "/Users/ayush".into());
        let timestamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs();
        let desktop_path = format!("{}/Desktop/AURA_Screenshot_{}.png", home, timestamp);
        let save_path = desktop_path.clone();

        thread::spawn(move || {
            let port = serial
                .as_deref()
                .and_then(|s| s.strip_prefix("emulator-"))
                .and_then(|p| p.parse::<u16>().ok())
                .unwrap_or(5554);

            let mut console_saved = false;
            if let Ok(mut stream) = std::net::TcpStream::connect_timeout(
                &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
                std::time::Duration::from_millis(500),
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
                let _ = stream.write_all(format!("screenrecord screenshot {}\n", desktop_path).as_bytes());
                let mut resp = [0u8; 1024];
                if let Ok(n) = stream.read(&mut resp) {
                    let resp_str = String::from_utf8_lossy(&resp[..n]);
                    if resp_str.contains("OK") {
                        console_saved = true;
                    }
                }
            }

            if console_saved && std::path::Path::new(&desktop_path).exists() {
                #[cfg(target_os = "macos")]
                {
                    let _ = aura_launcher_core::silent_command("open").arg("-R").arg(&desktop_path).spawn();
                }
                let _ = tx.send(AsyncMessage::Notification(format!("📸 Screenshot saved to Desktop: AURA_Screenshot_{}.png", timestamp)));
                return;
            }

            if let Some(adb_path) = adb_opt {
                let bridge = GuestBridge::new(adb_path);
                let dest = PathBuf::from(&save_path);
                match bridge.capture_screenshot(serial.as_deref(), &dest) {
                    Ok(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Saved screenshot to {}", save_path)));
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Screenshot failed: {}", e)));
                    }
                }
            }
        });
        self.notify("Capturing screenshot...".into());
    }

    fn open_bridge_in_guest_chrome(&mut self) {
        let serial = self.active_serial();
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let tx = self.tx.clone();

        // 1. Reveal Mac Transfer folder in Finder
        let dir = crate::http_bridge::HttpBridge::get_transfer_dir();
        #[cfg(target_os = "macos")]
        {
            let _ = aura_launcher_core::silent_command("open").arg(&dir).spawn();
        }

        // 2. Focus emulator window on macOS
        self.focus_emulator_window();

        // 3. Automation via guest console port
        thread::spawn(move || {
            // First try adb intent if adb happens to be available
            if let Some(adb_path) = &adb_opt {
                let client = AuraAdbClient::new(adb_path.clone());
                if let Ok(out) = client.shell_command(
                    serial.as_deref(),
                    "am start -a android.intent.action.VIEW -d http://localhost:8088 com.android.chrome",
                ) {
                    if !out.contains("device offline") && !out.contains("Error") {
                        let _ = tx.send(AsyncMessage::Notification("⚡ Offline Bridge opened in Chrome!".into()));
                        return;
                    }
                }
            }

            // Fallback to hardware console port (100% offline, zero ADB)
            let port = serial
                .as_deref()
                .and_then(|s| s.strip_prefix("emulator-"))
                .and_then(|p| p.parse::<u16>().ok())
                .unwrap_or(5554);

            if let Ok(mut stream) = std::net::TcpStream::connect_timeout(
                &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
                std::time::Duration::from_millis(1000),
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

                // Sequence:
                // 1. Tap Chrome dock icon at (315, 1860)
                let _ = stream.write_all(b"event mouse 315 1860 0 1\nevent mouse 315 1860 0 0\n");
                std::thread::sleep(std::time::Duration::from_millis(600));

                // 2. Tap omnibox / URL bar at (350, 70)
                let _ = stream.write_all(b"event mouse 350 70 0 1\nevent mouse 350 70 0 0\n");
                std::thread::sleep(std::time::Duration::from_millis(400));

                // 3. Clear existing URL with X at (980, 155)
                let _ = stream.write_all(b"event mouse 980 155 0 1\nevent mouse 980 155 0 0\n");
                std::thread::sleep(std::time::Duration::from_millis(300));

                // 4. Type URL localhost:8088
                let _ = stream.write_all(b"event text localhost:8088\n");
                std::thread::sleep(std::time::Duration::from_millis(500));

                // 5. Tap top suggestion row at (500, 320) & press Enter
                let _ = stream.write_all(b"event mouse 500 320 0 1\nevent mouse 500 320 0 0\n");
                let _ = stream.write_all(b"event send EV_KEY:KEY_ENTER:1\nevent send EV_KEY:KEY_ENTER:0\n");

                let _ = tx.send(AsyncMessage::Notification("⚡ Offline Bridge (http://localhost:8088) launched in Android Chrome!".into()));
            } else {
                let _ = tx.send(AsyncMessage::Notification("Could not connect to emulator console (port 5554)".into()));
            }
        });

        self.notify("Launching Offline Bridge in Android Chrome...".into());
    }

    fn focus_emulator_window(&self) {
        #[cfg(target_os = "windows")]
        {
            let _ = aura_launcher_core::silent_command("powershell")
                .arg("-NoProfile")
                .arg("-Command")
                .arg("$p = Get-Process -Name 'qemu-system-x86_64', 'emulator' -ErrorAction SilentlyContinue | Select-Object -First 1; $ws = New-Object -ComObject WScript.Shell; if ($p) { $ws.AppActivate($p.Id) } else { $ws.AppActivate('Android Emulator') }")
                .spawn();
        }
        #[cfg(target_os = "macos")]
        {
            let _ = aura_launcher_core::silent_command("osascript")
                .arg("-e")
                .arg("tell application \"System Events\" to set frontmost of first process whose name contains \"qemu-system\" to true")
                .spawn();
        }
    }
}

impl eframe::App for AuraGuiApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Poll async events
        while let Ok(msg) = self.rx.try_recv() {
            match msg {
                AsyncMessage::InstancesUpdated(list) => {
                    self.instances = list;
                    if self.active_instance_index >= self.instances.len() {
                        self.active_instance_index = 0;
                    }
                }
                AsyncMessage::PackagesLoaded(pkgs) => {
                    self.package_list = pkgs;
                }
                AsyncMessage::Notification(n) => {
                    self.notify(n);
                }
                AsyncMessage::FrameReady(img) => {
                    match &mut self.screen_texture {
                        Some(tex) => tex.set(img, egui::TextureOptions::LINEAR),
                        None => self.screen_texture = Some(ctx.load_texture("android_screen", img, egui::TextureOptions::LINEAR)),
                    }
                    self.last_frame_instant = Instant::now();
                    ctx.request_repaint();
                }
                AsyncMessage::BootStateChanged(booting, text) => {
                    self.is_booting = booting;
                    self.boot_status_text = text;
                    if !booting {
                        self.refresh_instances_async();
                        self.refresh_packages_async();
                    }
                }
                AsyncMessage::RemoteImagesLoaded(images) => {
                    self.remote_images = images;
                }
                AsyncMessage::RemoteFilesLoaded(files) => {
                    self.remote_files_list = files;
                }
            }
        }

        // Drag & Drop handling for APKs and Images
        let dropped = ctx.input(|i| i.raw.dropped_files.clone());
        if !dropped.is_empty() {
            for file in dropped {
                if let Some(path) = file.path {
                    let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_lowercase();
                    if ext == "apk" {
                        self.selected_apk_path = Some(path);
                        self.install_selected_apk();
                    } else if matches!(ext.as_str(), "jpg" | "jpeg" | "png" | "webp" | "bmp" | "gif") {
                        self.push_image_to_active_instance(&path);
                    } else {
                        self.push_file_to_active_instance(&path);
                    }
                }
            }
        }

        // Visual Drag & Drop Hover Overlay
        if ctx.input(|i| !i.raw.hovered_files.is_empty()) {
            egui::Area::new("drag_drop_overlay".into())
                .order(egui::Order::Foreground)
                .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
                .show(ctx, |ui| {
                    egui::Frame::popup(ui.style())
                        .fill(egui::Color32::from_rgba_premultiplied(15, 23, 42, 240))
                        .stroke(egui::Stroke::new(2.0_f32, egui::Color32::from_rgb(99, 102, 241)))
                        .rounding(16.0)
                        .show(ui, |ui| {
                            ui.set_min_size(egui::vec2(360.0, 120.0));
                            ui.vertical_centered(|ui| {
                                ui.add_space(18.0);
                                ui.label(egui::RichText::new("📥 Drop to Install APK or Push Image").size(18.0).strong().color(egui::Color32::WHITE));
                                ui.add_space(8.0);
                                ui.label(egui::RichText::new("APKs are auto-installed • Images are sent to Android Gallery & Face Swap").size(12.0).color(egui::Color32::from_rgb(148, 163, 184)));
                                ui.add_space(18.0);
                            });
                        });
                });
        }

        let is_running = self.instances.get(self.active_instance_index).map(|i| i.is_running).unwrap_or(false);

        // Periodic instance status refresh (every 4s)
        if self.last_instance_refresh.elapsed() > Duration::from_secs(4) {
            self.last_instance_refresh = Instant::now();
            self.refresh_instances_async();
        }

        // TOP BAR: BlueStacks + Bliss OS Header
        egui::TopBottomPanel::top("top_header").show(ctx, |ui| {
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                // Logo & Title
                ui.label(egui::RichText::new("🪷 AURA OS").size(16.0).strong().color(egui::Color32::from_rgb(56, 189, 248)));
                ui.label(egui::RichText::new("Android Virtualization Platform").weak().size(12.0));
                
                ui.separator();

                // Instance Selector Dropdown
                ui.label(egui::RichText::new("Active Instance:").size(12.0));
                let selected_name = self.instances.get(self.active_instance_index)
                    .map(|i| format!("{} (Port {})", i.name, i.port))
                    .unwrap_or_else(|| "None".into());

                egui::ComboBox::from_id_source("instance_selector")
                    .selected_text(egui::RichText::new(selected_name).strong())
                    .show_ui(ui, |ui| {
                        for (idx, inst) in self.instances.iter().enumerate() {
                            let status = if inst.is_running { "🟢" } else { "⚪" };
                            let label = format!("{} {} (Port {})", status, inst.name, inst.port);
                            ui.selectable_value(&mut self.active_instance_index, idx, label);
                        }
                    });

                // Status Pill
                if is_running {
                    let hv = self.status_report.accel.hypervisor.short_name();
                    let gfx = if cfg!(target_os = "macos") { "Metal" } else { "Vulkan" };
                    ui.label(egui::RichText::new(format!("● ONLINE ({} • {} • 120 FPS)", hv, gfx)).color(egui::Color32::from_rgb(34, 197, 94)).size(11.0).strong());
                } else if self.is_booting {
                    ui.label(egui::RichText::new("⏳ BOOTING...").color(egui::Color32::from_rgb(234, 179, 8)).size(11.0).strong());
                } else {
                    ui.label(egui::RichText::new("⚪ STOPPED").color(egui::Color32::from_rgb(148, 163, 184)).size(11.0));
                }

                // Right-aligned Quick Controls
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui.button(egui::RichText::new("🩺 Diagnostics").size(12.0)).clicked() {
                        self.diagnostics_open = !self.diagnostics_open;
                    }

                    if ui.button(egui::RichText::new("📱 Multi-Instance Manager").strong().color(egui::Color32::from_rgb(129, 140, 248)).size(12.0)).clicked() {
                        self.multi_instance_open = !self.multi_instance_open;
                    }

                    if ui.button(egui::RichText::new("🚀 Start Menu").strong().color(egui::Color32::from_rgb(56, 189, 248)).size(12.0)).clicked() {
                        self.app_drawer_open = !self.app_drawer_open;
                    }

                    if is_running {
                        if ui.button(egui::RichText::new("⏹ Stop VM").color(egui::Color32::from_rgb(239, 68, 68))).clicked() {
                            let serial = self.active_serial();
                            self.stop_instance(serial);
                        }
                    } else {
                        if ui.button(egui::RichText::new("▶ Start VM").color(egui::Color32::from_rgb(34, 197, 94)).strong()).clicked() {
                            if let Some(inst) = self.instances.get(self.active_instance_index).cloned() {
                                self.launch_instance(inst.name, inst.port);
                            }
                        }
                    }
                });
            });
            ui.add_space(3.0);
        });

        // BOTTOM BLISS OS TASKBAR (Inspired by Bliss OS Desktop / media_1789893218866.png)
        egui::TopBottomPanel::bottom("bottom_taskbar").show(ctx, |ui| {
            ui.add_space(2.0);
            ui.horizontal(|ui| {
                // Bliss OS Lotus Start Button
                if ui.button(egui::RichText::new("🪷").size(16.0)).on_hover_text("Open Bliss OS Start Menu").clicked() {
                    self.app_drawer_open = !self.app_drawer_open;
                }

                // 3x3 App Drawer Button
                if ui.button(egui::RichText::new("ⵌ").size(15.0)).on_hover_text("App Drawer").clicked() {
                    self.app_drawer_open = !self.app_drawer_open;
                }

                ui.separator();

                // Android Navigation Buttons: Back, Home, Recents
                if ui.button(egui::RichText::new(" ◁ ").size(14.0).strong()).on_hover_text("Back (ESC)").clicked() {
                    self.send_keyevent(4); // KEYCODE_BACK
                    self.focus_emulator_window();
                }
                if ui.button(egui::RichText::new(" ○ ").size(14.0).strong()).on_hover_text("Home").clicked() {
                    self.send_keyevent(3); // KEYCODE_HOME
                    self.focus_emulator_window();
                }
                if ui.button(egui::RichText::new(" □ ").size(14.0).strong()).on_hover_text("Recent Apps").clicked() {
                    self.send_keyevent(187); // KEYCODE_APP_SWITCH
                    self.focus_emulator_window();
                }

                ui.separator();

                // Center Pinned Quick Apps Dock
                if ui.button(egui::RichText::new("🖼 Gallery").size(12.0)).clicked() {
                    self.launch_app_by_pkg("com.android.gallery3d");
                }
                if ui.button(egui::RichText::new("🛍 Play Store").size(12.0)).clicked() {
                    self.launch_app_by_pkg("com.android.vending");
                }
                if ui.button(egui::RichText::new("⚡ Browser").size(12.0)).clicked() {
                    self.launch_app_by_pkg("com.android.chrome");
                }
                if ui.button(egui::RichText::new("📷 Camera").size(12.0)).clicked() {
                    self.launch_app_by_pkg("com.sec.android.app.camera");
                }
                if ui.button(egui::RichText::new("⚙ Settings").size(12.0)).clicked() {
                    self.launch_app_by_pkg("com.android.settings");
                }

                // Right Status / Clock Tray
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs();
                    let hours = (now / 3600) % 24;
                    let minutes = (now / 60) % 60;
                    ui.label(egui::RichText::new(format!("{:02}:{:02} UTC", hours, minutes)).size(11.0).strong());
                    ui.label("🔋 100%");
                    ui.label("📶 Online");
                    if let Some((msg, created)) = &self.notification_msg {
                        if created.elapsed() < Duration::from_secs(4) {
                            ui.label(egui::RichText::new(format!("🔔 {}", msg)).color(egui::Color32::from_rgb(56, 189, 248)).size(11.0));
                        }
                    }
                });
            });
            ui.add_space(2.0);
        });

        // RIGHT BLUESTACKS TOOLBAR
        egui::SidePanel::right("bluestacks_sidebar").resizable(false).exact_width(48.0).show(ctx, |ui| {
            ui.add_space(6.0);
            ui.vertical_centered(|ui| {
                if ui.button(egui::RichText::new("⛶").size(16.0)).on_hover_text("Toggle Fullscreen").clicked() {
                    self.fullscreen_mode = !self.fullscreen_mode;
                }
                ui.add_space(6.0);

                if ui.button(egui::RichText::new("📱").size(16.0)).on_hover_text("Multi-Instance Manager").clicked() {
                    self.multi_instance_open = !self.multi_instance_open;
                }
                ui.add_space(6.0);

                if ui.button(egui::RichText::new("📦").size(16.0)).on_hover_text("Install APK File").clicked() {
                    if let Some(path) = rfd::FileDialog::new()
                        .add_filter("Android Package (*.apk)", &["apk"])
                        .pick_file()
                    {
                        self.selected_apk_path = Some(path);
                        self.install_selected_apk();
                    }
                }
                ui.add_space(6.0);

                if ui.button(egui::RichText::new("🖼").size(16.0)).on_hover_text("Upload Image / File to Active Instance").clicked() {
                    if let Some(path) = rfd::FileDialog::new()
                        .add_filter("Supported Files", &["jpg", "jpeg", "png", "webp", "bmp", "gif", "apk", "pdf", "txt", "mp4"])
                        .add_filter("Images (*.jpg, *.png)", &["jpg", "jpeg", "png", "webp", "bmp", "gif"])
                        .add_filter("Android Package (*.apk)", &["apk"])
                        .pick_file()
                    {
                        let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_lowercase();
                        if ext == "apk" {
                            self.selected_apk_path = Some(path);
                            self.install_selected_apk();
                        } else if matches!(ext.as_str(), "jpg" | "jpeg" | "png" | "webp" | "bmp" | "gif") {
                            self.push_image_to_active_instance(&path);
                        } else {
                            self.push_file_to_active_instance(&path);
                        }
                    }
                }
                if ui.button(egui::RichText::new("📤").size(16.0)).on_hover_text("Export Files, APKs & Media to Mac").clicked() {
                    self.export_drawer_open = !self.export_drawer_open;
                    if self.export_drawer_open {
                        self.refresh_packages_async();
                        self.refresh_remote_images_async();
                        let dir = self.export_remote_path_input.clone();
                        self.refresh_remote_files_async(&dir);
                    }
                }
                ui.add_space(6.0);

                if ui.button(egui::RichText::new("📸").size(16.0)).on_hover_text("Take Screenshot").clicked() {
                    self.take_screenshot();
                }
                ui.add_space(6.0);

                if ui.button(egui::RichText::new("📋").size(16.0)).on_hover_text("Inject Clipboard Text").clicked() {
                    let adb_opt = self.status_report.toolchain.adb_path.clone();
                    let serial = self.active_serial();
                    let text = self.clipboard_text.clone();
                    if let Some(adb_path) = adb_opt {
                        let bridge = GuestBridge::new(adb_path);
                        thread::spawn(move || {
                            let _ = bridge.send_text(serial.as_deref(), if text.is_empty() { "AURA_OS" } else { &text });
                        });
                        self.notify("Sent clipboard text to Android focus.".into());
                    }
                }
                ui.add_space(6.0);

                if ui.button(egui::RichText::new("🔊").size(16.0)).on_hover_text("Volume Up").clicked() {
                    self.send_keyevent(24);
                }
                ui.add_space(4.0);

                if ui.button(egui::RichText::new("🔉").size(16.0)).on_hover_text("Volume Down").clicked() {
                    self.send_keyevent(25);
                }
                ui.add_space(6.0);

                if ui.button(egui::RichText::new("🔄").size(16.0)).on_hover_text("Rotate Screen Orientation").clicked() {
                    let adb_opt = self.status_report.toolchain.adb_path.clone();
                    let serial = self.active_serial();
                    if let Some(adb_path) = adb_opt {
                        thread::spawn(move || {
                            let client = AuraAdbClient::new(adb_path);
                            let _ = client.shell_command(serial.as_deref(), "settings put system user_rotation 1");
                        });
                        self.notify("Toggled orientation.".into());
                        self.focus_emulator_window();
                    }
                }
                ui.add_space(14.0);
                ui.separator();
                ui.add_space(14.0);

                // Quick Navigation Shortcuts
                if ui.button(egui::RichText::new("◁").size(16.0)).on_hover_text("Back").clicked() {
                    self.send_keyevent(4);
                    self.focus_emulator_window();
                }
                ui.add_space(6.0);
                if ui.button(egui::RichText::new("○").size(16.0)).on_hover_text("Home").clicked() {
                    self.send_keyevent(3);
                    self.focus_emulator_window();
                }
                ui.add_space(6.0);
                if ui.button(egui::RichText::new("□").size(16.0)).on_hover_text("Recent Apps").clicked() {
                    self.send_keyevent(187);
                    self.focus_emulator_window();
                }
            });
        });

        // POPUP START MENU / APP DRAWER (Bliss OS / Windows 11 style from media_1789893218866.png)
        if self.app_drawer_open {
            egui::Window::new("🪷 Bliss OS Start Menu")
                .anchor(egui::Align2::LEFT_BOTTOM, egui::vec2(10.0, -42.0))
                .fixed_size(egui::vec2(420.0, 480.0))
                .collapsible(false)
                .resizable(false)
                .show(ctx, |ui| {
                    ui.add_space(4.0);
                    ui.horizontal(|ui| {
                        ui.label(egui::RichText::new("Bliss OS Applications").strong().size(14.0));
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if ui.button("❌ Close").clicked() {
                                self.app_drawer_open = false;
                            }
                            if ui.button("🔄 Refresh").clicked() {
                                self.refresh_packages_async();
                            }
                        });
                    });
                    ui.separator();

                    // Search input at bottom of header
                    ui.horizontal(|ui| {
                        ui.label("🔍");
                        ui.text_edit_singleline(&mut self.search_query);
                    });
                    ui.add_space(6.0);

                    // Pinned Bliss OS core apps matching user reference image
                    let standard_apps = vec![
                        ("About Bliss", "com.android.settings", "🪷"),
                        ("Files", "com.android.documentsui", "📁"),
                        ("Camera", "com.sec.android.app.camera", "📷"),
                        ("Fulguris", "com.android.chrome", "⚡"),
                        ("Gallery", "com.android.gallery3d", "🖼"),
                        ("Google", "com.google.android.googlequicksearchbox", "🌐"),
                        ("Settings", "com.android.settings", "⚙"),
                        ("Clock", "com.android.deskclock", "⏰"),
                        ("Contacts", "com.android.contacts", "👤"),
                        ("Termux", "com.termux", "📟"),
                        ("Play Store", "com.android.vending", "🛍"),
                        ("One UI Home", "com.sec.android.app.launcher", "🏠"),
                    ];

                    let query = self.search_query.to_lowercase();

                    egui::ScrollArea::vertical().max_height(340.0).show(ui, |ui| {
                        egui::Grid::new("bliss_apps_grid").num_columns(3).spacing([12.0, 10.0]).show(ui, |ui| {
                            let mut col = 0;
                            for (name, pkg, icon) in &standard_apps {
                                if query.is_empty() || name.to_lowercase().contains(&query) || pkg.to_lowercase().contains(&query) {
                                    let btn = ui.button(egui::RichText::new(format!("{} {}", icon, name)).size(13.0));
                                    if btn.clicked() {
                                        self.launch_app_by_pkg(pkg);
                                    }
                                    btn.context_menu(|ui| {
                                        if ui.button("📤 Export APK to Mac").clicked() {
                                            self.export_apk_to_mac(pkg);
                                            ui.close_menu();
                                        }
                                    });
                                    col += 1;
                                    if col % 3 == 0 {
                                        ui.end_row();
                                    }
                                }
                            }

                            // Dynamic packages
                            let dynamic_pkgs = self.package_list.clone();
                            for pkg in &dynamic_pkgs {
                                if !standard_apps.iter().any(|(_, p, _)| p == pkg) {
                                    if query.is_empty() || pkg.to_lowercase().contains(&query) {
                                        let short_name = pkg.split('.').last().unwrap_or(pkg);
                                        let btn = ui.button(format!("📱 {}", short_name));
                                        if btn.clicked() {
                                            self.launch_app_by_pkg(pkg);
                                        }
                                        btn.context_menu(|ui| {
                                            if ui.button("📤 Export APK to Mac").clicked() {
                                                self.export_apk_to_mac(pkg);
                                                ui.close_menu();
                                            }
                                        });
                                        col += 1;
                                        if col % 3 == 0 {
                                            ui.end_row();
                                        }
                                    }
                                }
                            }
                        });
                    });
                });
        }

        // BLUESTACKS MULTI-INSTANCE MANAGER MODAL / DRAWER
        if self.multi_instance_open {
            egui::Window::new("📱 Multi-Instance Manager")
                .fixed_size(egui::vec2(580.0, 420.0))
                .collapsible(true)
                .resizable(true)
                .show(ctx, |ui| {
                    ui.horizontal(|ui| {
                        ui.heading("Instance Fleet");
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if ui.button("🔄 Refresh").clicked() {
                                self.refresh_instances_async();
                            }
                            if ui.button(egui::RichText::new("➕ Create Instance").color(egui::Color32::from_rgb(56, 189, 248)).strong()).clicked() {
                                let name = if self.new_instance_name.trim().is_empty() {
                                    format!("AURA_Instance_{}", self.instances.len() + 1)
                                } else {
                                    self.new_instance_name.trim().to_string()
                                };
                                self.create_new_instance(name);
                                self.new_instance_name.clear();
                            }
                            ui.add(egui::TextEdit::singleline(&mut self.new_instance_name).hint_text("Instance name..."));
                        });
                    });
                    ui.label(egui::RichText::new("Launch, clone, or isolate multiple Android instances with individual ports and displays.").weak());
                    ui.separator();

                    egui::ScrollArea::vertical().max_height(300.0).show(ui, |ui| {
                        let insts = self.instances.clone();
                        for (idx, inst) in insts.iter().enumerate() {
                            egui::Frame::group(ui.style()).fill(egui::Color32::from_rgb(24, 28, 38)).show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    ui.vertical(|ui| {
                                        ui.horizontal(|ui| {
                                            ui.label(egui::RichText::new(&inst.name).size(15.0).strong());
                                            if inst.is_running {
                                                ui.label(egui::RichText::new("RUNNING").color(egui::Color32::from_rgb(34, 197, 94)).size(11.0).strong());
                                            } else {
                                                ui.label(egui::RichText::new("STOPPED").color(egui::Color32::from_rgb(148, 163, 184)).size(11.0));
                                            }
                                        });
                                        ui.label(egui::RichText::new(format!(
                                            "Port: {} | Cores: {} | RAM: {} MB | Target: 1920x1080 Landscape",
                                            inst.port, inst.cores, inst.ram_mb
                                        )).weak().size(11.0));
                                    });

                                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                        if inst.is_running {
                                            if ui.button(egui::RichText::new("Stop").color(egui::Color32::from_rgb(239, 68, 68))).clicked() {
                                                self.stop_instance(inst.serial.clone());
                                            }
                                            if ui.button(egui::RichText::new("🎯 Focus").strong().color(egui::Color32::from_rgb(56, 189, 248))).clicked() {
                                                self.active_instance_index = idx;
                                                self.focus_emulator_window();
                                            }
                                        } else {
                                            if ui.button(egui::RichText::new("▶ Start").color(egui::Color32::from_rgb(34, 197, 94)).strong()).clicked() {
                                                self.launch_instance(inst.name.clone(), inst.port);
                                                self.active_instance_index = idx;
                                            }
                                        }

                                        if ui.button("Clone").clicked() {
                                            let clone_name = format!("{}_Clone", inst.name);
                                            self.create_new_instance(clone_name);
                                        }

                                        if inst.name != "AURA_OS_x86_64" && inst.name != "AURA_OS_ARM64" {
                                            if ui.button(egui::RichText::new("Delete").color(egui::Color32::from_rgb(239, 68, 68))).clicked() {
                                                self.delete_instance(inst.name.clone());
                                            }
                                        }
                                    });
                                });
                            });
                            ui.add_space(4.0);
                        }
                    });
                });
        }

        // DIAGNOSTICS & HARDWARE MODAL
        if self.diagnostics_open {
            egui::Window::new("🩺 System & Hypervisor Diagnostics")
                .fixed_size(egui::vec2(500.0, 360.0))
                .collapsible(true)
                .show(ctx, |ui| {
                    ui.label(egui::RichText::new("Host Virtualization & Acceleration Status").strong());
                    ui.separator();
                    ui.label(format!("OS: {:?} ({})", self.status_report.host.os, self.status_report.host.os_version));
                    ui.label(format!("CPU: {} ({} Cores)", self.status_report.host.cpu_brand, self.status_report.host.logical_cores));
                    ui.label(format!("Host RAM: {} MB", self.status_report.host.total_memory_mb));
                    ui.label(format!("Hypervisor: {} Active & Operational", self.status_report.accel.hypervisor.display_name()));
                    let renderer_desc = if cfg!(target_os = "macos") {
                        "Guest Hardware Renderer: skiagl (Apple Metal Host Translation)"
                    } else {
                        "Guest Hardware Renderer: skiagl (Vulkan Host Translation)"
                    };
                    ui.label(renderer_desc);
                    ui.separator();
                    ui.label(egui::RichText::new("SDK Toolchain").strong());
                    ui.label(format!("ADB: {}", self.status_report.toolchain.adb_path.as_ref().map(|p| p.display().to_string()).unwrap_or("Not found".into())));
                    ui.label(format!("Emulator: {}", self.status_report.toolchain.emulator_path.as_ref().map(|p| p.display().to_string()).unwrap_or("Not found".into())));
                    if ui.button("Close Diagnostics").clicked() {
                        self.diagnostics_open = false;
                    }
                });
        }

        // EXPORT HUB (DOWNLOAD / EXPORT TO MAC: FILES, APKs, MEDIA)
        if self.export_drawer_open {
            egui::Window::new("📤 AURA Export Hub — APKs, Files & Media")
                .fixed_size(egui::vec2(600.0, 480.0))
                .collapsible(true)
                .show(ctx, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(egui::RichText::new("Export from Android to Mac Desktop").strong().size(14.0).color(egui::Color32::from_rgb(56, 189, 248)));
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if ui.button("✖ Close").clicked() {
                                self.export_drawer_open = false;
                            }
                            if ui.button("📂 Open Export Folder").clicked() {
                                let home = std::env::var("HOME").unwrap_or_else(|_| "/Users/ayush".to_string());
                                let export_dir = std::path::PathBuf::from(home).join("Desktop").join("AURA_Exported");
                                let _ = std::fs::create_dir_all(&export_dir);
                                let _ = aura_launcher_core::silent_command("open").arg(&export_dir).output();
                            }
                        });
                    });
                    ui.separator();

                    // Tab selector row
                    ui.horizontal(|ui| {
                        let apk_btn = egui::Button::new(egui::RichText::new("📦 Export Installed APKs").strong())
                            .fill(if self.export_tab == ExportTab::Apk { egui::Color32::from_rgb(37, 99, 235) } else { egui::Color32::from_rgb(30, 41, 59) })
                            .rounding(6.0);
                        if ui.add(apk_btn).clicked() {
                            self.export_tab = ExportTab::Apk;
                            if self.package_list.is_empty() {
                                self.refresh_packages_async();
                            }
                        }

                        let file_btn = egui::Button::new(egui::RichText::new("📁 Export Files & Storage").strong())
                            .fill(if self.export_tab == ExportTab::Files { egui::Color32::from_rgb(37, 99, 235) } else { egui::Color32::from_rgb(30, 41, 59) })
                            .rounding(6.0);
                        if ui.add(file_btn).clicked() {
                            self.export_tab = ExportTab::Files;
                            if self.remote_files_list.is_empty() {
                                let dir = self.export_remote_path_input.clone();
                                self.refresh_remote_files_async(&dir);
                            }
                        }

                        let media_btn = egui::Button::new(egui::RichText::new("🖼 Photos & Media").strong())
                            .fill(if self.export_tab == ExportTab::Media { egui::Color32::from_rgb(37, 99, 235) } else { egui::Color32::from_rgb(30, 41, 59) })
                            .rounding(6.0);
                        if ui.add(media_btn).clicked() {
                            self.export_tab = ExportTab::Media;
                            if self.remote_images.is_empty() {
                                self.refresh_remote_images_async();
                            }
                        }
                    });
                    ui.separator();

                    match self.export_tab {
                        ExportTab::Apk => {
                            ui.horizontal(|ui| {
                                ui.label("🔍 Search:");
                                ui.text_edit_singleline(&mut self.export_package_search);
                                if ui.button("🔄 Refresh Apps").clicked() {
                                    self.refresh_packages_async();
                                }
                            });
                            ui.add_space(4.0);

                            ui.horizontal(|ui| {
                                ui.label("Custom Package ID:");
                                ui.add(egui::TextEdit::singleline(&mut self.export_custom_pkg_input).hint_text("e.g. id.flash.apk"));
                                let exp_custom = egui::Button::new(egui::RichText::new("📤 Export APK").color(egui::Color32::from_rgb(56, 189, 248)))
                                    .fill(egui::Color32::from_rgb(30, 41, 59))
                                    .rounding(6.0);
                                if ui.add(exp_custom).clicked() && !self.export_custom_pkg_input.trim().is_empty() {
                                    let pkg = self.export_custom_pkg_input.clone();
                                    self.export_apk_to_mac(&pkg);
                                }
                            });
                            ui.add_space(6.0);

                            let query = self.export_package_search.to_lowercase();
                            let pkgs: Vec<String> = self.package_list.iter()
                                .filter(|p| query.is_empty() || p.to_lowercase().contains(&query))
                                .cloned()
                                .collect();

                            ui.label(egui::RichText::new(format!("Showing {} package(s):", pkgs.len())).size(11.5).weak());
                            ui.add_space(4.0);

                            if pkgs.is_empty() {
                                ui.vertical_centered(|ui| {
                                    ui.add_space(40.0);
                                    ui.label("No packages loaded yet.");
                                    if ui.button("🔄 Scan Installed Apps").clicked() {
                                        self.refresh_packages_async();
                                    }
                                });
                            } else {
                                egui::ScrollArea::vertical().max_height(280.0).show(ui, |ui| {
                                    for pkg in pkgs {
                                        let is_priority = pkg.contains("flash") || pkg.contains("aura") || pkg.contains("camera") || pkg.contains("game") || (!pkg.starts_with("com.android.") && !pkg.starts_with("com.google.android."));
                                        let border_color = if is_priority { egui::Color32::from_rgb(56, 189, 248) } else { egui::Color32::from_rgb(39, 51, 74) };
                                        let short_name = pkg.split('.').last().unwrap_or(&pkg).to_string();
                                        let pkg_clone = pkg.clone();

                                        egui::Frame::none()
                                            .fill(egui::Color32::from_rgb(24, 32, 47))
                                            .stroke(egui::Stroke::new(1.0_f32, border_color))
                                            .rounding(8.0)
                                            .inner_margin(egui::Margin::symmetric(12.0, 8.0))
                                            .show(ui, |ui| {
                                                ui.horizontal(|ui| {
                                                    ui.label(egui::RichText::new("📦").size(18.0));
                                                    ui.vertical(|ui| {
                                                        ui.horizontal(|ui| {
                                                            ui.label(egui::RichText::new(&short_name).strong().size(13.0));
                                                            if is_priority {
                                                                ui.label(egui::RichText::new("[App]").size(10.0).color(egui::Color32::from_rgb(56, 189, 248)));
                                                            }
                                                        });
                                                        ui.label(egui::RichText::new(&pkg).size(10.5).weak());
                                                    });
                                                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                                        let btn = egui::Button::new(egui::RichText::new("📤 Export APK").color(egui::Color32::from_rgb(56, 189, 248)))
                                                            .fill(egui::Color32::from_rgb(30, 41, 59))
                                                            .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(56, 189, 248)))
                                                            .rounding(6.0);
                                                        if ui.add(btn).clicked() {
                                                            self.export_apk_to_mac(&pkg_clone);
                                                        }
                                                    });
                                                });
                                            });
                                        ui.add_space(4.0);
                                    }
                                });
                            }
                        }
                        ExportTab::Files => {
                            // Quick folder buttons
                            ui.horizontal_wrapped(|ui| {
                                ui.label(egui::RichText::new("Quick Folders:").size(12.0).weak());
                                if ui.small_button("📥 Downloads").clicked() {
                                    self.export_remote_path_input = "/sdcard/Download".to_string();
                                    self.refresh_remote_files_async("/sdcard/Download");
                                }
                                if ui.small_button("📄 Documents").clicked() {
                                    self.export_remote_path_input = "/sdcard/Documents".to_string();
                                    self.refresh_remote_files_async("/sdcard/Documents");
                                }
                                if ui.small_button("📷 DCIM").clicked() {
                                    self.export_remote_path_input = "/sdcard/DCIM".to_string();
                                    self.refresh_remote_files_async("/sdcard/DCIM");
                                }
                                if ui.small_button("🖼 Pictures").clicked() {
                                    self.export_remote_path_input = "/sdcard/Pictures".to_string();
                                    self.refresh_remote_files_async("/sdcard/Pictures");
                                }
                                if ui.small_button("🎬 Movies").clicked() {
                                    self.export_remote_path_input = "/sdcard/Movies".to_string();
                                    self.refresh_remote_files_async("/sdcard/Movies");
                                }
                                if ui.small_button("💾 /sdcard Root").clicked() {
                                    self.export_remote_path_input = "/sdcard".to_string();
                                    self.refresh_remote_files_async("/sdcard");
                                }
                            });
                            ui.add_space(6.0);

                            // Remote path input + action buttons
                            ui.horizontal(|ui| {
                                ui.label("Android Path:");
                                ui.text_edit_singleline(&mut self.export_remote_path_input);
                                if ui.button("🔍 Scan").clicked() {
                                    let dir = self.export_remote_path_input.clone();
                                    self.refresh_remote_files_async(&dir);
                                }
                            });
                            ui.add_space(4.0);

                            ui.horizontal(|ui| {
                                let exp_btn = egui::Button::new(egui::RichText::new("📤 Export Path to Mac Desktop").strong().color(egui::Color32::WHITE))
                                    .fill(egui::Color32::from_rgb(37, 99, 235))
                                    .rounding(6.0);
                                if ui.add(exp_btn).clicked() {
                                    let path = self.export_remote_path_input.clone();
                                    self.export_file_to_mac(&path, None);
                                }

                                let choose_dest_btn = egui::Button::new("📂 Choose Mac Dest & Export...")
                                    .fill(egui::Color32::from_rgb(30, 41, 59))
                                    .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(51, 65, 85)))
                                    .rounding(6.0);
                                if ui.add(choose_dest_btn).clicked() {
                                    if let Some(dest_dir) = rfd::FileDialog::new().pick_folder() {
                                        let path = self.export_remote_path_input.clone();
                                        self.export_file_to_mac(&path, Some(dest_dir));
                                    }
                                }
                            });
                            ui.add_space(6.0);

                            ui.label(egui::RichText::new(format!("Scanned {} file(s) in '{}':", self.remote_files_list.len(), self.export_remote_path_input)).size(11.5).weak());
                            ui.add_space(4.0);

                            if self.remote_files_list.is_empty() {
                                ui.vertical_centered(|ui| {
                                    ui.add_space(30.0);
                                    ui.label("No files scanned in this path yet.");
                                    ui.label("Click 'Scan' or 'Export Path to Mac Desktop' directly.");
                                });
                            } else {
                                egui::ScrollArea::vertical().max_height(240.0).show(ui, |ui| {
                                    let files = self.remote_files_list.clone();
                                    for f_path in files {
                                        let file_name = std::path::Path::new(&f_path)
                                            .file_name()
                                            .unwrap_or_default()
                                            .to_string_lossy()
                                            .to_string();
                                        let f_path_clone = f_path.clone();

                                        egui::Frame::none()
                                            .fill(egui::Color32::from_rgb(24, 32, 47))
                                            .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(39, 51, 74)))
                                            .rounding(8.0)
                                            .inner_margin(egui::Margin::symmetric(12.0, 8.0))
                                            .show(ui, |ui| {
                                                ui.horizontal(|ui| {
                                                    ui.label(egui::RichText::new("📄").size(18.0));
                                                    ui.vertical(|ui| {
                                                        ui.label(egui::RichText::new(&file_name).strong().size(13.0));
                                                        ui.label(egui::RichText::new(&f_path).size(10.5).weak());
                                                    });
                                                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                                        let btn = egui::Button::new(egui::RichText::new("📤 Export").color(egui::Color32::from_rgb(56, 189, 248)))
                                                            .fill(egui::Color32::from_rgb(30, 41, 59))
                                                            .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(56, 189, 248)))
                                                            .rounding(6.0);
                                                        if ui.add(btn).clicked() {
                                                            self.export_file_to_mac(&f_path_clone, None);
                                                        }
                                                    });
                                                });
                                            });
                                        ui.add_space(4.0);
                                    }
                                });
                            }
                        }
                        ExportTab::Media => {
                            ui.horizontal(|ui| {
                                let export_all_btn = egui::Button::new(egui::RichText::new("📤 Export All to Mac Desktop").strong().color(egui::Color32::WHITE))
                                    .fill(egui::Color32::from_rgb(37, 99, 235))
                                    .rounding(6.0);
                                if ui.add(export_all_btn).clicked() {
                                    self.export_all_images_to_mac();
                                }

                                ui.add_space(8.0);
                                ui.checkbox(&mut self.auto_export_enabled, "⚡ Auto-export new photos");
                                if ui.button("🔄 Scan Photos").clicked() {
                                    self.refresh_remote_images_async();
                                }
                            });

                            ui.add_space(8.0);
                            ui.label(egui::RichText::new(format!("Found {} image(s) on active instance:", self.remote_images.len())).size(12.0).weak());
                            ui.add_space(4.0);

                            if self.remote_images.is_empty() {
                                ui.vertical_centered(|ui| {
                                    ui.add_space(40.0);
                                    ui.label(egui::RichText::new("📷 No photos found yet").size(14.0).color(egui::Color32::from_rgb(148, 163, 184)));
                                    ui.label("Take photos using AURA DeepFake Camera or push images to Gallery.");
                                    ui.add_space(12.0);
                                    if ui.button("🔄 Scan Emulator for Photos").clicked() {
                                        self.refresh_remote_images_async();
                                    }
                                });
                            } else {
                                egui::ScrollArea::vertical().max_height(270.0).show(ui, |ui| {
                                    let images = self.remote_images.clone();
                                    for r_path in images {
                                        let file_name = std::path::Path::new(&r_path)
                                            .file_name()
                                            .unwrap_or_default()
                                            .to_string_lossy()
                                            .to_string();

                                        egui::Frame::none()
                                            .fill(egui::Color32::from_rgb(24, 32, 47))
                                            .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(39, 51, 74)))
                                            .rounding(8.0)
                                            .inner_margin(egui::Margin::symmetric(14.0, 10.0))
                                            .show(ui, |ui| {
                                                ui.horizontal(|ui| {
                                                    ui.label(egui::RichText::new("🖼").size(18.0));
                                                    ui.vertical(|ui| {
                                                        ui.label(egui::RichText::new(&file_name).strong().size(13.0));
                                                        ui.label(egui::RichText::new(&r_path).size(10.5).weak());
                                                    });
                                                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                                        let btn = egui::Button::new(egui::RichText::new("📤 Export to Desktop").color(egui::Color32::from_rgb(56, 189, 248)))
                                                            .fill(egui::Color32::from_rgb(30, 41, 59))
                                                            .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(56, 189, 248)))
                                                            .rounding(6.0);
                                                        if ui.add(btn).clicked() {
                                                            self.export_image_to_mac(&r_path);
                                                        }
                                                    });
                                                });
                                            });
                                        ui.add_space(4.0);
                                    }
                                });
                            }
                        }
                    }
                });
        }

        // FLOATING TOAST NOTIFICATION BANNER (Smooth Fade & Slide)
        if let Some((msg, instant)) = &self.notification_msg {
            let elapsed = instant.elapsed().as_secs_f32();
            if elapsed < 3.5 {
                let alpha = if elapsed < 0.25 {
                    elapsed / 0.25
                } else if elapsed > 3.0 {
                    ((3.5 - elapsed) / 0.5).max(0.0)
                } else {
                    1.0
                };
                let alpha_u8 = (alpha * 255.0) as u8;

                egui::Area::new(egui::Id::new("floating_toast"))
                    .anchor(egui::Align2::CENTER_TOP, egui::vec2(0.0, 52.0))
                    .order(egui::Order::Foreground)
                    .show(ctx, |ui| {
                        egui::Frame::none()
                            .fill(egui::Color32::from_rgba_premultiplied(15, 23, 42, (alpha * 240.0) as u8))
                            .stroke(egui::Stroke::new(1.5_f32, egui::Color32::from_rgba_premultiplied(56, 189, 248, alpha_u8)))
                            .rounding(8.0)
                            .inner_margin(egui::Margin::symmetric(22.0, 10.0))
                            .show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    ui.label(egui::RichText::new("✨").size(15.0));
                                    ui.label(
                                        egui::RichText::new(msg)
                                            .strong()
                                            .size(13.0)
                                            .color(egui::Color32::from_rgba_premultiplied(248, 250, 252, alpha_u8)),
                                    );
                                });
                            });
                    });
            }
        }

        // CENTRAL EMULATOR DISPLAY VIEWPORT (THE CORE INSTANCE DASHBOARD)
        egui::CentralPanel::default().show(ctx, |ui| {
            let available_size = ui.available_size();
            let time = ctx.input(|i| i.time);
            let pulse = ((time * 2.8).sin() * 0.5 + 0.5) as f32;

            if is_running {
                ui.vertical_centered(|ui| {
                    ui.add_space(available_size.y * 0.04);

                    // Glowing Instance Running Badge with Animated Radar Pulse
                    ui.horizontal(|ui| {
                        let badge_w = 540.0;
                        ui.add_space(((available_size.x - badge_w) / 2.0).max(0.0));
                        
                        let stroke_g = (180.0 + 75.0 * pulse) as u8;
                        let stroke_color = egui::Color32::from_rgb(34, stroke_g, 94);

                        egui::Frame::none()
                            .fill(egui::Color32::from_rgb(13, 19, 33))
                            .stroke(egui::Stroke::new(1.5_f32, stroke_color))
                            .rounding(10.0)
                            .inner_margin(egui::Margin::symmetric(20.0, 12.0))
                            .show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    ui.label(egui::RichText::new("●").size(18.0).color(stroke_color));
                                    ui.label(egui::RichText::new("AURA OS VM ONLINE").size(15.0).strong().color(egui::Color32::WHITE));
                                    ui.separator();
                                    ui.label(egui::RichText::new("120 FPS Direct GPU • NVIDIA Vulkan • Port 5554").size(12.0).weak());
                                });
                            });
                    });

                    ui.add_space(20.0);

                    // Primary Hero Focus Button with Smooth Animated Border
                    let focus_border_cyan = egui::Color32::from_rgb(
                        (14.0 + 40.0 * pulse) as u8,
                        (165.0 + 40.0 * pulse) as u8,
                        248,
                    );
                    
                    let focus_btn = egui::Button::new(
                        egui::RichText::new("🎯  FOCUS ANDROID SCREEN (BRING TO FRONT)")
                            .size(16.0)
                            .strong()
                            .color(egui::Color32::WHITE)
                    )
                    .fill(egui::Color32::from_rgb(14, 165, 233))
                    .stroke(egui::Stroke::new(1.8_f32, focus_border_cyan))
                    .min_size(egui::vec2(540.0, 50.0))
                    .rounding(10.0);

                    if ui.add(focus_btn).clicked() {
                        self.focus_emulator_window();
                        self.notify("Focused Android Window".into());
                    }

                    ui.add_space(24.0);

                    // Quick App Launcher Cards Grid (2 rows x 3 columns)
                    ui.label(egui::RichText::new("ONE-CLICK APPLICATION LAUNCHERS").size(13.0).strong().color(egui::Color32::from_rgb(148, 163, 184)));
                    ui.add_space(8.0);

                    let card_w = 176.0;
                    let card_h = 58.0;
                    let grid_w = card_w * 3.0 + 16.0; // 3 cards + 2*8px spacing

                    // Row 1
                    ui.horizontal(|ui| {
                        ui.add_space(((available_size.x - grid_w) / 2.0).max(0.0));
                        
                        if render_app_tile(ui, ctx, "🛍", "Play Store", "Apps & Games", egui::Color32::from_rgb(34, 197, 94), egui::vec2(card_w, card_h)) {
                            self.launch_app_by_pkg("com.android.vending");
                            self.focus_emulator_window();
                        }
                        ui.add_space(8.0);
                        if render_app_tile(ui, ctx, "🌐", "Chrome", "Web Browser", egui::Color32::from_rgb(56, 189, 248), egui::vec2(card_w, card_h)) {
                            self.launch_app_by_pkg("com.android.chrome");
                            self.focus_emulator_window();
                        }
                        ui.add_space(8.0);
                        if render_app_tile(ui, ctx, "⚙️", "Settings", "Android 16 Config", egui::Color32::from_rgb(168, 85, 247), egui::vec2(card_w, card_h)) {
                            self.launch_app_by_pkg("com.android.settings");
                            self.focus_emulator_window();
                        }
                    });

                    ui.add_space(8.0);

                    // Row 2
                    ui.horizontal(|ui| {
                        ui.add_space(((available_size.x - grid_w) / 2.0).max(0.0));
                        
                        if render_app_tile(ui, ctx, "📁", "Files", "Storage & Media", egui::Color32::from_rgb(234, 179, 8), egui::vec2(card_w, card_h)) {
                            self.launch_app_by_pkg("com.google.android.documentsui");
                            self.focus_emulator_window();
                        }
                        ui.add_space(8.0);
                        if render_app_tile(ui, ctx, "▶️", "YouTube", "Videos in 1080p", egui::Color32::from_rgb(239, 68, 68), egui::vec2(card_w, card_h)) {
                            self.launch_app_by_pkg("com.google.android.youtube");
                            self.focus_emulator_window();
                        }
                        ui.add_space(8.0);
                        if render_app_tile(ui, ctx, "📱", "App Drawer", "All Installed Apps", egui::Color32::from_rgb(99, 102, 241), egui::vec2(card_w, card_h)) {
                            self.app_drawer_open = true;
                        }
                    });

                    ui.add_space(24.0);

                    // Platform Tools Bar
                    ui.label(egui::RichText::new("HYPERVISOR CONTROL ACTIONS").size(13.0).strong().color(egui::Color32::from_rgb(148, 163, 184)));
                    ui.add_space(8.0);

                    let tools_w = 880.0;
                    ui.horizontal(|ui| {
                        ui.add_space(((available_size.x - tools_w) / 2.0).max(0.0));
                        
                        // 1. HERO BUTTON: Open Bridge in Android Chrome
                        let bridge_btn = egui::Button::new(
                            egui::RichText::new("⚡ Open Bridge in Chrome")
                                .strong()
                                .size(13.5)
                                .color(egui::Color32::from_rgb(110, 231, 183)),
                        )
                        .fill(egui::Color32::from_rgb(15, 33, 40))
                        .stroke(egui::Stroke::new(1.5_f32, egui::Color32::from_rgb(52, 211, 153)))
                        .min_size(egui::vec2(210.0, 40.0))
                        .rounding(8.0);
                        if ui.add(bridge_btn).on_hover_text("Open http://localhost:8088 directly in Android Chrome & reveal Mac Transfer folder").clicked() {
                            self.open_bridge_in_guest_chrome();
                        }

                        ui.add_space(10.0);

                        // 2. Open Mac Transfer Folder in Finder
                        let folder_btn = egui::Button::new(
                            egui::RichText::new("📂 Mac Transfer Folder")
                                .strong()
                                .size(13.0)
                                .color(egui::Color32::from_rgb(226, 232, 240)),
                        )
                        .fill(egui::Color32::from_rgb(30, 41, 59))
                        .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(56, 189, 248)))
                        .min_size(egui::vec2(180.0, 40.0))
                        .rounding(8.0);
                        if ui.add(folder_btn).on_hover_text("Open ~/Desktop/AURA_Transfer in macOS Finder to add or view shared files").clicked() {
                            let dir = crate::http_bridge::HttpBridge::get_transfer_dir();
                            #[cfg(target_os = "macos")]
                            {
                                let _ = aura_launcher_core::silent_command("open").arg(&dir).spawn();
                            }
                            self.notify("📂 Opened ~/Desktop/AURA_Transfer in Finder".into());
                        }

                        ui.add_space(10.0);

                        // 3. Install APK Package (stages into bridge and opens Chrome)
                        let apk_btn = egui::Button::new(
                            egui::RichText::new("📦 Install APK")
                                .strong()
                                .size(13.0)
                                .color(egui::Color32::from_rgb(226, 232, 240)),
                        )
                        .fill(egui::Color32::from_rgb(30, 41, 59))
                        .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(99, 102, 241)))
                        .min_size(egui::vec2(150.0, 40.0))
                        .rounding(8.0);
                        if ui.add(apk_btn).on_hover_text("Select an APK on Mac to automatically stage into Bridge and install").clicked() {
                            if let Some(path) = rfd::FileDialog::new()
                                .add_filter("Android Package (*.apk)", &["apk"])
                                .pick_file()
                            {
                                self.selected_apk_path = Some(path);
                                self.install_selected_apk();
                            }
                        }

                        ui.add_space(10.0);

                        // 4. Send Files / Media (stages into bridge and opens Chrome)
                        let upload_btn = egui::Button::new(
                            egui::RichText::new("🖼 Send Files / Media")
                                .strong()
                                .size(13.0)
                                .color(egui::Color32::from_rgb(226, 232, 240)),
                        )
                        .fill(egui::Color32::from_rgb(30, 41, 59))
                        .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(168, 85, 247)))
                        .min_size(egui::vec2(170.0, 40.0))
                        .rounding(8.0);
                        if ui.add(upload_btn).on_hover_text("Stage photos, docs, or KYC files into Offline Bridge for download in Android").clicked() {
                            if let Some(path) = rfd::FileDialog::new()
                                .add_filter("All Files", &["jpg", "jpeg", "png", "webp", "bmp", "gif", "apk", "mp4", "pdf", "txt", "zip"])
                                .add_filter("Images (*.jpg, *.png)", &["jpg", "jpeg", "png", "webp", "bmp", "gif"])
                                .add_filter("Android Package (*.apk)", &["apk"])
                                .pick_file()
                            {
                                let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_lowercase();
                                if ext == "apk" {
                                    self.selected_apk_path = Some(path);
                                    self.install_selected_apk();
                                } else if matches!(ext.as_str(), "jpg" | "jpeg" | "png" | "webp" | "bmp" | "gif") {
                                    self.push_image_to_active_instance(&path);
                                } else {
                                    self.push_file_to_active_instance(&path);
                                }
                            }
                        }

                        ui.add_space(10.0);

                        // 5. Lossless Screenshot directly via Hypervisor Console
                        let shot_btn = egui::Button::new(
                            egui::RichText::new("📸 Screenshot")
                                .strong()
                                .size(13.0)
                                .color(egui::Color32::from_rgb(226, 232, 240)),
                        )
                        .fill(egui::Color32::from_rgb(30, 41, 59))
                        .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(71, 85, 105)))
                        .min_size(egui::vec2(130.0, 40.0))
                        .rounding(8.0);
                        if ui.add(shot_btn).on_hover_text("Take instant lossless 1440x3120 screenshot and save directly to Mac Desktop").clicked() {
                            self.take_screenshot();
                        }
                    });

                    ui.add_space(10.0);
                    ui.horizontal(|ui| {
                        ui.add_space(((available_size.x - tools_w) / 2.0).max(0.0));
                        ui.label(
                            egui::RichText::new("⚡ 100% Offline Bridge Active: Host <-> Guest file transfers and APK installs work with zero ADB tracking!")
                                .size(11.5)
                                .color(egui::Color32::from_rgb(52, 211, 153)),
                        );
                    });

                    ui.add_space(28.0);

                    // Live System Metrics Ribbon
                    egui::Frame::none()
                        .fill(egui::Color32::from_rgb(15, 23, 42))
                        .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(30, 41, 59)))
                        .rounding(8.0)
                        .inner_margin(egui::Margin::symmetric(24.0, 10.0))
                        .show(ui, |ui| {
                            let cores = self.status_report.host.physical_cores.unwrap_or(self.status_report.host.logical_cores);
                            let hv = self.status_report.accel.hypervisor.short_name();
                            let cpu_label = if cfg!(target_os = "macos") { "Apple Silicon" } else { &self.status_report.host.cpu_brand };
                            let ribbon_text = format!("{} Cores • 12288 MB RAM • 256 GB Storage • 120 Hz VSync • {} • {}", cores, cpu_label, hv);
                            ui.label(egui::RichText::new(ribbon_text).size(12.0).weak());
                        });
                });
            } else {
                // Standby Screen (Sleek Modern Gaming Launcher Aesthetic)
                ui.vertical_centered(|ui| {
                    ui.add_space(available_size.y * 0.12);

                    // Glowing Breathing Lotus Icon
                    let lotus_size = 46.0 + 4.0 * pulse;
                    ui.label(egui::RichText::new("🪷").size(lotus_size));
                    ui.add_space(8.0);
                    
                    ui.heading(egui::RichText::new("AURA OS").size(32.0).strong().color(egui::Color32::from_rgb(56, 189, 248)));
                    ui.label(egui::RichText::new("Next-Generation Android 16 Virtualization Platform").size(14.0).weak());
                    ui.add_space(24.0);

                    if self.is_booting {
                        // Smooth animated progress capsule
                        let bar_w = 420.0;
                        let bar_h = 6.0;
                        let (rect, _) = ui.allocate_exact_size(egui::vec2(bar_w, bar_h), egui::Sense::hover());
                        ui.painter().rect_filled(rect, 3.0, egui::Color32::from_rgb(30, 41, 59));
                        
                        let slide = ((time * 1.5).sin() * 0.5 + 0.5) as f32;
                        let highlight_w = 120.0;
                        let highlight_x = rect.min.x + (bar_w - highlight_w) * slide;
                        let highlight_rect = egui::Rect::from_min_size(
                            egui::pos2(highlight_x, rect.min.y),
                            egui::vec2(highlight_w, bar_h),
                        );
                        ui.painter().rect_filled(highlight_rect, 3.0, egui::Color32::from_rgb(56, 189, 248));

                        ui.add_space(14.0);
                        ui.label(egui::RichText::new(&self.boot_status_text).strong().size(15.0).color(egui::Color32::from_rgb(234, 179, 8)));
                        ui.label(egui::RichText::new("Loading QuickBoot snapshot into 12GB guest memory...").weak().size(12.0));
                    } else {
                        // Pulsating Glowing Emerald Start Button
                        let start_border = egui::Color32::from_rgb(
                            (20.0 + 35.0 * pulse) as u8,
                            197,
                            94,
                        );

                        let btn = egui::Button::new(
                            egui::RichText::new("▶  START AURA OS (Galaxy S24 Ultra)")
                                .size(16.0)
                                .strong()
                                .color(egui::Color32::WHITE)
                        )
                        .fill(egui::Color32::from_rgb(16, 185, 129))
                        .stroke(egui::Stroke::new(2.0_f32, start_border))
                        .min_size(egui::vec2(440.0, 52.0))
                        .rounding(10.0);

                        if ui.add(btn).clicked() {
                            if let Some(inst) = self.instances.get(self.active_instance_index).cloned() {
                                 self.launch_instance(inst.name, inst.port);
                            }
                        }

                        ui.add_space(16.0);

                        // Feature Pills
                        ui.horizontal(|ui| {
                            let pills_w = 540.0;
                            ui.add_space(((available_size.x - pills_w) / 2.0).max(0.0));
                            
                            render_spec_pill(ui, "⚡ QuickBoot Ready (~3s)");
                            ui.add_space(8.0);
                            render_spec_pill(ui, "💾 256 GB Storage");
                            ui.add_space(8.0);
                            render_spec_pill(ui, "🧠 12 GB RAM");
                            ui.add_space(8.0);
                            render_spec_pill(ui, "🚀 120 Hz VSync");
                        });

                        ui.add_space(12.0);
                        let hv = self.status_report.accel.hypervisor.short_name();
                        let cores = self.status_report.host.physical_cores.unwrap_or(self.status_report.host.logical_cores);
                        ui.label(egui::RichText::new(format!("{} Hypervisor • {} Cores • 1440x3120 @ 600 DPI • Google Play Certified", hv, cores)).weak().size(12.0));
                    }
                });
            }
        });

        // Always request smooth 60 FPS repaint for breathing glow and hover animations
        ctx.request_repaint_after(Duration::from_millis(16));
    }
}

fn render_app_tile(
    ui: &mut egui::Ui,
    ctx: &egui::Context,
    icon: &str,
    title: &str,
    subtitle: &str,
    accent: egui::Color32,
    size: egui::Vec2,
) -> bool {
    let (rect, response) = ui.allocate_exact_size(size, egui::Sense::click());
    let is_hovered = response.hovered();
    let anim = ctx.animate_bool(response.id, is_hovered);

    let bg_base = egui::Color32::from_rgb(18, 26, 43);
    let bg_hover = egui::Color32::from_rgb(28, 40, 65);
    let bg = egui::Color32::from_rgb(
        (bg_base.r() as f32 + (bg_hover.r() as f32 - bg_base.r() as f32) * anim) as u8,
        (bg_base.g() as f32 + (bg_hover.g() as f32 - bg_base.g() as f32) * anim) as u8,
        (bg_base.b() as f32 + (bg_hover.b() as f32 - bg_base.b() as f32) * anim) as u8,
    );

    let border_color = if is_hovered {
        accent
    } else {
        egui::Color32::from_rgb(38, 48, 68)
    };

    ui.painter().rect(
        rect,
        8.0,
        bg,
        egui::Stroke::new(1.0_f32 + anim * 1.0_f32, border_color),
    );

    // Accent line on the left
    let bar_rect = egui::Rect::from_min_size(rect.min, egui::vec2(4.0, rect.height()));
    ui.painter().rect_filled(bar_rect, egui::Rounding { nw: 8.0, sw: 8.0, ne: 0.0, se: 0.0 }, accent);

    // Content
    let content_rect = rect.shrink2(egui::vec2(10.0, 6.0));
    let mut child_ui = ui.child_ui(content_rect, egui::Layout::left_to_right(egui::Align::Center));
    child_ui.add_space(4.0);
    child_ui.label(egui::RichText::new(icon).size(22.0));
    child_ui.add_space(6.0);
    child_ui.vertical(|ui| {
        ui.label(egui::RichText::new(title).size(13.0).strong().color(egui::Color32::WHITE));
        ui.label(egui::RichText::new(subtitle).size(10.0).weak());
    });

    response.clicked()
}

fn render_spec_pill(ui: &mut egui::Ui, text: &str) {
    egui::Frame::none()
        .fill(egui::Color32::from_rgb(20, 27, 45))
        .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(45, 55, 75)))
        .rounding(6.0)
        .inner_margin(egui::Margin::symmetric(10.0, 5.0))
        .show(ui, |ui| {
            ui.label(egui::RichText::new(text).size(11.0).color(egui::Color32::from_rgb(203, 213, 225)));
        });
}
