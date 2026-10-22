use aura_launcher_core::{PlatformStatusReport, VirtualDeviceConfig};
use aura_vm_manager::{AuraAdbClient, AuraVmManager, GuestBridge, PerformanceProfiler};
use std::env;
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = env::args().collect();
    let command = args.get(1).map(|s| s.as_str()).unwrap_or("info");

    println!("====================================================");
    println!("        AURA OS — Android Virtualization Platform   ");
    println!("        Platform Engine & Launcher Core v0.3.0       ");
    println!("====================================================\n");

    match command {
        "info" => print_info(),
        "doctor" => run_doctor(),
        "devices" => list_devices(),
        "config" => print_config(),
        "create" => create_device(args.get(2).map(|s| s.as_str())),
        "start" => start_device(args.get(2).map(|s| s.as_str())),
        "stop" => stop_device(args.get(2).map(|s| s.as_str())),
        "status" => check_status(args.get(2).map(|s| s.as_str())),
        "install" => install_apk(args.get(2).map(|s| s.as_str()), args.get(3).map(|s| s.as_str())),
        "uninstall" => uninstall_apk(args.get(2).map(|s| s.as_str()), args.get(3).map(|s| s.as_str())),
        "packages" => list_packages(args.get(2).map(|s| s.as_str()), args.get(3).map(|s| s.as_str())),
        "push" => bridge_push(args.get(2).map(|s| s.as_str()), args.get(3).map(|s| s.as_str())),
        "pull" => bridge_pull(args.get(2).map(|s| s.as_str()), args.get(3).map(|s| s.as_str())),
        "export-apk" => export_apk_cli(args.get(2).map(|s| s.as_str()), args.get(3).map(|s| s.as_str())),
        "export-file" => export_file_cli(args.get(2).map(|s| s.as_str()), args.get(3).map(|s| s.as_str())),
        "clipboard" => bridge_clipboard(args.get(2).map(|s| s.as_str())),
        "screenshot" => bridge_screenshot(args.get(2).map(|s| s.as_str())),
        "benchmark" => run_benchmark(args.get(2).map(|s| s.as_str())),
        "help" | "--help" | "-h" => print_help(),
        other => {
            eprintln!("Unknown command: '{}'\n", other);
            print_help();
            std::process::exit(1);
        }
    }
}

fn print_info() {
    let report = PlatformStatusReport::generate();
    println!("--- HOST OS & CPU HARDWARE ---");
    println!("  Operating System : {:?}", report.host.os);
    println!("  OS Version       : {}", report.host.os_version);
    println!("  CPU Architecture : {:?}", report.host.arch);
    println!("  CPU Brand        : {}", report.host.cpu_brand);
    println!("  Logical Cores    : {}", report.host.logical_cores);
    println!("  Physical Cores   : {:?}", report.host.physical_cores.unwrap_or(0));
    println!("  Total System RAM : {} MB", report.host.total_memory_mb);
    println!("  Available RAM    : {} MB\n", report.host.available_memory_mb);

    println!("--- HARDWARE VIRTUALIZATION ACCELERATION ---");
    println!("  Hypervisor Type  : {:?}", report.accel.hypervisor);
    println!("  Supported        : {}", report.accel.is_supported);
    println!("  Enabled          : {}", report.accel.is_enabled);
    println!("  Details          : {}\n", report.accel.details);

    println!("--- ANDROID TOOLCHAIN RESOLUTION ---");
    println!("  SDK Root         : {:?}", report.toolchain.sdk_root.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "Not Found".to_string()));
    println!("  ADB Path         : {:?}", report.toolchain.adb_path.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "Not Found".to_string()));
    println!("  ADB Version      : {}", report.toolchain.adb_version.as_deref().unwrap_or("Unknown"));
    println!("  Emulator Path    : {:?}", report.toolchain.emulator_path.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "Not Found".to_string()));
    println!("  Emulator Version : {}", report.toolchain.emulator_version.as_deref().unwrap_or("Unknown"));
    println!("  JDK Path         : {:?}", report.toolchain.jdk_path.as_ref().map(|p| p.display().to_string()).unwrap_or_else(|| "Not Found".to_string()));
    println!("  JDK Version      : {}", report.toolchain.jdk_version.as_deref().unwrap_or("Unknown"));
    println!("  Build Tools      : {:?}", report.toolchain.installed_build_tools);
    println!("  Platforms        : {:?}\n", report.toolchain.installed_platforms);

    println!("--- STATUS SUMMARY ---");
    println!("  Ready for Virtualization: {}", report.is_ready_for_virtualization);
}

