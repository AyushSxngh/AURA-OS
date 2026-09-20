#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod gui;

use eframe::egui;
use gui::AuraGuiApp;

fn main() -> eframe::Result<()> {
    let icon_data = match image::load_from_memory(include_bytes!("../assets/icon.png")) {
        Ok(img) => {
            let rgba = img.to_rgba8();
            let (width, height) = rgba.dimensions();
            Some(egui::IconData {
                rgba: rgba.into_raw(),
                width,
                height,
            })
        }
        Err(_) => None,
    };

    let mut viewport = egui::ViewportBuilder::default()
        .with_title("AURA OS — Android Desktop & Multi-Instance Virtualization Platform")
        .with_inner_size([1120.0, 720.0])
        .with_min_inner_size([900.0, 600.0])
        .with_active(true);

    if let Some(icon) = icon_data {
        viewport = viewport.with_icon(icon);
    }

    let native_options = eframe::NativeOptions {
        viewport,
        vsync: true,
        multisampling: 0,
        depth_buffer: 0,
        ..Default::default()
    };

    eframe::run_native(
        "AURA OS Virtualization Platform",
        native_options,
        Box::new(|cc| Box::new(AuraGuiApp::new(cc))),
    )
}
