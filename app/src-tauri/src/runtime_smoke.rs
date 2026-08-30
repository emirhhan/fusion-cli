//! Paketlenmiş `.app` için başsız dağıtım duman testi.
//!
//! Yalnız açık `--runtime-smoke` argümanıyla çalışır. Tauri penceresi açılmadan
//! bundle kaynaklarını kurar, sağlık kapısından geçirir ve `app` stdio
//! protokolünün `oturum.durum` isteğine cevap verdiğini doğrular. Sağlayıcı/model
//! çağrısı yapmaz.

use std::ffi::OsStr;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Arc};
use std::time::{Duration, Instant};

use crate::runtime_installer::RuntimeResources;
use crate::runtime_manager::{CommandHealthProbe, RuntimeManager};
use crate::runtime_paths::RuntimePaths;

const SMOKE_TIMEOUT: Duration = Duration::from_secs(30);
const POLL_INTERVAL: Duration = Duration::from_millis(50);

pub fn requested<I, S>(args: I) -> bool
where
    I: IntoIterator<Item = S>,
    S: AsRef<OsStr>,
{
    args.into_iter()
        .any(|arg| arg.as_ref() == OsStr::new("--runtime-smoke"))
}

fn runtime_dir_for_executable(executable: &Path) -> Result<PathBuf, String> {
    let macos = executable
        .parent()
        .ok_or("Uygulama yürütülebilir dizini çözülemedi")?;
    let contents = macos
        .parent()
        .ok_or("Uygulama Contents dizini çözülemedi")?;
    Ok(contents.join("Resources/runtime"))
}

pub fn run_from_bundle() -> Result<(), String> {
    let executable = std::env::current_exe()
        .map_err(|error| format!("Uygulama yürütülebilir yolu çözülemedi: {error}"))?;
    let runtime_dir = runtime_dir_for_executable(&executable)?;
    let home = std::env::var_os("HOME")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .ok_or("Temiz kullanıcı HOME dizini verilmedi")?;
    let paths = RuntimePaths::for_home(&home);
    let manager = RuntimeManager::new(
        RuntimeResources {
            manifest_path: runtime_dir.join("runtime-manifest.json"),
            archive_path: runtime_dir.join("fusion-runtime.tar.gz"),
        },
        paths.clone(),
        crate::beklenen_hedef(),
        Arc::new(CommandHealthProbe),
    );
    let ready = manager.prepare(|_| {}).map_err(|error| error.to_string())?;
    smoke_core_protocol(&ready.executable)?;
    std::fs::write(paths.root.join("runtime-smoke-ok"), b"ok\n")
        .map_err(|error| format!("Smoke başarı kaydı yazılamadı: {error}"))
}

fn smoke_core_protocol(executable: &Path) -> Result<(), String> {
    let mut child = Command::new(executable)
        .arg("app")
        .env("FUSION_SECRET_KEY", "fusion-runtime-smoke-only")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("Smoke çekirdeği başlatılamadı: {error}"))?;

    let mut stdin = child
        .stdin
        .take()
        .ok_or("Smoke çekirdek girdisi alınamadı")?;
    let stdout = child
        .stdout
        .take()
        .ok_or("Smoke çekirdek çıktısı alınamadı")?;
    let (sender, receiver) = mpsc::channel();
    std::thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(stdout).read_line(&mut line).map(|_| line);
        let _ = sender.send(result);
    });

    let request = serde_json::json!({
        "tip": "istek",
        "id": "smoke-1",
        "ad": "oturum.durum",
        "veri": {},
    });
    writeln!(stdin, "{request}").map_err(|error| format!("Smoke isteği yazılamadı: {error}"))?;
    stdin
        .flush()
        .map_err(|error| format!("Smoke isteği gönderilemedi: {error}"))?;

    let line = receiver.recv_timeout(SMOKE_TIMEOUT).map_err(|_| {
        terminate(&mut child);
        "App protokolü 30 saniyede yanıt vermedi".to_string()
    })?;
    let line = line.map_err(|error| format!("Smoke yanıtı okunamadı: {error}"))?;
    let response: serde_json::Value =
        serde_json::from_str(&line).map_err(|error| format!("Smoke yanıtı JSON değil: {error}"))?;
    if response.get("tip").and_then(|value| value.as_str()) != Some("sonuc")
        || response.get("id").and_then(|value| value.as_str()) != Some("smoke-1")
    {
        terminate(&mut child);
        return Err("App protokolü beklenen oturum sonucunu döndürmedi".into());
    }

    drop(stdin);
    wait_success(&mut child)
}

fn wait_success(child: &mut Child) -> Result<(), String> {
    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => return Ok(()),
            Ok(Some(_)) => return Err("Smoke çekirdeği başarısız kapandı".into()),
            Ok(None) if started.elapsed() < SMOKE_TIMEOUT => std::thread::sleep(POLL_INTERVAL),
            Ok(None) => {
                terminate(child);
                return Err("Smoke çekirdeği 30 saniyede kapanmadı".into());
            }
            Err(error) => return Err(format!("Smoke çekirdeği beklenemedi: {error}")),
        }
    }
}

fn terminate(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    use std::os::unix::fs::PermissionsExt;

    #[test]
    fn smoke_modu_yalniz_acik_argumanla_etkinlesir() {
        assert!(requested(["fusion-desktop", "--runtime-smoke"]));
        assert!(!requested(["fusion-desktop"]));
        assert!(!requested(["fusion-desktop", "runtime-smoke"]));
    }

    #[test]
    fn app_bundle_runtime_dizinini_executable_yolundan_cozer() {
        let executable =
            std::path::Path::new("/Applications/Fusion.app/Contents/MacOS/fusion-desktop");
        assert_eq!(
            runtime_dir_for_executable(executable).unwrap(),
            std::path::PathBuf::from("/Applications/Fusion.app/Contents/Resources/runtime")
        );
    }

    #[cfg(unix)]
    #[test]
    fn cekirdek_protokolu_oturum_durumuyla_dogrulanir() {
        let temp = tempfile::tempdir().unwrap();
        let executable = temp.path().join("fusion");
        std::fs::write(
            &executable,
            "#!/bin/sh\nread request\nprintf '%s\\n' '{\"tip\":\"sonuc\",\"id\":\"smoke-1\",\"veri\":{}}'\n",
        )
        .unwrap();
        let mut permissions = std::fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o755);
        std::fs::set_permissions(&executable, permissions).unwrap();

        assert!(smoke_core_protocol(&executable).is_ok());
    }
}
