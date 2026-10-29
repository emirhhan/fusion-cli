use crate::core_process::{core_launch, stop_child, validate_runtime_executable};
use serde::Serialize;
use std::collections::HashMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex};
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

/// Oturum başına sıralı yazım kuyruğu. `send` satırı kanala koyup HEMEN döner;
/// tek bir yazıcı iş parçacığı satırları gelme sırasıyla çocuğun stdin'ine yazar.
/// Böylece dolu boruda bloklanan yazım ne global oturum kilidini ne de komut
/// iş parçacığını tutar (R2-02) ve çağrı sırası korunur. Gönderici düşürülünce
/// (`stop`, süreç kapanışı) yazıcı biter ve stdin kapanır (EOF).
type SessionStdin = mpsc::Sender<String>;

fn yazici_baslat(mut stdin: ChildStdin) -> SessionStdin {
    let (gonderici, alici) = mpsc::channel::<String>();
    std::thread::spawn(move || {
        // Yazım hatasında (kırık boru) çıkılır; alıcı düşünce sonraki `send`
        // "oturum çalışmıyor" döner.
        while let Ok(satir) = alici.recv() {
            if writeln!(stdin, "{satir}").is_err() || stdin.flush().is_err() {
                return;
            }
        }
    });
    gonderici
}