fn run_doctor() {
    let report = PlatformStatusReport::generate();
    println!("Running AURA OS Environment Diagnostic Audit...\n");

    if report.actionable_errors.is_empty() {
        println!("[SUCCESS] No critical platform errors found.");
    } else {
        println!("[CRITICAL ERRORS FOUND]:");
        for err in &report.actionable_errors {
            println!("  - {}", err);
        }
    }

    if !report.actionable_warnings.is_empty() {
        println!("\n[ACTIONABLE WARNINGS]:");
        for warn in &report.actionable_warnings {
            println!("  - {}", warn);
        }
    }
}

fn list_devices() {
    let report = PlatformStatusReport::generate();
    println!("Checking connected ADB devices and configured AVDs...\n");

    if let Some(adb_path) = report.toolchain.adb_path {
        let adb = AuraAdbClient::new(adb_path);
        match adb.list_devices() {
            Ok(devices) => {
                println!("Connected ADB Devices ({}):", devices.len());
                for dev in devices {
                    println!("  - Serial: {}, State: {}", dev.serial, dev.state);
                }
            }
            Err(e) => eprintln!("Failed to query ADB devices: {}", e),
        }
    } else {
        println!("ADB binary unavailable.");
    }

    if let Some(emu_path) = report.toolchain.emulator_path {
        let vm_mgr = AuraVmManager::new(emu_path, report.toolchain.sdk_root);
        match vm_mgr.list_avds() {
            Ok(avds) => {
                println!("\nConfigured Virtual Devices (AVDs) ({}):", avds.len());
                if avds.is_empty() {
                    println!("  (No AVDs configured yet)");
                } else {
                    for avd in avds {
                        println!("  - AVD: {}", avd);
                    }
                }
            }
            Err(e) => eprintln!("Failed to list AVDs: {}", e),
        }
    } else {
        println!("Android Emulator binary unavailable.");
    }
}

fn create_device(name_opt: Option<&str>) {
    let report = PlatformStatusReport::generate();
    let emu_path = match report.toolchain.emulator_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] Emulator binary not found in Android SDK.");
            return;
        }
    };

    let vm_mgr = AuraVmManager::new(emu_path, report.toolchain.sdk_root);
    let mut config = VirtualDeviceConfig::default();
    if let Some(name) = name_opt {
        config.name = name.to_string();
    }

    let is_arm = cfg!(target_arch = "aarch64") || config.abi == aura_launcher_core::GuestAbi::Arm64V8a;
    let arch_str = if is_arm { "arm64-v8a" } else { "x86_64" };
    let sys_pkg = format!("system-images;android-34;google_apis_playstore;{}", arch_str);
    println!("Creating AURA OS Virtual Device '{}' using guest package '{}'...", config.name, sys_pkg);

    match vm_mgr.create_avd(&config.name, &sys_pkg) {
        Ok(_) => println!("[SUCCESS] AVD '{}' created successfully via avdmanager.", config.name),
        Err(e) => println!("[INFO] avdmanager output / creation status: {}", e),
    }

    println!("Applying custom AURA OS hardware profile config to config.ini...");
    match vm_mgr.configure_avd_ini(&config.name, &config) {
        Ok(_) => println!("[SUCCESS] Configured and tuned AVD profile at .android/avd/{}.avd/config.ini", config.name),
        Err(e) => eprintln!("[ERROR] Failed to configure AVD profile: {}", e),
    }
}

