mod core_process;
mod permissions;
mod runtime_installer;
mod runtime_manager;
mod runtime_manifest;
mod runtime_paths;
mod runtime_smoke;
mod session_manager;
mod speech;

use std::path::PathBuf;
use std::sync::Arc;

use permissions::{izin_ayarlari_ac, izin_durumu, izin_iste};
use runtime_installer::RuntimeResources;
use runtime_manager::{CommandHealthProbe, RuntimeManager, RuntimeStatus};
use runtime_paths::RuntimePaths;
use session_manager::{SessionManager, SessionSnapshot, VARSAYILAN_OTURUM};
use speech::{cleanup_for_window, start_recognition, SpeechManager};
use tauri::{Emitter, Manager, WebviewUrl, WebviewWindowBuilder};

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

/// Konuşma penceresinin kimliği. Ana pencereden AYRI bir penceredir.
const SES_PENCERESI: &str = "ses";
const SES_NORMAL_BOYUT: (f64, f64) = (380.0, 460.0);
const SES_NORMAL_MIN_BOYUT: (f64, f64) = (360.0, 420.0);
const SES_NORMAL_MAX_BOYUT: (f64, f64) = (520.0, 720.0);
const SES_MINI_BOYUT: (f64, f64) = (360.0, 112.0);

#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
struct VoiceWindowGeometry {
    x: Option<f64>,
    y: Option<f64>,
    normal_width: f64,
    normal_height: f64,
    wide: bool,
    on_top: bool,
}

#[derive(Debug, PartialEq)]
struct VoiceGeometryPlan {
    position: Option<(f64, f64)>,
    size: (f64, f64),
    min_size: Option<(f64, f64)>,
    max_size: Option<(f64, f64)>,
    resizable: bool,
    on_top: Option<bool>,
}

#[derive(Debug, Clone, Copy)]
enum VoiceWindowLifecycle {
    Minimize,
    Close,
}

#[derive(Debug, PartialEq)]
struct VoiceWindowLifecyclePlan {
    minimize_voice: bool,
    close_voice: bool,
    restore_main: bool,
    stop_recognition: bool,
}

fn voice_window_lifecycle_plan(lifecycle: VoiceWindowLifecycle) -> VoiceWindowLifecyclePlan {
    match lifecycle {
        VoiceWindowLifecycle::Minimize => VoiceWindowLifecyclePlan {
            minimize_voice: true,
            close_voice: false,
            restore_main: false,
            stop_recognition: false,
        },
        VoiceWindowLifecycle::Close => VoiceWindowLifecyclePlan {
            minimize_voice: false,
            close_voice: true,
            restore_main: true,
            stop_recognition: true,
        },
    }
}

fn voice_geometry_plan(geometry: &VoiceWindowGeometry) -> VoiceGeometryPlan {
    let position = geometry.x.zip(geometry.y);
    if geometry.wide {
        VoiceGeometryPlan {
            position,
            size: (
                geometry
                    .normal_width
                    .clamp(SES_NORMAL_MIN_BOYUT.0, SES_NORMAL_MAX_BOYUT.0),
                geometry
                    .normal_height
                    .clamp(SES_NORMAL_MIN_BOYUT.1, SES_NORMAL_MAX_BOYUT.1),
            ),
            min_size: Some(SES_NORMAL_MIN_BOYUT),
            max_size: Some(SES_NORMAL_MAX_BOYUT),
            resizable: true,
            on_top: Some(geometry.on_top),
        }
    } else {
        VoiceGeometryPlan {
            position,
            size: SES_MINI_BOYUT,
            min_size: None,
            max_size: None,
            resizable: false,
            on_top: Some(geometry.on_top),
        }
    }
}

fn voice_size_plan(wide: bool) -> VoiceGeometryPlan {
    VoiceGeometryPlan {
        position: None,
        size: if wide {
            SES_NORMAL_BOYUT
        } else {
            SES_MINI_BOYUT
        },
        min_size: wide.then_some(SES_NORMAL_MIN_BOYUT),
        max_size: wide.then_some(SES_NORMAL_MAX_BOYUT),
        resizable: wide,
        on_top: None,
    }
}