struct ManagedSession {
    snapshot: SessionSnapshot,
    child: Option<Child>,
    stdin: Option<SessionStdin>,
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
        let mut komut = Command::new(&launch.executable);
        crate::core_process::kendi_grubunda(&mut komut);
        let mut child = crate::core_process::pencere_acmadan(&mut komut)
            .args(&launch.args)
            .current_dir(&launch.current_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(cekirdek_gunlugu(session_id))
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
                stdin: Some(yazici_baslat(stdin)),
            },
        );
        drop(sessions);

        let sessions = Arc::clone(&self.sessions);
        let id = session_id.to_string();
        std::thread::spawn(move || {
            crate::core_process::satirlari_oku(output, |line| {
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
            });

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

    /// Satırı oturumun yazım kuyruğuna koyar; bloklamaz. Yazım sonucu (kırık
    /// boru) kuyruğa konduktan sonra oluşursa bir sonraki çağrıda "çalışmıyor" döner.
    pub(crate) fn send(&self, session_id: &str, line: String) -> Result<(), String> {
        let gonderici = {
            let sessions = self.sessions.lock().unwrap();
            let session = sessions.get(session_id).ok_or("oturum çalışmıyor")?;
            if session.snapshot.durum != "calisiyor" {
                return Err("oturum çalışmıyor".into());
            }
            session.stdin.clone().ok_or("oturum çalışmıyor")?
        };
        gonderici
            .send(line)
            .map_err(|_| "oturum çalışmıyor".to_string())
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

    #[cfg(test)]
    pub(crate) fn start_test_child(&self, session_id: &str) -> Result<u32, String> {
        let mut child = Command::new(
            std::env::current_exe().map_err(|error| format!("test ikilisi bulunamadı: {error}"))?,
        )
        .args([
            "--exact",
            "session_manager::testler::session_test_helper",
            "--ignored",
            "--nocapture",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("test session child başlatılamadı: {error}"))?;
        let stdin = child.stdin.take().ok_or("test session stdin alınamadı")?;
        let pid = child.id();
        self.sessions.lock().unwrap().insert(
            session_id.into(),
            ManagedSession {
                snapshot: SessionSnapshot::running(session_id, Path::new("/test"), pid),
                child: Some(child),
                stdin: Some(yazici_baslat(stdin)),
            },
        );
        Ok(pid)
    }

    /// Aldığı satırları `kayit` dosyasına sırayla yazan bir çocuk başlatır.
    #[cfg(test)]
    fn start_test_child_kayitli(&self, session_id: &str, kayit: &Path) -> Result<u32, String> {
        let mut child = Command::new(
            std::env::current_exe().map_err(|error| format!("test ikilisi bulunamadı: {error}"))?,
        )
        .args([
            "--exact",
            "session_manager::testler::session_test_helper_kayit",
            "--ignored",
            "--nocapture",
        ])
        .env("FUSION_TEST_KAYIT", kayit)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("test session child başlatılamadı: {error}"))?;
        let stdin = child.stdin.take().ok_or("test session stdin alınamadı")?;
        let pid = child.id();
        self.sessions.lock().unwrap().insert(
            session_id.into(),
            ManagedSession {
                snapshot: SessionSnapshot::running(session_id, Path::new("/test"), pid),
                child: Some(child),
                stdin: Some(yazici_baslat(stdin)),
            },
        );
        Ok(pid)
    }

    /// Stdin'ini hiç okumayan bir çocuk başlatır (yazım borusu dolunca bloklanır).
    #[cfg(test)]
    fn start_test_child_stdin_okumayan(&self, session_id: &str) -> Result<u32, String> {
        let mut child = Command::new(
            std::env::current_exe().map_err(|error| format!("test ikilisi bulunamadı: {error}"))?,
        )
        .args([
            "--exact",
            "session_manager::testler::session_test_helper_uyku",
            "--ignored",
            "--nocapture",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("test session child başlatılamadı: {error}"))?;
        let stdin = child.stdin.take().ok_or("test session stdin alınamadı")?;
        let pid = child.id();
        self.sessions.lock().unwrap().insert(
            session_id.into(),
            ManagedSession {
                snapshot: SessionSnapshot::running(session_id, Path::new("/test"), pid),
                child: Some(child),
                stdin: Some(yazici_baslat(stdin)),
            },
        );
        Ok(pid)
    }

    #[cfg(test)]
    pub(crate) fn test_is_running(&self, session_id: &str) -> bool {
        self.sessions
            .lock()
            .unwrap()
            .get_mut(session_id)
            .and_then(|session| session.child.as_mut())
            .is_some_and(|child| matches!(child.try_wait(), Ok(None)))
    }
}

/// Kök verilmediğinde kullanılacak dizin.
///
/// `std::env::current_dir()` KULLANILMAZ: Finder/LaunchServices ile açılan bir
/// uygulamada çalışma dizini `/` olur ve her sohbet dosya ağacında `/sbin`,
/// `/usr`, `/var` gösterirdi — kullanıcı bunu bildirdi. Ev dizini hem güvenli
/// hem anlamlı bir başlangıçtır; kullanıcı proje seçtiğinde zaten değişir.
/// Çekirdeğin hata çıktısının yazılacağı yer.
///
/// Ölçüldü (28 Eylül): Windows'ta uygulama "Çekirdek bağlantısı kapatıldı" dedi;
/// hata çıktısı `Stdio::null()` ile atıldığı için sebep hiçbir yerde yoktu. Çıktı
/// artık oturum başına bir dosyaya yazılır (her başlatmada baştan). Dosya
/// açılamazsa çekirdek yine başlar; günlük yokluğu açılışı engellemez.
fn cekirdek_gunlugu(session_id: &str) -> Stdio {
    let Some(dizin) = gunluk_dizini() else {
        return Stdio::null();
    };
    if std::fs::create_dir_all(&dizin).is_err() {
        return Stdio::null();
    }
    let ad: String = session_id
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' {
                c
            } else {
                '_'
            }
        })
        .take(64)
        .collect();
    match std::fs::File::create(dizin.join(format!("core-{ad}.log"))) {
        Ok(dosya) => Stdio::from(dosya),
        Err(_) => Stdio::null(),
    }
}

/// En son yazılan çekirdek günlüğünün sonu; arayüz bağlantı koptuğunda gösterir.
///
/// Sır sızmaması için çekirdek zaten hata çıktısına sır yazmaz (RULES.md "Sırlar");
/// burada yalnız son `sinir` bayt döner, tam dosya değil.
pub(crate) fn son_cekirdek_gunlugu(sinir: usize) -> Option<String> {
    let dizin = gunluk_dizini()?;
    let en_yeni = std::fs::read_dir(&dizin)
        .ok()?
        .filter_map(Result::ok)
        .filter(|giris| {
            let ad = giris.file_name();
            let ad = ad.to_string_lossy();
            ad.starts_with("core-") && ad.ends_with(".log")
        })
        .filter_map(|giris| Some((giris.metadata().ok()?.modified().ok()?, giris.path())))
        .max_by_key(|(zaman, _)| *zaman)?
        .1;
    let icerik = std::fs::read(&en_yeni).ok()?;
    let baslangic = icerik.len().saturating_sub(sinir);
    let metin = String::from_utf8_lossy(&icerik[baslangic..])
        .trim()
        .to_string();
    (!metin.is_empty()).then_some(metin)
}