fn start_device(name_opt: Option<&str>) {
    let report = PlatformStatusReport::generate();
    let emu_path = match report.toolchain.emulator_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] Emulator binary not found in Android SDK.");
            return;
        }
    };

    let vm_mgr = AuraVmManager::new(emu_path, report.toolchain.sdk_root);
    let mut config = VirtualDeviceConfig::default();
    if let Some(name) = name_opt {
        config.name = name.to_string();
    }

    println!("Starting AURA OS Virtual Device '{}' with hardware acceleration (WHPX)...", config.name);
    match vm_mgr.start_vm(&config) {
        Ok(child) => println!("[SUCCESS] Virtual Machine process spawned successfully. PID: {}", child.id()),
        Err(e) => eprintln!("[ERROR] Failed to start virtual machine: {}", e),
    }
}

fn stop_device(serial_opt: Option<&str>) {
    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let adb = AuraAdbClient::new(adb_path);
    println!("Sending graceful shutdown command to virtual machine...");
    match adb.stop_emulator(serial_opt) {
        Ok(_) => println!("[SUCCESS] Stop command delivered to virtual device."),
        Err(e) => eprintln!("[ERROR] Failed to stop virtual device: {}", e),
    }
}

fn check_status(serial_opt: Option<&str>) {
    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let adb = AuraAdbClient::new(adb_path);
    let is_booted = adb.is_boot_completed(serial_opt);
    println!("Virtual Machine Boot Status:");
    if is_booted {
        println!("  State: RUNNING & BOOT COMPLETED (sys.boot_completed = 1)");
    } else {
        println!("  State: BOOTING / NOT READY");
    }
}

fn install_apk(apk_path_str: Option<&str>, serial_opt: Option<&str>) {
    let apk_str = match apk_path_str {
        Some(s) => s,
        None => {
            eprintln!("Usage: aura-cli install <PATH_TO_APK> [DEVICE_SERIAL]");
            return;
        }
    };

    let apk_path = PathBuf::from(apk_str);
    if !apk_path.exists() {
        eprintln!("[ERROR] APK file not found at '{}'", apk_path.display());
        return;
    }

    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let adb = AuraAdbClient::new(adb_path);
    println!("Installing APK '{}' to virtual device...", apk_path.display());
    match adb.install_apk(serial_opt, &apk_path) {
        Ok(res) => println!("[SUCCESS] APK installed successfully: {}", res),
        Err(e) => eprintln!("[ERROR] APK installation failed: {}", e),
    }
}

fn uninstall_apk(pkg_str: Option<&str>, serial_opt: Option<&str>) {
    let package_name = match pkg_str {
        Some(s) => s,
        None => {
            eprintln!("Usage: aura-cli uninstall <PACKAGE_NAME> [DEVICE_SERIAL]");
            return;
        }
    };

    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let adb = AuraAdbClient::new(adb_path);
    println!("Uninstalling package '{}' from virtual device...", package_name);
    match adb.uninstall_apk(serial_opt, package_name) {
        Ok(res) => println!("[SUCCESS] Package uninstalled successfully: {}", res),
        Err(e) => eprintln!("[ERROR] Uninstall failed: {}", e),
    }
}

fn list_packages(filter_opt: Option<&str>, serial_opt: Option<&str>) {
    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let adb = AuraAdbClient::new(adb_path);
    match adb.list_packages(serial_opt) {
        Ok(pkgs) => {
            let filtered: Vec<&String> = if let Some(q) = filter_opt {
                pkgs.iter().filter(|p| p.to_lowercase().contains(&q.to_lowercase())).collect()
            } else {
                pkgs.iter().collect()
            };

            if let Some(q) = filter_opt {
                println!("Packages matching '{}' ({} of {} total):", q, filtered.len(), pkgs.len());
            } else {
                println!("Installed Packages ({}):", filtered.len());
            }

            for pkg in filtered {
                println!("  - {}", pkg);
            }
        }
        Err(e) => eprintln!("[ERROR] Failed to list packages: {}", e),
    }
}

