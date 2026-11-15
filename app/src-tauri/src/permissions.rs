use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PermissionKind {
    Workspace,
    Microphone,
    Speech,
    Keychain,
    /// macOS Erişilebilirlik (AX): masaüstünde tıklama/yazma/kaydırma (P-005).
    Accessibility,
    /// macOS Ekran Kaydı: masaüstü ekran görüntüsü (P-005).
    #[serde(rename = "screenRecording")]
    ScreenRecording,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
// Bu enum ARAYÜZLE paylaşılan bir protokol tipidir: dört durumun hepsi
// `serde` ile aynı biçimde serileşir ve ön yüz dördünü de bekler. `Denied` ve
// `Restricted` yalnız macOS izin API'lerinden üretilebiliyor; Windows derlemesinde
// hiçbir yerde kurulmadıkları için `-D warnings` altında `dead_code` hatası
// veriyorlardı. Ölçüldü (alpha.12 Windows işi): `error: variant `Denied` is never
// constructed` ile clippy düştü ve kurucu hiç üretilmedi.
//
// Bastırma yalnız macOS DIŞINDA açılır: macOS'ta varyantlar gerçekten
// ulaşılabilir olmalı ve orada lint'in çalışmaya devam etmesi istenir.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
pub enum PermissionState {
    Unknown,
    Granted,
    Denied,
    Restricted,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
pub struct PermissionCapability {
    state: PermissionState,
    supported: bool,
}

impl PermissionCapability {
    fn supported(state: PermissionState) -> Self {
        Self {
            state,
            supported: true,
        }
    }
}

#[cfg(any(test, not(target_os = "macos")))]
fn unsupported_capability() -> PermissionCapability {
    PermissionCapability {
        state: PermissionState::Restricted,
        supported: false,
    }
}

#[cfg(test)]
fn capability_status(
    kind: PermissionKind,
    probe: impl FnOnce(PermissionKind) -> PermissionState,
    _request: impl FnOnce(PermissionKind),
) -> PermissionCapability {
    PermissionCapability::supported(probe(kind))
}

fn settings_url(kind: PermissionKind, platform: &str) -> Option<&'static str> {
    if platform != "macos" {
        return None;
    }
    match kind {
        PermissionKind::Microphone => {
            Some("x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")
        }
        PermissionKind::Speech => Some(
            "x-apple.systempreferences:com.apple.preference.security?Privacy_SpeechRecognition",
        ),
        PermissionKind::Accessibility => {
            Some("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        }
        PermissionKind::ScreenRecording => {
            Some("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        }
        PermissionKind::Workspace | PermissionKind::Keychain => None,
    }
}

/// TCC (Erişilebilirlik, Ekran Kaydı) C API'leri; hiçbir ek crate gerektirmez.
/// `AXIsProcessTrustedWithOptions` istem seçeneği bir CFDictionary ister; CoreFoundation
/// doğrudan bağlanır. İstemler Fusion.app süreci adına açılır: masaüstü araçlarını koşturan
/// sidecar bu uygulamanın çocuğu olduğundan TCC aynı sorumlu süreci görür (elle doğrulanır).
#[cfg(target_os = "macos")]
mod tcc {
    use std::ffi::c_void;

    #[link(name = "ApplicationServices", kind = "framework")]
    extern "C" {
        fn AXIsProcessTrusted() -> bool;
        fn AXIsProcessTrustedWithOptions(options: *const c_void) -> bool;
        static kAXTrustedCheckOptionPrompt: *const c_void;
    }

    #[link(name = "CoreGraphics", kind = "framework")]
    extern "C" {
        fn CGPreflightScreenCaptureAccess() -> bool;
        fn CGRequestScreenCaptureAccess() -> bool;
    }

    #[link(name = "CoreFoundation", kind = "framework")]
    extern "C" {
        fn CFDictionaryCreate(
            allocator: *const c_void,
            keys: *const *const c_void,
            values: *const *const c_void,
            count: isize,
            key_callbacks: *const c_void,
            value_callbacks: *const c_void,
        ) -> *const c_void;
        fn CFRelease(value: *const c_void);
        static kCFBooleanTrue: *const c_void;
        static kCFTypeDictionaryKeyCallBacks: c_void;
        static kCFTypeDictionaryValueCallBacks: c_void;
    }

    pub fn accessibility_trusted() -> bool {
        // SAFETY: Argümansız, durum okuyan C çağrısı.
        unsafe { AXIsProcessTrusted() }
    }

    pub fn screen_capture_allowed() -> bool {
        // SAFETY: Argümansız, istem açmayan C çağrısı (10.15+).
        unsafe { CGPreflightScreenCaptureAccess() }
    }

    /// Sistem Erişilebilirlik istemini açar; dönüş o anki (istem öncesi) durumdur.
    pub fn prompt_accessibility() -> bool {
        // SAFETY: Sözlük tek anahtar/değerle kurulur, çağrıdan sonra serbest bırakılır;
        // anahtar ve değer CoreFoundation'ın sahip olduğu sabitlerdir.
        unsafe {
            let keys = [kAXTrustedCheckOptionPrompt];
            let values = [kCFBooleanTrue];
            let options = CFDictionaryCreate(
                std::ptr::null(),
                keys.as_ptr(),
                values.as_ptr(),
                1,
                &kCFTypeDictionaryKeyCallBacks as *const c_void,
                &kCFTypeDictionaryValueCallBacks as *const c_void,
            );
            if options.is_null() {
                return AXIsProcessTrusted();
            }
            let trusted = AXIsProcessTrustedWithOptions(options);
            CFRelease(options);
            trusted
        }
    }

    /// Ekran Kaydı istemini açar (bir kez); izin sonrası yeniden açılış gerekir.
    pub fn prompt_screen_capture() -> bool {
        // SAFETY: Argümansız C çağrısı.
        unsafe { CGRequestScreenCaptureAccess() }
    }
}

#[cfg(target_os = "macos")]
fn macos_status(kind: PermissionKind) -> PermissionCapability {
    use objc2_av_foundation::{AVAuthorizationStatus, AVCaptureDevice, AVMediaTypeAudio};
    use objc2_speech::{SFSpeechRecognizer, SFSpeechRecognizerAuthorizationStatus};

    let state = match kind {
        PermissionKind::Workspace | PermissionKind::Keychain => PermissionState::Unknown,
        PermissionKind::Microphone => {
            let media_type =
                unsafe { AVMediaTypeAudio }.expect("AVMediaTypeAudio is available on macOS");
            match unsafe { AVCaptureDevice::authorizationStatusForMediaType(media_type) } {
                AVAuthorizationStatus::NotDetermined => PermissionState::Unknown,
                AVAuthorizationStatus::Authorized => PermissionState::Granted,
                AVAuthorizationStatus::Denied => PermissionState::Denied,
                _ => PermissionState::Restricted,
            }
        }
        PermissionKind::Speech => match unsafe { SFSpeechRecognizer::authorizationStatus() } {
            SFSpeechRecognizerAuthorizationStatus::NotDetermined => PermissionState::Unknown,
            SFSpeechRecognizerAuthorizationStatus::Authorized => PermissionState::Granted,
            SFSpeechRecognizerAuthorizationStatus::Denied => PermissionState::Denied,
            _ => PermissionState::Restricted,
        },
        // TCC "sorulmadı" ile "reddedildi"yi ayırt etmez; ikisi de Denied'dır.
        PermissionKind::Accessibility => granted_or_denied(tcc::accessibility_trusted()),
        PermissionKind::ScreenRecording => granted_or_denied(tcc::screen_capture_allowed()),
    };
    PermissionCapability::supported(state)
}

#[cfg(target_os = "macos")]
fn granted_or_denied(allowed: bool) -> PermissionState {
    if allowed {
        PermissionState::Granted
    } else {
        PermissionState::Denied
    }
}

#[cfg(not(target_os = "macos"))]
fn platform_status(kind: PermissionKind) -> PermissionCapability {
    platform_status_for(kind, std::env::consts::OS)
}

#[cfg(any(test, not(target_os = "macos")))]
fn platform_status_for(kind: PermissionKind, platform: &str) -> PermissionCapability {
    match (platform, kind) {
        // #430: Windows'ta computer use için izin adımı yok; anahtar hemen etkindir.
        ("windows", PermissionKind::Accessibility | PermissionKind::ScreenRecording) => {
            PermissionCapability::supported(PermissionState::Granted)
        }
        ("windows", PermissionKind::Workspace | PermissionKind::Keychain) => {
            // supported bir TCC istemi var demek değil, özelliğin bu hedefte
            // mevcut olduğu demektir (folder picker / Credential Manager).
            PermissionCapability::supported(PermissionState::Unknown)
        }
        (_, PermissionKind::Workspace | PermissionKind::Keychain) if platform == "macos" => {
            PermissionCapability::supported(PermissionState::Unknown)
        }
        _ => unsupported_capability(),
    }
}

#[cfg(target_os = "macos")]
fn platform_status(kind: PermissionKind) -> PermissionCapability {
    macos_status(kind)
}

/// Sistem izin penceresine kullanıcının cevabı için bekleme üst sınırı. Tamamlama bloğu hiç
/// çağrılmazsa (pencere açılamadı, süreç askıda) `recv()` sonsuza dek bloklar ve
/// `spawn_blocking` iş parçacığı sızardı (R2-17).
#[cfg(any(test, target_os = "macos"))]
const IZIN_CEVAP_ZAMAN_ASIMI: std::time::Duration = std::time::Duration::from_secs(300);

/// Cevabı zaman aşımıyla bekler; gelmezse `None` (çağıran "bilinmiyor" döner, uydurmaz).
#[cfg(any(test, target_os = "macos"))]
fn await_decision<T>(
    receive: &std::sync::mpsc::Receiver<T>,
    timeout: std::time::Duration,
) -> Option<T> {
    receive.recv_timeout(timeout).ok()
}

#[cfg(target_os = "macos")]
async fn request_macos(kind: PermissionKind) -> PermissionCapability {
    use block2::RcBlock;
    use objc2_av_foundation::{AVCaptureDevice, AVMediaTypeAudio};
    use objc2_speech::SFSpeechRecognizer;
    use std::sync::mpsc;

    match kind {
        PermissionKind::Workspace | PermissionKind::Keychain => {
            PermissionCapability::supported(PermissionState::Granted)
        }
        PermissionKind::Microphone => tauri::async_runtime::spawn_blocking(move || {
            let (send, receive) = mpsc::sync_channel(1);
            let handler = RcBlock::new(move |granted: objc2::runtime::Bool| {
                let _ = send.send(bool::from(granted));
            });
            let media_type =
                unsafe { AVMediaTypeAudio }.expect("AVMediaTypeAudio is available on macOS");
            unsafe {
                AVCaptureDevice::requestAccessForMediaType_completionHandler(media_type, &handler)
            };
            match await_decision(&receive, IZIN_CEVAP_ZAMAN_ASIMI) {
                Some(true) => PermissionCapability::supported(PermissionState::Granted),
                Some(false) => PermissionCapability::supported(PermissionState::Denied),
                None => PermissionCapability::supported(PermissionState::Unknown),
            }
        })
        .await
        .unwrap_or_else(|_| PermissionCapability::supported(PermissionState::Restricted)),
        PermissionKind::Speech => tauri::async_runtime::spawn_blocking(move || {
            let (send, receive) = mpsc::sync_channel(1);
            let handler = RcBlock::new(move |status| {
                let _ = send.send(status);
            });
            unsafe { SFSpeechRecognizer::requestAuthorization(&handler) };
            match await_decision(&receive, IZIN_CEVAP_ZAMAN_ASIMI) {
                Some(objc2_speech::SFSpeechRecognizerAuthorizationStatus::Authorized) => {
                    PermissionCapability::supported(PermissionState::Granted)
                }
                Some(objc2_speech::SFSpeechRecognizerAuthorizationStatus::Denied) => {
                    PermissionCapability::supported(PermissionState::Denied)
                }
                Some(_) => PermissionCapability::supported(PermissionState::Restricted),
                None => PermissionCapability::supported(PermissionState::Unknown),
            }
        })
        .await
        .unwrap_or_else(|_| PermissionCapability::supported(PermissionState::Restricted)),
        // İstem çağrıları hemen döner (pencere sistem tarafından ayrı açılır); dönüş
        // istem ÖNCESİ durumdur, arayüz "Yeniden dene" ile yeniden sorar.
        PermissionKind::Accessibility => tauri::async_runtime::spawn_blocking(|| {
            PermissionCapability::supported(granted_or_denied(tcc::prompt_accessibility()))
        })
        .await
        .unwrap_or_else(|_| PermissionCapability::supported(PermissionState::Restricted)),
        PermissionKind::ScreenRecording => tauri::async_runtime::spawn_blocking(|| {
            PermissionCapability::supported(granted_or_denied(tcc::prompt_screen_capture()))
        })
        .await
        .unwrap_or_else(|_| PermissionCapability::supported(PermissionState::Restricted)),
    }
}

#[tauri::command]
pub fn izin_durumu(kind: PermissionKind) -> PermissionCapability {
    platform_status(kind)
}

#[tauri::command]
pub async fn izin_iste(kind: PermissionKind) -> PermissionCapability {
    #[cfg(target_os = "macos")]
    {
        request_macos(kind).await
    }
    #[cfg(not(target_os = "macos"))]
    {
        request_without_tcc(kind, std::env::consts::OS)
    }
}

/// TCC olmayan platformlarda izin isteği: istenecek sistem penceresi yoktur.
#[cfg(any(test, not(target_os = "macos")))]
fn request_without_tcc(kind: PermissionKind, platform: &str) -> PermissionCapability {
    match kind {
        PermissionKind::Workspace | PermissionKind::Keychain => {
            PermissionCapability::supported(PermissionState::Granted)
        }
        // #430: Windows computer use izinsiz çalışır (girdi ve ekran yakalama).
        PermissionKind::Accessibility | PermissionKind::ScreenRecording
            if platform == "windows" =>
        {
            PermissionCapability::supported(PermissionState::Granted)
        }
        PermissionKind::Microphone
        | PermissionKind::Speech
        | PermissionKind::Accessibility
        | PermissionKind::ScreenRecording => unsupported_capability(),
    }
}

#[tauri::command]
pub fn izin_ayarlari_ac(kind: PermissionKind) -> Result<(), String> {
    let url = settings_url(kind, std::env::consts::OS)
        .ok_or_else(|| "Bu izin için doğrudan bir sistem ayarı yok.".to_string())?;
    tauri_plugin_opener::open_url(url, None::<&str>).map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;

    #[test]
    fn status_query_uses_only_the_side_effect_free_probe() {
        let probes = Cell::new(0);
        let requests = Cell::new(0);

        let result = capability_status(
            PermissionKind::Microphone,
            |_| {
                probes.set(probes.get() + 1);
                PermissionState::Denied
            },
            |_| requests.set(requests.get() + 1),
        );

        assert_eq!(
            result,
            PermissionCapability::supported(PermissionState::Denied)
        );
        assert_eq!(probes.get(), 1);
        assert_eq!(requests.get(), 0);
    }

    /// Ölçüldü (30 Ekim): `receive.recv()` zaman aşımsızdı; tamamlama bloğu çağrılmazsa iş parçacığı sızıyordu.
    #[test]
    fn permission_wait_gives_up_instead_of_blocking_forever() {
        let (_send, receive) = std::sync::mpsc::sync_channel::<bool>(1);
        let started = std::time::Instant::now();
        assert_eq!(
            await_decision(&receive, std::time::Duration::from_millis(50)),
            None
        );
        assert!(started.elapsed() < std::time::Duration::from_secs(2));

        let (send, receive) = std::sync::mpsc::sync_channel::<bool>(1);
        send.send(true).unwrap();
        assert_eq!(
            await_decision(&receive, std::time::Duration::from_secs(1)),
            Some(true)
        );
    }

    #[test]
    fn unsupported_capability_is_explicit_and_never_granted() {
        assert_eq!(
            unsupported_capability(),
            PermissionCapability {
                state: PermissionState::Restricted,
                supported: false
            },
        );
    }

    #[test]
    fn macos_settings_urls_are_specific_and_never_full_disk_access() {
        assert_eq!(
            settings_url(PermissionKind::Microphone, "macos"),
            Some("x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")
        );
        assert_eq!(
            settings_url(PermissionKind::Speech, "macos"),
            Some(
                "x-apple.systempreferences:com.apple.preference.security?Privacy_SpeechRecognition"
            )
        );
        assert_eq!(settings_url(PermissionKind::Keychain, "macos"), None);
        assert_eq!(settings_url(PermissionKind::Workspace, "macos"), None);
    }

    /// Ölçüldü (31 Ekim): Erişilebilirlik ve Ekran Kaydı türleri yoktu; arayüz izin kartı açamıyordu.
    #[test]
    fn computer_use_permissions_link_to_their_privacy_panes() {
        assert_eq!(
            settings_url(PermissionKind::Accessibility, "macos"),
            Some("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        );
        assert_eq!(
            settings_url(PermissionKind::ScreenRecording, "macos"),
            Some("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        );
        let kind: PermissionKind = serde_json::from_str("\"screenRecording\"").unwrap();
        assert_eq!(kind, PermissionKind::ScreenRecording);
    }

    /// #430: Windows'ta computer use için izin adımı yoktur ("the toggle takes effect
    /// immediately"); Erişilebilirlik ve Ekran Kaydı verilmiş sayılır, Linux'ta desteklenmez.
    #[test]
    fn windows_computer_use_needs_no_permission_step() {
        for kind in [
            PermissionKind::Accessibility,
            PermissionKind::ScreenRecording,
        ] {
            assert_eq!(
                platform_status_for(kind, "windows"),
                PermissionCapability::supported(PermissionState::Granted)
            );
            assert_eq!(
                request_without_tcc(kind, "windows"),
                PermissionCapability::supported(PermissionState::Granted)
            );
            assert_eq!(platform_status_for(kind, "linux"), unsupported_capability());
            assert_eq!(request_without_tcc(kind, "linux"), unsupported_capability());
            assert_eq!(settings_url(kind, "windows"), None);
        }
    }

    #[test]
    fn unsupported_platform_has_no_settings_deep_link() {
        assert_eq!(settings_url(PermissionKind::Microphone, "linux"), None);
    }

    #[test]
    fn windows_workspace_and_credential_vault_are_supported_without_tcc() {
        assert_eq!(
            platform_status_for(PermissionKind::Workspace, "windows"),
            PermissionCapability::supported(PermissionState::Unknown)
        );
        assert_eq!(
            platform_status_for(PermissionKind::Keychain, "windows"),
            PermissionCapability::supported(PermissionState::Unknown)
        );
        assert_eq!(
            platform_status_for(PermissionKind::Microphone, "windows"),
            unsupported_capability()
        );
    }
}