/// `…/Fusion/logs`: çalışma zamanı kökünün (`…/Fusion/runtime`) kardeşi.
fn gunluk_dizini() -> Option<PathBuf> {
    let home = varsayilan_kok().ok()?;
    let runtime = crate::runtime_paths::RuntimePaths::for_home(&home).root;
    Some(runtime.parent()?.join("logs"))
}

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
    use std::io::Read;
    use std::path::{Path, PathBuf};

    #[test]
    #[ignore]
    fn session_test_helper() {
        let mut input = Vec::new();
        std::io::stdin().read_to_end(&mut input).unwrap();
    }

    /// Stdin satırlarını `FUSION_TEST_KAYIT` dosyasına, gelme sırasıyla yazar.
    #[test]
    #[ignore]
    fn session_test_helper_kayit() {
        use std::io::{BufRead, Write};
        let Some(yol) = std::env::var_os("FUSION_TEST_KAYIT") else {
            return;
        };
        let mut dosya = std::fs::File::create(yol).unwrap();
        for satir in std::io::stdin().lock().lines().map_while(Result::ok) {
            writeln!(dosya, "{satir}").unwrap();
            dosya.flush().unwrap();
        }
    }

    #[test]
    #[ignore]
    fn session_test_helper_uyku() {
        std::thread::sleep(std::time::Duration::from_secs(20));
    }

    /// Ölçüldü (30 Ekim): `send` global oturum kilidini tutarken yazıyordu; stdin'i
    /// okumayan çocuğa büyük yazım dolu boruda bloklanınca `list`/`stop` (ve onlara
    /// bağlı tüm Tauri komutları) yazım bitene kadar donuyordu (R2-02). Sıralı
    /// yazım kuyruğuyla `send` kuyruğa koyup anında döner.
    #[test]
    fn bloklanan_yazim_send_list_ve_stopu_dondurmaz() {
        use std::time::{Duration, Instant};
        let manager = SessionManager::new();
        manager.start_test_child_stdin_okumayan("tikali").unwrap();

        let baslangic = Instant::now();
        manager
            .send("tikali", "x".repeat(4 * 1024 * 1024))
            .expect("send kuyruğa koymalı");
        manager.send("tikali", "ikinci".into()).unwrap();
        let send_suresi = baslangic.elapsed();
        std::thread::sleep(Duration::from_millis(300));

        let (bitti, bekle) = std::sync::mpsc::channel();
        let kopya = manager.clone();
        std::thread::spawn(move || {
            let baslangic = Instant::now();
            let liste = kopya.list();
            let list_suresi = baslangic.elapsed();
            let _ = kopya.stop("tikali");
            let _ = bitti.send((liste.len(), list_suresi, baslangic.elapsed()));
        });

        let (adet, list_suresi, toplam) = bekle
            .recv_timeout(Duration::from_secs(8))
            .expect("list/stop yazım yüzünden bloklandı");
        assert_eq!(adet, 1);
        assert!(send_suresi < Duration::from_secs(1), "{send_suresi:?}");
        assert!(list_suresi < Duration::from_secs(1), "{list_suresi:?}");
        assert!(toplam < Duration::from_secs(6), "{toplam:?}");
    }

    /// Aynı oturuma art arda gönderilen satırlar çocuğa gönderim sırasıyla ulaşır.
    #[test]
    fn art_arda_gonderilen_satirlar_sirasini_korur() {
        use std::time::{Duration, Instant};
        const ADET: usize = 200;
        let dizin = tempfile::tempdir().unwrap();
        let kayit = dizin.path().join("alinan.txt");
        let manager = SessionManager::new();
        manager.start_test_child_kayitli("sirali", &kayit).unwrap();

        for i in 0..ADET {
            manager.send("sirali", format!("satir-{i}")).unwrap();
        }
        let son = Instant::now() + Duration::from_secs(10);
        let beklenen: Vec<String> = (0..ADET).map(|i| format!("satir-{i}")).collect();
        let mut alinan = Vec::new();
        while Instant::now() < son {
            alinan = std::fs::read_to_string(&kayit)
                .unwrap_or_default()
                .lines()
                .map(str::to_string)
                .collect();
            if alinan.len() >= ADET {
                break;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        manager.stop("sirali").unwrap();

        assert_eq!(alinan, beklenen);
    }

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