fn bridge_push(host_path_opt: Option<&str>, guest_path_opt: Option<&str>) {
    let (h_str, g_str) = match (host_path_opt, guest_path_opt) {
        (Some(h), Some(g)) => (h, g),
        _ => {
            eprintln!("Usage: aura-cli push <HOST_FILE_PATH> <GUEST_DESTINATION_PATH>");
            return;
        }
    };

    let host_path = PathBuf::from(h_str);
    if !host_path.exists() {
        eprintln!("[ERROR] Host file not found at '{}'", host_path.display());
        return;
    }

    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let bridge = GuestBridge::new(adb_path);
    println!("Pushing '{}' to guest '{}'...", host_path.display(), g_str);
    match bridge.push_file(None, &host_path, g_str) {
        Ok(res) => println!("[SUCCESS] File transferred: {}", res),
        Err(e) => eprintln!("[ERROR] Push failed: {}", e),
    }
}

fn bridge_pull(guest_path_opt: Option<&str>, host_dest_opt: Option<&str>) {
    let (g_str, h_str) = match (guest_path_opt, host_dest_opt) {
        (Some(g), Some(h)) => (g, h),
        _ => {
            eprintln!("Usage: aura-cli pull <GUEST_FILE_PATH> <HOST_DESTINATION_PATH>");
            return;
        }
    };

    let host_path = PathBuf::from(h_str);
    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let bridge = GuestBridge::new(adb_path);
    println!("Pulling '{}' from guest to '{}'...", g_str, host_path.display());
    match bridge.pull_file(None, g_str, &host_path) {
        Ok(res) => println!("[SUCCESS] File pulled: {}", res),
        Err(e) => eprintln!("[ERROR] Pull failed: {}", e),
    }
}

fn export_apk_cli(pkg_opt: Option<&str>, dest_opt: Option<&str>) {
    let pkg = match pkg_opt {
        Some(p) => p,
        None => {
            eprintln!("Usage: aura-cli export-apk <PACKAGE_NAME> [LOCAL_DEST_PATH]");
            return;
        }
    };
    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };
    let client = AuraAdbClient::new(adb_path);
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let default_dest = PathBuf::from(home).join("Desktop").join("AURA_Exported");
    let dest_path = dest_opt.map(PathBuf::from).unwrap_or(default_dest);

    println!("Locating installed APK for package '{}'...", pkg);
    match client.export_apk(None, pkg, &dest_path) {
        Ok(out_file) => {
            println!("[SUCCESS] APK exported to '{}'", out_file.display());
            let _ = aura_launcher_core::silent_command("open").arg("-R").arg(&out_file).output();
        }
        Err(e) => eprintln!("[ERROR] Export APK failed: {}", e),
    }
}

fn export_file_cli(remote_path_opt: Option<&str>, dest_opt: Option<&str>) {
    let remote_path = match remote_path_opt {
        Some(p) => p,
        None => {
            eprintln!("Usage: aura-cli export-file <REMOTE_PATH> [LOCAL_DEST_PATH]");
            return;
        }
    };
    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };
    let client = AuraAdbClient::new(adb_path);
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let default_dest = PathBuf::from(home).join("Desktop").join("AURA_Exported");
    let dest_path = dest_opt.map(PathBuf::from).unwrap_or(default_dest);

    println!("Exporting '{}' from guest...", remote_path);
    match client.export_file(None, remote_path, &dest_path) {
        Ok(out_file) => {
            println!("[SUCCESS] File exported to '{}'", out_file.display());
            let _ = aura_launcher_core::silent_command("open").arg("-R").arg(&out_file).output();
        }
        Err(e) => eprintln!("[ERROR] Export file failed: {}", e),
    }
}

fn bridge_clipboard(text_opt: Option<&str>) {
    let text = match text_opt {
        Some(t) => t,
        None => {
            eprintln!("Usage: aura-cli clipboard <TEXT_TO_SEND>");
            return;
        }
    };

    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let bridge = GuestBridge::new(adb_path);
    println!("Injecting clipboard text into guest: \"{}\"...", text);
    match bridge.send_text(None, text) {
        Ok(_) => println!("[SUCCESS] Clipboard text injected."),
        Err(e) => eprintln!("[ERROR] Clipboard injection failed: {}", e),
    }
}

