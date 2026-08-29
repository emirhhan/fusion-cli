use crate::core_process::{core_launch, stop_child, validate_runtime_executable};
use serde::Serialize;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter};

pub(crate) const VARSAYILAN_OTURUM: &str = "varsayilan";

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub(crate) struct SessionSnapshot {
    pub(crate) oturum_id: String,
    pub(crate) kok: String,
    pub(crate) pid: u32,
    pub(crate) durum: String,
    pub(crate) kapanis_nedeni: Option<String>,
}

impl SessionSnapshot {
    fn running(id: &str, root: &Path, pid: u32) -> Self {
        Self {
            oturum_id: id.to_string(),
            kok: root.to_string_lossy().into_owned(),
            pid,
            durum: "calisiyor".into(),
            kapanis_nedeni: None,
        }
    }

    fn mark_closed(&mut self, reason: &str) {
        if self.durum == "calisiyor" {
            self.durum = "kapandi".into();
            self.kapanis_nedeni = Some(reason.into());
        }
    }
}

fn can_reuse(snapshot: &SessionSnapshot, child_running: bool) -> bool {
    snapshot.durum == "calisiyor" && child_running
}

fn is_current_process(snapshot: &SessionSnapshot, pid: u32) -> bool {
    snapshot.pid == pid
}

#[derive(Debug, Clone, Serialize)]
struct SessionLine {
    oturum_id: String,
    satir: String,
}

#[derive(Debug, Clone, Serialize)]
struct SessionClosed {
    oturum_id: String,
    neden: String,
}

#[derive(Debug, PartialEq, Eq)]
struct SessionLaunch {
    executable: PathBuf,
    args: Vec<String>,
    current_dir: PathBuf,
}

fn session_launch(executable: &Path, root: &Path) -> SessionLaunch {
    let core = core_launch(executable);
    SessionLaunch {
        executable: core.executable,
        args: core.args,
        current_dir: root.to_path_buf(),
    }
}

struct ManagedSession {
    snapshot: SessionSnapshot,
    child: Option<Child>,
    stdin: Option<ChildStdin>,
}

type SessionMap = Arc<Mutex<HashMap<String, ManagedSession>>>;

#[derive(Clone, Default)]
pub(crate) struct SessionManager {
    sessions: SessionMap,
}

impl SessionManager {
    pub(crate) fn new() -> Self {
        Self::default()
    }