fn apply_voice_geometry(
    window: &tauri::WebviewWindow,
    plan: &VoiceGeometryPlan,
) -> Result<(), String> {
    window
        .set_min_size(None::<tauri::LogicalSize<f64>>)
        .map_err(|error| error.to_string())?;
    window
        .set_max_size(None::<tauri::LogicalSize<f64>>)
        .map_err(|error| error.to_string())?;
    window
        .set_resizable(plan.resizable)
        .map_err(|error| error.to_string())?;
    window
        .set_size(tauri::LogicalSize::new(plan.size.0, plan.size.1))
        .map_err(|error| error.to_string())?;
    window
        .set_min_size(
            plan.min_size
                .map(|(width, height)| tauri::LogicalSize::new(width, height)),
        )
        .map_err(|error| error.to_string())?;
    window
        .set_max_size(
            plan.max_size
                .map(|(width, height)| tauri::LogicalSize::new(width, height)),
        )
        .map_err(|error| error.to_string())?;
    if let Some((x, y)) = plan.position {
        window
            .set_position(tauri::LogicalPosition::new(x, y))
            .map_err(|error| error.to_string())?;
    }
    if let Some(on_top) = plan.on_top {
        window
            .set_always_on_top(on_top)
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

/// Konuşma kipini aç: ana pencereyi simge durumuna küçült, küçük konuşma
/// penceresini göster.
///
/// Kullanıcının istediği davranış tam olarak budur: mikrofona basınca ana
/// pencere sarı düğmedeki gibi çekilir, konuşma için küçük bir pencere kalır ve
/// istenildiğinde ana pencere geri açılır. Bunu uygulama İÇİNDE bir katmanla
/// yapmak aynı şey değildir — pencere yöneticisi devreye girmez.
#[tauri::command]
async fn ses_penceresi_ac(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(mevcut) = app.get_webview_window(SES_PENCERESI) {
        mevcut.show().map_err(|e| e.to_string())?;
        mevcut.set_focus().map_err(|e| e.to_string())?;
    } else {
        WebviewWindowBuilder::new(
            &app,
            SES_PENCERESI,
            WebviewUrl::App("index.html?pencere=ses".into()),
        )
        .title("Fusion ile konuş")
        .inner_size(SES_NORMAL_BOYUT.0, SES_NORMAL_BOYUT.1)
        .min_inner_size(SES_NORMAL_MIN_BOYUT.0, SES_NORMAL_MIN_BOYUT.1)
        .max_inner_size(SES_NORMAL_MAX_BOYUT.0, SES_NORMAL_MAX_BOYUT.1)
        .resizable(true)
        .always_on_top(true)
        .decorations(false)
        .shadow(false)
        .center()
        .build()
        .map_err(|error| format!("konuşma penceresi açılamadı: {error}"))?;
    }
    // Ana pencere simge durumuna küçülür; kapanmaz. Kapatmak, çalışan turu ve
    // oturumları da sonlandırırdı.
    if let Some(ana) = app.get_webview_window("main") {
        ana.minimize().map_err(|error| error.to_string())?;
    }
    Ok(())
}

/// Konuşma penceresini kapatmadan sistemin simge durumuna küçültür.
/// Tanıma sürer; pencere geri açıldığında aynı tur görünür.
#[tauri::command]
fn ses_penceresi_simge_durumu(app: tauri::AppHandle) -> Result<(), String> {
    let plan = voice_window_lifecycle_plan(VoiceWindowLifecycle::Minimize);
    if plan.minimize_voice {
        if let Some(ses) = app.get_webview_window(SES_PENCERESI) {
            ses.minimize().map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

/// Konuşma penceresinin boyutunu değiştir.
///
/// İki ölçü vardır: `dar` yalnız karakter ve mikrofon (masaüstünün köşesinde
/// durur), `genis` dökümü ve ayarları da gösterir. Boyut Rust tarafında
/// uygulanır çünkü pencere çerçevesizdir ve web tarafı kendi kabuğunu
/// büyütemez.
#[tauri::command]
fn ses_penceresi_boyut(app: tauri::AppHandle, genis: bool) -> Result<(), String> {
    let Some(pencere) = app.get_webview_window(SES_PENCERESI) else {
        return Err("konuşma penceresi açık değil".to_string());
    };
    apply_voice_geometry(&pencere, &voice_size_plan(genis))
}

#[tauri::command]
fn ses_penceresi_geometri_uygula(
    app: tauri::AppHandle,
    geometry: VoiceWindowGeometry,
) -> Result<(), String> {
    let Some(pencere) = app.get_webview_window(SES_PENCERESI) else {
        return Err("konuşma penceresi açık değil".to_string());
    };
    apply_voice_geometry(&pencere, &voice_geometry_plan(&geometry))
}

/// Konuşma penceresi hep üstte kalsın mı?
#[tauri::command]
fn ses_penceresi_ustte(app: tauri::AppHandle, ustte: bool) -> Result<(), String> {
    let Some(pencere) = app.get_webview_window(SES_PENCERESI) else {
        return Err("konuşma penceresi açık değil".to_string());
    };
    pencere
        .set_always_on_top(ustte)
        .map_err(|error| error.to_string())
}

/// Kapatma onaylandı: oturumları durdur ve uygulamadan çık.
#[tauri::command]
fn kapatmayi_onayla(app: tauri::AppHandle) {
    let _ = app.state::<SpeechManager>().stop();
    let sessions = app.state::<SessionManager>();
    sessions.stop_all();
    app.exit(0);
}

/// Konuşma tanımayı başlat.
///
/// Yardımcı UYGULAMANIN ÇOCUĞU olarak çalıştırılır; bu şart. macOS izni çağıran
/// sürecin kimliğine bağlar: yardımcı terminalden çalıştırıldığında izin
/// penceresi HİÇ açılmaz ve `authorizationStatus()` sessizce `notDetermined`
/// kalır (ölçüldü). Uygulamadan doğrulduğunda `Info.plist` açıklamaları
/// devreye girer ve kullanıcı izni görür.
///
/// Yardımcının her satırı olduğu gibi `ses://tanima` olayıyla yayılır; ayrıştırma
/// arayüz tarafındadır.
fn speech_helper_resource_name(target_os: &str) -> &'static str {
    match target_os {
        "macos" => "fusion-listen",
        "windows" => "fusion-listen.exe",
        _ => unreachable!("Fusion masaüstü yalnız macOS ve Windows hedefler"),
    }
}

#[tauri::command]
fn tanima_baslat(
    app: tauri::AppHandle,
    manager: tauri::State<SpeechManager>,
) -> Result<u64, String> {
    let helper = app
        .path()
        .resolve(
            speech_helper_resource_name(std::env::consts::OS),
            tauri::path::BaseDirectory::Resource,
        )
        .map_err(|error| format!("tanıma yardımcısı bulunamadı: {error}"))?;
    if !helper.is_file() {
        return Err("Bu pakette konuşma tanıma yardımcısı yok.".into());
    }
    let mut command = std::process::Command::new(helper);
    command.arg("tr-TR");
    start_recognition(app, manager.inner(), &mut command)
}

#[tauri::command]
fn tanima_durdur(manager: tauri::State<SpeechManager>) -> Result<(), String> {
    manager.stop()
}

#[tauri::command]
fn tanima_durum(manager: tauri::State<SpeechManager>) -> bool {
    manager.is_running()
}

/// Konuşma kipini kapat: konuşma penceresini gizle, ana pencereyi geri getir.
#[tauri::command]
async fn ses_penceresi_kapat(
    app: tauri::AppHandle,
    manager: tauri::State<'_, SpeechManager>,
) -> Result<(), String> {
    let plan = voice_window_lifecycle_plan(VoiceWindowLifecycle::Close);
    if plan.stop_recognition {
        manager.stop()?;
    }
    if plan.close_voice {
        if let Some(ses) = app.get_webview_window(SES_PENCERESI) {
            ses.close().map_err(|error| error.to_string())?;
        }
    }
    if plan.restore_main {
        if let Some(ana) = app.get_webview_window("main") {
            ana.unminimize().map_err(|error| error.to_string())?;
            ana.show().map_err(|error| error.to_string())?;
            ana.set_focus().map_err(|error| error.to_string())?;
        }
    }
    Ok(())
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

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(SessionManager::new())
        .manage(SpeechManager::new())
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
            ses_penceresi_ac,
            ses_penceresi_simge_durumu,
            ses_penceresi_kapat,
            ses_penceresi_boyut,
            ses_penceresi_geometri_uygula,
            ses_penceresi_ustte,
            tanima_baslat,
            tanima_durdur,
            tanima_durum,
            kapatmayi_onayla,
            runtime_durum,
            runtime_hazirla,
            runtime_onar,
            izin_durumu,
            izin_iste,
            izin_ayarlari_ac
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                // Kapatma ONAYSIZ yapılmaz: çalışan tur ve açık sohbetler
                // kaybolur. Yanlışlıkla kapatmak (Cmd+Q, Alt+F4, kırmızı düğme)
                // iş kaybettiriyordu. Karar arayüzde sorulur; onaylanırsa
                // arayüz `kapatmayi_onayla` çağırır.
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.emit("uygulama://kapatma-istegi", ());
                    return;
                }
                if window.label() == SES_PENCERESI {
                    let manager = window.state::<SpeechManager>();
                    cleanup_for_window(window.label(), manager.inner());
                    return;
                }
                let sessions = window.state::<SessionManager>();
                sessions.stop_all();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");
    app.run(|app, event| {
        if matches!(
            event,
            tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
        ) {
            let _ = app.state::<SpeechManager>().stop();
        }
    });
}

#[cfg(test)]
mod voice_geometry_tests {
    use super::*;

    #[test]
    fn minimizing_the_voice_window_keeps_recognition_running() {
        let plan = voice_window_lifecycle_plan(VoiceWindowLifecycle::Minimize);

        assert!(plan.minimize_voice);
        assert!(!plan.close_voice);
        assert!(!plan.restore_main);
        assert!(!plan.stop_recognition);
    }

    #[test]
    fn closing_the_voice_window_stops_recognition_and_restores_main_window() {
        let plan = voice_window_lifecycle_plan(VoiceWindowLifecycle::Close);

        assert!(!plan.minimize_voice);
        assert!(plan.close_voice);
        assert!(plan.restore_main);
        assert!(plan.stop_recognition);
    }

    #[test]
    fn normal_mode_uses_the_required_default_and_resize_limits() {
        let plan = voice_geometry_plan(&VoiceWindowGeometry {
            x: None,
            y: None,
            normal_width: 380.0,
            normal_height: 460.0,
            wide: true,
            on_top: true,
        });

        assert_eq!(plan.size, (380.0, 460.0));
        assert_eq!(plan.min_size, Some((360.0, 420.0)));
        assert_eq!(plan.max_size, Some((520.0, 720.0)));
        assert!(plan.resizable);
    }

    #[test]
    fn mini_mode_is_fixed_at_the_required_size() {
        let plan = voice_geometry_plan(&VoiceWindowGeometry {
            x: None,
            y: None,
            normal_width: 500.0,
            normal_height: 700.0,
            wide: false,
            on_top: true,
        });

        assert_eq!(plan.size, (360.0, 112.0));
        assert_eq!(plan.min_size, None);
        assert_eq!(plan.max_size, None);
        assert!(!plan.resizable);
    }

    #[test]
    fn restored_normal_geometry_is_clamped_and_keeps_position_and_on_top() {
        let plan = voice_geometry_plan(&VoiceWindowGeometry {
            x: Some(120.0),
            y: Some(80.0),
            normal_width: 900.0,
            normal_height: 200.0,
            wide: true,
            on_top: false,
        });

        assert_eq!(plan.position, Some((120.0, 80.0)));
        assert_eq!(plan.size, (520.0, 420.0));
        assert_eq!(plan.on_top, Some(false));
    }

    #[test]
    fn size_only_mode_change_does_not_overwrite_on_top_preference() {
        let plan = voice_size_plan(false);

        assert_eq!(plan.size, (360.0, 112.0));
        assert_eq!(plan.on_top, None);
    }

    #[test]
    fn speech_helper_resource_name_matches_each_packaged_platform() {
        assert_eq!(speech_helper_resource_name("macos"), "fusion-listen");
        assert_eq!(speech_helper_resource_name("windows"), "fusion-listen.exe");
    }
}
