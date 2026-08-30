mod core_process;
mod runtime_installer;
mod runtime_manager;
mod runtime_manifest;
mod runtime_paths;
mod runtime_smoke;
mod session_manager;

use std::path::PathBuf;
use std::sync::Arc;

use runtime_installer::RuntimeResources;
use runtime_manager::{CommandHealthProbe, RuntimeManager, RuntimeStatus};
use runtime_paths::RuntimePaths;
use session_manager::{SessionManager, SessionSnapshot, VARSAYILAN_OTURUM};
use tauri::{Emitter, Manager};

/// Bu makinenin çalışma zamanı paketiyle eşleşmesi gereken hedef üçlü.
///
/// Değer `runtime-manifest.json` içindeki `target` alanıyla
/// `RuntimeManifest::validate` tarafından karşılaştırılır ve
/// `desktop_build/runtime/build_runtime.py` içindeki `platform_target` ile
/// AYNI dizeleri üretmek zorundadır: ikisi ayrışırsa paket kurulur ama
/// doğrulama reddeder. Desteklenmeyen bir platformda derlemeyi sessizce
/// yanlış bir üçlüyle sürdürmek yerine derleme zamanında durulur.
fn beklenen_hedef() -> String {
    #[cfg(target_os = "macos")]
    {
        format!("{}-apple-darwin", std::env::consts::ARCH)
    }
    #[cfg(target_os = "windows")]
    {
        format!("{}-pc-windows-msvc", std::env::consts::ARCH)
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        compile_error!("Fusion masaüstü yalnız macOS ve Windows hedefler")
    }
}

/// Geliştirici Kipi geçersiz kılması: paketlenmiş, doğrulanmış çalışma
/// zamanını atlayıp elle verilen bir ikiliyi çalıştırmayı sağlar. YALNIZ
/// hata ayıklama derlemesinde ve `FUSION_DEVELOPER_RUNTIME` ortam değişkeni
/// açıkça tam bir yol içeriyorsa devreye girer; devreye girdiğinde bunu
/// STDERR'e görünür bir uyarı olarak yazar. Release derlemesinde bu
/// fonksiyon `#[cfg(not(debug_assertions))]` sürümü nedeniyle ortam
/// değişkenini HİÇ okumaz — kullanıcının makinesindeki rastgele bir ortam
/// değişkeni paketlenmiş çalışma zamanının yerine asla geçemez.
#[cfg(debug_assertions)]
fn gelistirici_calisma_zamani_override(ortam: impl Fn(&str) -> Option<String>) -> Option<PathBuf> {
    let yol = ortam("FUSION_DEVELOPER_RUNTIME")?;
    let yol = yol.trim();
    if yol.is_empty() {
        return None;
    }
    eprintln!(
        "[Geliştirici Kipi] UYARI: paketlenmiş çalışma zamanı ATLANIYOR; \
         FUSION_DEVELOPER_RUNTIME kullanılıyor: {yol}"
    );
    Some(PathBuf::from(yol))
}

#[cfg(not(debug_assertions))]
fn gelistirici_calisma_zamani_override(_ortam: impl Fn(&str) -> Option<String>) -> Option<PathBuf> {
    None
}

#[tauri::command]
fn cekirdek_baslat(
    app: tauri::AppHandle,
    runtime: tauri::State<RuntimeManager>,
    sessions: tauri::State<SessionManager>,
) -> Result<(), String> {
    let executable = runtime_executable(&runtime)?;
    sessions
        .start(app, &executable, VARSAYILAN_OTURUM, None)
        .map(|_| ())
}

#[tauri::command]
fn cekirdege_yaz(satir: String, sessions: tauri::State<SessionManager>) -> Result<(), String> {
    sessions.send(VARSAYILAN_OTURUM, satir)
}

fn runtime_executable(runtime: &RuntimeManager) -> Result<PathBuf, String> {
    match gelistirici_calisma_zamani_override(|anahtar| std::env::var(anahtar).ok()) {
        Some(yol) => Ok(yol),
        None => runtime.executable().map_err(|error| error.to_string()),
    }
}

#[tauri::command]
fn oturum_olustur(
    app: tauri::AppHandle,
    runtime: tauri::State<RuntimeManager>,
    sessions: tauri::State<SessionManager>,
    oturum_id: String,
    kok: Option<String>,
) -> Result<SessionSnapshot, String> {
    let executable = runtime_executable(&runtime)?;
    let root = kok.as_deref().map(std::path::Path::new);
    sessions.start(app, &executable, &oturum_id, root)
}