    pub(crate) fn start(
        &self,
        app: AppHandle,
        executable: &Path,
        session_id: &str,
        root: Option<&Path>,
    ) -> Result<SessionSnapshot, String> {
        let session_id = session_id.trim();
        if session_id.is_empty() {
            return Err("oturum kimliği boş olamaz".into());
        }

        let root = match root {
            Some(path) => path.to_path_buf(),
            None => varsayilan_kok()?,
        };
        if !root.is_dir() {
            return Err(format!("çalışma dizini bulunamadı: {}", root.display()));
        }
        validate_runtime_executable(executable)?;

        let mut sessions = self.sessions.lock().unwrap();
        if let Some(existing) = sessions.get_mut(session_id) {
            let child_running = existing
                .child
                .as_mut()
                .is_some_and(|child| matches!(child.try_wait(), Ok(None)));
            if can_reuse(&existing.snapshot, child_running) {
                return Ok(existing.snapshot.clone());
            }
            if child_running {
                if let Some(child) = existing.child.as_mut() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
            sessions.remove(session_id);
        }

        let launch = session_launch(executable, &root);
        let mut child = Command::new(&launch.executable)
            .args(&launch.args)
            .current_dir(&launch.current_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("Fusion çalışma zamanı başlatılamadı: {error}"))?;
        let output = child.stdout.take().ok_or("çekirdek çıktısı alınamadı")?;
        let stdin = child.stdin.take().ok_or("çekirdek girdisi alınamadı")?;
        let pid = child.id();
        let snapshot = SessionSnapshot::running(session_id, &root, pid);
        sessions.insert(
            session_id.into(),
            ManagedSession {
                snapshot: snapshot.clone(),
                child: Some(child),
                stdin: Some(stdin),
            },
        );
        drop(sessions);

        let sessions = Arc::clone(&self.sessions);
        let id = session_id.to_string();
        std::thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                let Ok(line) = line else { break };
                let _ = app.emit(
                    "oturum-satir",
                    SessionLine {
                        oturum_id: id.clone(),
                        satir: line.clone(),
                    },
                );
                if id == VARSAYILAN_OTURUM {
                    let _ = app.emit("cekirdek-satir", line);
                }
            }

            let is_current = {
                let mut sessions = sessions.lock().unwrap();
                sessions.get_mut(&id).is_some_and(|session| {
                    if !is_current_process(&session.snapshot, pid) {
                        return false;
                    }
                    session.stdin = None;
                    session.snapshot.mark_closed("süreç kapandı");
                    true
                })
            };
            if !is_current {
                return;
            }
            let _ = app.emit(
                "oturum-kapandi",
                SessionClosed {
                    oturum_id: id.clone(),
                    neden: "süreç kapandı".into(),
                },
            );
            if id == VARSAYILAN_OTURUM {
                let _ = app.emit("cekirdek-kapandi", ());
            }
        });

        Ok(snapshot)
    }

    pub(crate) fn send(&self, session_id: &str, line: String) -> Result<(), String> {
        let mut sessions = self.sessions.lock().unwrap();
        let session = sessions.get_mut(session_id).ok_or("oturum çalışmıyor")?;
        let input = session.stdin.as_mut().ok_or("oturum çalışmıyor")?;
        writeln!(input, "{line}").map_err(|error| format!("yazılamadı: {error}"))?;
        input
            .flush()
            .map_err(|error| format!("boşaltılamadı: {error}"))
    }

    pub(crate) fn list(&self) -> Vec<SessionSnapshot> {
        let mut sessions = self.sessions.lock().unwrap();
        for session in sessions.values_mut() {
            let exited = session
                .child
                .as_mut()
                .is_some_and(|child| matches!(child.try_wait(), Ok(Some(_))));
            if exited {
                session.stdin = None;
                session.snapshot.mark_closed("süreç kapandı");
            }
        }
        let mut snapshots: Vec<_> = sessions.values().map(|s| s.snapshot.clone()).collect();
        snapshots.sort_by(|left, right| left.oturum_id.cmp(&right.oturum_id));
        snapshots
    }

    pub(crate) fn stop(&self, session_id: &str) -> Result<(), String> {
        let child = {
            let mut sessions = self.sessions.lock().unwrap();
            let session = sessions.get_mut(session_id).ok_or("oturum bulunamadı")?;
            session.stdin = None;
            session.snapshot.mark_closed("kullanıcı kapattı");
            session.child.take()
        };
        if let Some(child) = child {
            stop_child(child);
        }
        Ok(())
    }

    pub(crate) fn stop_all(&self) {
        let ids: Vec<_> = self.sessions.lock().unwrap().keys().cloned().collect();
        for id in ids {
            let _ = self.stop(&id);
        }
    }
}

