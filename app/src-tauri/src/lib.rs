mod core_process;
mod runtime_manifest;
mod runtime_paths;

use core_process::CoreProcess;
use tauri::Manager;

#[tauri::command]
fn cekirdek_baslat(app: tauri::AppHandle, durum: tauri::State<CoreProcess>) -> Result<(), String> {
    durum.start(app)
}

#[tauri::command]
fn cekirdege_yaz(satir: String, durum: tauri::State<CoreProcess>) -> Result<(), String> {
    durum.send(satir)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(CoreProcess::new())
        .invoke_handler(tauri::generate_handler![cekirdek_baslat, cekirdege_yaz])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let durum = window.state::<CoreProcess>();
                durum.stop();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