#[tauri::command]
fn oturuma_yaz(
    oturum_id: String,
    satir: String,
    sessions: tauri::State<SessionManager>,
) -> Result<(), String> {
    sessions.send(&oturum_id, satir)
}

#[tauri::command]
fn oturum_kapat(oturum_id: String, sessions: tauri::State<SessionManager>) -> Result<(), String> {
    sessions.stop(&oturum_id)
}

#[tauri::command]
fn oturumlari_listele(sessions: tauri::State<SessionManager>) -> Vec<SessionSnapshot> {
    sessions.list()
}

/// Arayüzün gösterebileceği güncel çalışma zamanı durumunu döner.
///
/// Ağ çağrısı yapmaz, dosya değiştirmez; yalnızca en son `prepare`/`repair`
/// sonucunun senkron anlık görüntüsüdür (bkz. `RuntimeManager::status`).
#[tauri::command]
fn runtime_durum(manager: tauri::State<RuntimeManager>) -> RuntimeStatus {
    manager.status()
}

/// Çalışma zamanını kullanıma hazırlar (ilk kurulum ya da güncelleme).
///
/// Sağlık denetimi (dolayısıyla olası askıda kalma riski taşıyan tek adım)
/// `RuntimeManager`/`CommandHealthProbe` içinde 30 saniyelik sabit bir zaman
/// aşımına bağlıdır (`SAGLIK_ZAMAN_ASIMI`); bu komut o sınırı OLDUĞU GİBİ
/// aşağı taşır ve asla kendi başına ek bir bekleme eklemez. `spawn_blocking`
/// kullanılması, senkron kurulum/sağlık kodunun Tauri'nin async çalışma
/// zamanını TIKAMAMASI içindir; arayüz bu süre boyunca `runtime-ilerleme`
/// olaylarını dinleyerek kullanıcıya ilerleme gösterebilir.
#[tauri::command]
async fn runtime_hazirla(
    app: tauri::AppHandle,
    manager: tauri::State<'_, RuntimeManager>,
) -> Result<RuntimeStatus, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        manager
            .prepare(|progress| {
                let _ = app.emit("runtime-ilerleme", progress);
            })
            .map(RuntimeStatus::ready)
            .map_err(|error| error.to_string())
    })
    .await
    .map_err(|error| format!("Çalışma zamanı görevi tamamlanamadı: {error}"))?
}

/// Paket sürümünü, kullanıcı verisine dokunmadan yeniden kurmayı dener.
///
/// Aynı zaman aşımı/ilerleme garantisi `runtime_hazirla` ile paylaşılır;
/// bkz. oradaki belge notu.
#[tauri::command]
async fn runtime_onar(
    app: tauri::AppHandle,
    manager: tauri::State<'_, RuntimeManager>,
) -> Result<RuntimeStatus, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        manager
            .repair(|progress| {
                let _ = app.emit("runtime-ilerleme", progress);
            })
            .map(RuntimeStatus::ready)
            .map_err(|error| error.to_string())
    })
    .await
    .map_err(|error| format!("Onarım görevi tamamlanamadı: {error}"))?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    if runtime_smoke::requested(std::env::args_os()) {
        let exit_code = match runtime_smoke::run_from_bundle() {
            Ok(()) => 0,
            Err(error) => {
                eprintln!("[fusion][runtime-smoke] {error}");
                1
            }
        };
        std::process::exit(exit_code);
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(SessionManager::new())
        .setup(|app| {
            let resources = RuntimeResources::from_app(app.handle())?;
            let ev_dizini = app.path().home_dir()?;
            let paths = RuntimePaths::for_home(&ev_dizini);
            let manager = RuntimeManager::new(
                resources,
                paths,
                beklenen_hedef(),
                Arc::new(CommandHealthProbe),
            );
            app.manage(manager);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            cekirdek_baslat,
            cekirdege_yaz,
            oturum_olustur,
            oturuma_yaz,
            oturum_kapat,
            oturumlari_listele,
            runtime_durum,
            runtime_hazirla,
            runtime_onar
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let sessions = window.state::<SessionManager>();
                sessions.stop_all();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