fn bridge_screenshot(output_path_opt: Option<&str>) {
    let out_str = output_path_opt.unwrap_or("screenshot.png");
    let out_path = PathBuf::from(out_str);

    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let bridge = GuestBridge::new(adb_path);
    println!("Capturing guest display screenshot to '{}'...", out_path.display());
    match bridge.capture_screenshot(None, &out_path) {
        Ok(_) => println!("[SUCCESS] Screenshot captured and saved: '{}'", out_path.display()),
        Err(e) => eprintln!("[ERROR] Screenshot failed: {}", e),
    }
}

fn run_benchmark(serial_opt: Option<&str>) {
    let report = PlatformStatusReport::generate();
    let adb_path = match report.toolchain.adb_path {
        Some(p) => p,
        None => {
            eprintln!("[ERROR] ADB binary not found.");
            return;
        }
    };

    let profiler = PerformanceProfiler::new(adb_path);
    println!("Executing AURA OS Guest Performance Benchmark...");
    println!("Sampling guest CPU topology, memory pressure, cold app start latency, and GPU renderer...\n");

    match profiler.run_benchmark(serial_opt) {
        Ok(bench) => {
            println!("====================================================");
            println!("           AURA OS PERFORMANCE BENCHMARK REPORT    ");
            println!("====================================================");
            println!("  Guest Boot Status        : Online & Verified");
            println!("  Allocated Guest Cores    : {} cores", bench.cpu_cores_guest);
            println!("  CPU BogoMips Rating      : {:.2}", bench.cpu_bogo_mips.unwrap_or(0.0));
            println!("  Total Guest Memory       : {} MB ({} KB)", bench.total_memory_kb / 1024, bench.total_memory_kb);
            println!("  Available Guest Memory   : {} MB ({} KB)", bench.free_memory_kb / 1024, bench.free_memory_kb);
            println!("  Cold App Launch Latency  : {} ms", bench.app_launch_ms.unwrap_or(0));
            println!("  Graphics HWUI Pipeline   : {}", bench.graphics_pipeline);
            println!("====================================================");
            println!("\n[SUCCESS] Performance profile captured successfully.");
        }
        Err(e) => eprintln!("[ERROR] Benchmark execution failed: {}", e),
    }
}

fn print_config() {
    let config = VirtualDeviceConfig::default();
    println!("Default AURA OS Virtual Device Profile:");
    println!("{}", serde_json::to_string_pretty(&config).unwrap());
}

fn print_help() {
    println!("Usage: aura-cli [COMMAND] [ARGS]\n");
    println!("Commands:");
    println!("  info                               Display host environment, hardware acceleration, and toolchain info");
    println!("  doctor                             Perform platform diagnostic checks and report actionable issues");
    println!("  devices                            List active ADB devices and configured AVDs");
    println!("  create [NAME]                      Create/configure a virtual device profile");
    println!("  start [NAME]                       Start virtual machine process");
    println!("  stop [SERIAL]                      Gracefully stop virtual machine process");
    println!("  status [SERIAL]                    Poll virtual machine boot and runtime status");
    println!("  install <APK_PATH> [SERIAL]        Install an Android APK onto virtual device");
    println!("  uninstall <PACKAGE> [SERIAL]       Uninstall an application package from virtual device");
    println!("  packages [FILTER] [SERIAL]         List installed application packages on virtual device");
    println!("  push <SRC> <DST>                   Push file from host to guest Android");
    println!("  pull <SRC> <DST>                   Pull file from guest Android to host");
    println!("  export-apk <PACKAGE> [DEST]        Extract and export installed APK from virtual device to host");
    println!("  export-file <REMOTE_PATH> [DEST]   Export file or folder from virtual device to host Mac");
    println!("  clipboard <TEXT>                   Inject clipboard text into active guest");
    println!("  screenshot [OUTPUT_PNG]            Capture instant PNG screenshot of guest display");
    println!("  benchmark [SERIAL]                 Profile guest CPU, RAM, app latency, and GPU pipeline");
    println!("  config                             Print default virtual device configuration");
    println!("  help                               Show this help message");
}