/// Kök verilmediğinde kullanılacak dizin.
///
/// `std::env::current_dir()` KULLANILMAZ: Finder/LaunchServices ile açılan bir
/// uygulamada çalışma dizini `/` olur ve her sohbet dosya ağacında `/sbin`,
/// `/usr`, `/var` gösterirdi — kullanıcı bunu bildirdi. Ev dizini hem güvenli
/// hem anlamlı bir başlangıçtır; kullanıcı proje seçtiğinde zaten değişir.
fn varsayilan_kok() -> Result<PathBuf, String> {
    let home = std::env::var_os("HOME")
        .or_else(|| std::env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .ok_or_else(|| "ev dizini belirlenemedi".to_string())?;
    if home.as_os_str().is_empty() || home == Path::new("/") {
        return Err("ev dizini geçersiz".into());
    }
    Ok(home)
}

#[cfg(test)]
#[derive(Default)]
struct SessionRegistry {
    sessions: HashMap<String, SessionSnapshot>,
}

#[cfg(test)]
impl SessionRegistry {
    fn insert_if_absent(&mut self, snapshot: SessionSnapshot) -> bool {
        if self.sessions.contains_key(&snapshot.oturum_id) {
            return false;
        }
        self.sessions.insert(snapshot.oturum_id.clone(), snapshot);
        true
    }

    fn mark_closed(&mut self, id: &str, reason: &str) {
        if let Some(snapshot) = self.sessions.get_mut(id) {
            snapshot.mark_closed(reason);
        }
    }

    fn get(&self, id: &str) -> Option<&SessionSnapshot> {
        self.sessions.get(id)
    }

    fn list(&self) -> Vec<SessionSnapshot> {
        let mut snapshots: Vec<_> = self.sessions.values().cloned().collect();
        snapshots.sort_by(|left, right| left.oturum_id.cmp(&right.oturum_id));
        snapshots
    }
}

#[cfg(test)]
mod testler {
    use super::*;
    use std::path::{Path, PathBuf};

    #[test]
    fn oturum_komutu_koku_calisma_dizini_olarak_kullanir() {
        let launch = session_launch(
            Path::new("/paket/runtime/fusion"),
            Path::new("/projeler/oyun"),
        );

        assert_eq!(launch.executable, PathBuf::from("/paket/runtime/fusion"));
        assert_eq!(launch.args, vec!["app"]);
        assert_eq!(launch.current_dir, PathBuf::from("/projeler/oyun"));
    }

    #[test]
    fn oturum_anlik_goruntusu_arayuz_sozlesmesine_uyar() {
        let snapshot = SessionSnapshot::running("oyun", Path::new("/projeler/oyun"), 42);
        let value = serde_json::to_value(snapshot).unwrap();

        assert_eq!(value["oturum_id"], "oyun");
        assert_eq!(value["kok"], "/projeler/oyun");
        assert_eq!(value["pid"], 42);
        assert_eq!(value["durum"], "calisiyor");
    }

    #[test]
    fn kayit_defteri_ayni_oturumu_iki_kez_acmaz() {
        let mut registry = SessionRegistry::default();
        let first = SessionSnapshot::running("oyun", Path::new("/projeler/oyun"), 42);
        let second = SessionSnapshot::running("oyun", Path::new("/projeler/baska"), 99);

        assert!(registry.insert_if_absent(first.clone()));
        assert!(!registry.insert_if_absent(second));
        assert_eq!(registry.list(), vec![first]);
    }

    /// Finder'dan açılan uygulamada çalışma dizini `/` olur; oraya düşmek
    /// her sohbette dosya ağacında `/sbin`, `/usr`, `/var` göstermek demekti.
    #[test]
    fn kok_verilmediginde_kok_dizine_dusulmez() {
        let kok = varsayilan_kok().expect("ev dizini bulunmalı");
        assert_ne!(kok, PathBuf::from("/"));
        assert!(kok.is_dir(), "varsayılan kök gerçek bir dizin olmalı");
    }

    #[test]
    fn bir_oturumu_kapatmak_digerini_etkilemez() {
        let mut registry = SessionRegistry::default();
        registry.insert_if_absent(SessionSnapshot::running(
            "oyun",
            Path::new("/projeler/oyun"),
            42,
        ));
        registry.insert_if_absent(SessionSnapshot::running(
            "site",
            Path::new("/projeler/site"),
            43,
        ));

        registry.mark_closed("oyun", "kullanici");

        assert_eq!(registry.get("oyun").unwrap().durum, "kapandi");
        assert_eq!(registry.get("site").unwrap().durum, "calisiyor");
    }

    #[test]
    fn stdoutu_kapanmis_oturum_surec_henuz_cikmadi_diye_yeniden_kullanilmaz() {
        let mut snapshot = SessionSnapshot::running("oyun", Path::new("/projeler/oyun"), 42);
        snapshot.mark_closed("süreç kapandı");

        assert!(!can_reuse(&snapshot, true));
        assert!(!can_reuse(&snapshot, false));
    }

    #[test]
    fn eski_okuyucu_yeni_ayni_kimlikli_sureci_kapatamaz() {
        let snapshot = SessionSnapshot::running("oyun", Path::new("/projeler/oyun"), 99);

        assert!(!is_current_process(&snapshot, 42));
        assert!(is_current_process(&snapshot, 99));
    }
}
