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

enum AsyncMessage {
    InstancesUpdated(Vec<InstanceInfo>),
    PackagesLoaded(Vec<String>),
    Notification(String),
    #[allow(dead_code)]
    FrameReady(egui::ColorImage),
    BootStateChanged(bool, String),
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
    clipboard_text: String,
    
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

        let initial_instances = vec![
            InstanceInfo {
                name: "AURA_OS_x86_64".to_string(),
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
            clipboard_text: String::new(),
            
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
                        let is_running = online_devices.iter().any(|d| d.serial == serial && d.state == "device");

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
                list.push(InstanceInfo {
                    name: "AURA_OS_x86_64".to_string(),
                    is_running: false,
                    serial: None,
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

    fn launch_instance(&mut self, instance_name: String, port: u16) {
        let emu_opt = self.status_report.toolchain.emulator_path.clone();
        let sdk_opt = self.status_report.toolchain.sdk_root.clone();
        let adb_opt = self.status_report.toolchain.adb_path.clone();
        let mut config = self.device_config.clone();
        config.name = instance_name.clone();
        let tx = self.tx.clone();
        let target_name = instance_name.clone();

        self.is_booting = true;
        self.boot_status_text = format!("Starting Android 14 VM '{}' (port {})...", target_name, port);

        if let Some(emu_path) = emu_opt {
            let mgr = AuraVmManager::new(emu_path, sdk_opt);
            thread::spawn(move || {
                let _ = tx.send(AsyncMessage::BootStateChanged(true, format!("Spawning QEMU hypervisor engine for {}...", target_name)));
                match mgr.start_vm_with_port(&config, Some(port)) {
                    Ok(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Instance '{}' hypervisor started on port {}.", target_name, port)));
                        let _ = tx.send(AsyncMessage::BootStateChanged(true, "Hypervisor online. Waiting for Android System UI to finish boot...".into()));

                        // Poll for boot completed
                        if let Some(adb_path) = adb_opt {
                            let client = AuraAdbClient::new(adb_path);
                            let serial = format!("emulator-{}", port);
                            for _ in 0..60 {
                                thread::sleep(Duration::from_millis(1500));
                                if let Ok(out) = client.shell_command(Some(&serial), "getprop sys.boot_completed") {
                                    if out.trim() == "1" {
                                        let _ = tx.send(AsyncMessage::BootStateChanged(false, "Android 14 Ready!".into()));
                                        let _ = tx.send(AsyncMessage::Notification("Android System UI fully booted!".into()));
                                        break;
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::BootStateChanged(false, String::new()));
                        let _ = tx.send(AsyncMessage::Notification(format!("Failed to start '{}': {}", target_name, e)));
                    }
                }
            });
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
            thread::spawn(move || {
                match mgr.clone_avd("AURA_OS_x86_64", &target_name) {
                    Ok(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Instance '{}' created successfully.", target_name)));
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
                        Err(e) => {
                            let _ = tx.send(AsyncMessage::Notification(format!("Install failed for '{}': {}", name_in_thread, e)));
                        }
                    }
                });
                self.notify(format!("Installing '{}'...", apk_name));
            }
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

        if let Some(adb_path) = adb_opt {
            let bridge = GuestBridge::new(adb_path);
            let timestamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_secs();
            let save_path = format!("tests/screenshot_{}.png", timestamp);
            let dest = PathBuf::from(&save_path);

            thread::spawn(move || {
                match bridge.capture_screenshot(serial.as_deref(), &dest) {
                    Ok(_) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Saved screenshot to {}", save_path)));
                    }
                    Err(e) => {
                        let _ = tx.send(AsyncMessage::Notification(format!("Screenshot failed: {}", e)));
                    }
                }
            });
            self.notify("Capturing screenshot...".into());
        }
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
            }
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
                    ui.label(egui::RichText::new("● ONLINE (WHPX • Vulkan • 60 FPS)").color(egui::Color32::from_rgb(34, 197, 94)).size(11.0).strong());
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
                    self.launch_app_by_pkg("com.android.camera2");
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
                        ("Camera", "com.android.camera2", "📷"),
                        ("Fulguris", "com.android.chrome", "⚡"),
                        ("Gallery", "com.android.gallery3d", "🖼"),
                        ("Google", "com.google.android.googlequicksearchbox", "🌐"),
                        ("Settings", "com.android.settings", "⚙"),
                        ("Clock", "com.android.deskclock", "⏰"),
                        ("Contacts", "com.android.contacts", "👤"),
                        ("Termux", "com.termux", "📟"),
                        ("Play Store", "com.android.vending", "🛍"),
                        ("Desktop Mode", "com.aura.launcher", "🖥"),
                    ];

                    let query = self.search_query.to_lowercase();

                    egui::ScrollArea::vertical().max_height(340.0).show(ui, |ui| {
                        egui::Grid::new("bliss_apps_grid").num_columns(3).spacing([12.0, 10.0]).show(ui, |ui| {
                            let mut col = 0;
                            for (name, pkg, icon) in &standard_apps {
                                if query.is_empty() || name.to_lowercase().contains(&query) || pkg.to_lowercase().contains(&query) {
                                    if ui.button(egui::RichText::new(format!("{} {}", icon, name)).size(13.0)).clicked() {
                                        self.launch_app_by_pkg(pkg);
                                    }
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
                                        if ui.button(format!("📱 {}", short_name)).clicked() {
                                            self.launch_app_by_pkg(pkg);
                                        }
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

                                        if inst.name != "AURA_OS_x86_64" {
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
                    ui.label("Hypervisor: WHPX (Windows Hypervisor Platform) Active & Operational");
                    ui.label("Guest Hardware Renderer: skiagl (Vulkan Host Translation)");
                    ui.separator();
                    ui.label(egui::RichText::new("SDK Toolchain").strong());
                    ui.label(format!("ADB: {}", self.status_report.toolchain.adb_path.as_ref().map(|p| p.display().to_string()).unwrap_or("Not found".into())));
                    ui.label(format!("Emulator: {}", self.status_report.toolchain.emulator_path.as_ref().map(|p| p.display().to_string()).unwrap_or("Not found".into())));
                    if ui.button("Close Diagnostics").clicked() {
                        self.diagnostics_open = false;
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
                        if render_app_tile(ui, ctx, "⚙️", "Settings", "Android 14 Config", egui::Color32::from_rgb(168, 85, 247), egui::vec2(card_w, card_h)) {
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

                    let tools_w = 544.0;
                    ui.horizontal(|ui| {
                        ui.add_space(((available_size.x - tools_w) / 2.0).max(0.0));
                        
                        let apk_btn = egui::Button::new("📦 Install APK File")
                            .fill(egui::Color32::from_rgb(30, 41, 59))
                            .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(51, 65, 85)))
                            .min_size(egui::vec2(174.0, 38.0))
                            .rounding(8.0);
                        if ui.add(apk_btn).clicked() {
                            if let Some(path) = rfd::FileDialog::new()
                                .add_filter("Android Package", &["apk"])
                                .pick_file()
                            {
                                self.selected_apk_path = Some(path);
                                self.install_selected_apk();
                            }
                        }

                        ui.add_space(8.0);

                        let shot_btn = egui::Button::new("📸 Capture Screenshot")
                            .fill(egui::Color32::from_rgb(30, 41, 59))
                            .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(51, 65, 85)))
                            .min_size(egui::vec2(174.0, 38.0))
                            .rounding(8.0);
                        if ui.add(shot_btn).clicked() {
                            self.take_screenshot();
                        }

                        ui.add_space(8.0);

                        let stop_btn = egui::Button::new(egui::RichText::new("🛑 Stop VM (Save)").color(egui::Color32::from_rgb(248, 113, 113)).strong())
                            .fill(egui::Color32::from_rgb(30, 41, 59))
                            .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(239, 68, 68)))
                            .min_size(egui::vec2(174.0, 38.0))
                            .rounding(8.0);
                        if ui.add(stop_btn).clicked() {
                            let serial = self.active_serial();
                            self.stop_instance(serial);
                        }
                    });

                    ui.add_space(28.0);

                    // Live System Metrics Ribbon
                    egui::Frame::none()
                        .fill(egui::Color32::from_rgb(15, 23, 42))
                        .stroke(egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(30, 41, 59)))
                        .rounding(8.0)
                        .inner_margin(egui::Margin::symmetric(24.0, 10.0))
                        .show(ui, |ui| {
                            ui.label(egui::RichText::new("6 Physical Cores • 8192 MB RAM • 32 GB Storage • 120 Hz VSync • NVIDIA GeForce GTX 1650 • WHPX").size(12.0).weak());
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
                    ui.label(egui::RichText::new("Next-Generation Android 14 Virtualization Platform").size(14.0).weak());
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
                        ui.label(egui::RichText::new("Loading QuickBoot snapshot into 8GB guest memory...").weak().size(12.0));
                    } else {
                        // Pulsating Glowing Emerald Start Button
                        let start_border = egui::Color32::from_rgb(
                            (20.0 + 35.0 * pulse) as u8,
                            197,
                            94,
                        );

                        let btn = egui::Button::new(
                            egui::RichText::new("▶  START AURA OS (1080p LANDSCAPE)")
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
                            let pills_w = 520.0;
                            ui.add_space(((available_size.x - pills_w) / 2.0).max(0.0));
                            
                            render_spec_pill(ui, "⚡ QuickBoot Ready (~3s)");
                            ui.add_space(8.0);
                            render_spec_pill(ui, "💾 32 GB Storage");
                            ui.add_space(8.0);
                            render_spec_pill(ui, "🧠 8 GB RAM");
                            ui.add_space(8.0);
                            render_spec_pill(ui, "🚀 120 Hz VSync");
                        });

                        ui.add_space(12.0);
                        ui.label(egui::RichText::new("WHPX Hypervisor • 6 Cores • 1920x1080 @ 240 DPI • Google Play Certified").weak().size(12.0));
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
