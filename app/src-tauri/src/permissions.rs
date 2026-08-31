use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PermissionKind {
    Workspace,
    Microphone,
    Speech,
    Keychain,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
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
        PermissionKind::Workspace | PermissionKind::Keychain => None,
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
    };
    PermissionCapability::supported(state)
}

#[cfg(not(target_os = "macos"))]
fn platform_status(kind: PermissionKind) -> PermissionCapability {
    match kind {
        PermissionKind::Workspace | PermissionKind::Keychain => {
            PermissionCapability::supported(PermissionState::Unknown)
        }
        PermissionKind::Microphone | PermissionKind::Speech => unsupported_capability(),
    }
}

#[cfg(target_os = "macos")]
fn platform_status(kind: PermissionKind) -> PermissionCapability {
    macos_status(kind)
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
            match receive.recv() {
                Ok(true) => PermissionCapability::supported(PermissionState::Granted),
                Ok(false) => PermissionCapability::supported(PermissionState::Denied),
                Err(_) => PermissionCapability::supported(PermissionState::Restricted),
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
            match receive.recv() {
                Ok(objc2_speech::SFSpeechRecognizerAuthorizationStatus::Authorized) => {
                    PermissionCapability::supported(PermissionState::Granted)
                }
                Ok(objc2_speech::SFSpeechRecognizerAuthorizationStatus::Denied) => {
                    PermissionCapability::supported(PermissionState::Denied)
                }
                Ok(_) | Err(_) => PermissionCapability::supported(PermissionState::Restricted),
            }
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
        match kind {
            PermissionKind::Workspace | PermissionKind::Keychain => {
                PermissionCapability::supported(PermissionState::Granted)
            }
            PermissionKind::Microphone | PermissionKind::Speech => unsupported_capability(),
        }
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

    #[test]
    fn unsupported_platform_has_no_settings_deep_link() {
        assert_eq!(settings_url(PermissionKind::Microphone, "linux"), None);
    }
}
