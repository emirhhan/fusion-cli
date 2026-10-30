use crate::core_process::{core_launch, stop_child, validate_runtime_executable};
use serde::Serialize;
use std::collections::HashMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Arc, Mutex, MutexGuard, PoisonError};
use tauri::{AppHandle, Emitter, Manager};

/// Kilidi zehirlenmeye (başka iş parçacığı kilit tutarken panik) rağmen alır. Eskiden
/// `lock().unwrap()` tek bir panikten sonra TÜM oturum komutlarını zincirleme panikletiyordu
/// (Q1-22, R2-25). Harita her işlemde tutarlı bırakıldığından veri kullanılabilirdir.
fn lock_tolerant<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(PoisonError::into_inner)
}

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

/// Okuyucu iş parçacığı çıktı bitince çağırır: oturum hâlâ bu süreçse kapalı işaretler ve
/// kapanış NEDENİNİ döner. `stop` kullanıcı kapatmasını önce işaretlediyse o neden korunur;
/// eskiden hep "süreç kapandı" yayılıp bilerek kapatma ile çökme ayırt edilemiyordu (R2-18).
fn close_if_current(sessions: &SessionMap, id: &str, pid: u32) -> Option<String> {
    let mut sessions = lock_tolerant(sessions);
    let session = sessions.get_mut(id)?;
    if !is_current_process(&session.snapshot, pid) {
        return None;
    }
    session.stdin = None;
    session.snapshot.mark_closed("süreç kapandı");
    Some(
        session
            .snapshot
            .kapanis_nedeni
            .clone()
            .unwrap_or_else(|| "süreç kapandı".into()),
    )
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
        varlik_kapsamina_ekle(&app, &root);

        let mut sessions = lock_tolerant(&self.sessions);
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

            let Some(neden) = close_if_current(&sessions, &id, pid) else {
                return;
            };
            let _ = app.emit(
                "oturum-kapandi",
                SessionClosed {
                    oturum_id: id.clone(),
                    neden,
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
            let sessions = lock_tolerant(&self.sessions);
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
        let mut sessions = lock_tolerant(&self.sessions);
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
            let mut sessions = lock_tolerant(&self.sessions);
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
        let ids: Vec<_> = lock_tolerant(&self.sessions).keys().cloned().collect();
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
        lock_tolerant(&self.sessions).insert(
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
        lock_tolerant(&self.sessions).insert(
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
        lock_tolerant(&self.sessions).insert(
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
    match std::fs::File::create(dizin.join(gunluk_dosya_adi(session_id))) {
        Ok(dosya) => Stdio::from(dosya),
        Err(_) => Stdio::null(),
    }
}

/// Oturum kimliğinden günlük dosya adı. Temizleme `a/b` ve `a_b` gibi farklı kimlikleri aynı
/// ada düşürüp birbirinin günlüğünü eziyordu (R2-19): ad değiştiyse kimliğin özeti eklenir.
/// Değişmeyen kimlikler (`varsayilan` gibi) eski adı korur.
fn gunluk_dosya_adi(session_id: &str) -> String {
    use std::hash::{Hash, Hasher};
    let temiz: String = session_id
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
    if temiz == session_id {
        return format!("core-{temiz}.log");
    }
    let mut ozet = std::collections::hash_map::DefaultHasher::new();
    session_id.hash(&mut ozet);
    format!("core-{temiz}-{:08x}.log", ozet.finish() as u32)
}

/// En son yazılan çekirdek günlüğünün sonu; arayüz bağlantı koptuğunda gösterir.
///
/// Sır sızmaması için çekirdek zaten hata çıktısına sır yazmaz (RULES.md "Sırlar");
/// burada yalnız son `sinir` bayt döner, tam dosya değil.
pub(crate) fn son_cekirdek_gunlugu(sinir: usize, oturum_id: Option<&str>) -> Option<String> {
    let dizin = gunluk_dizini()?;
    // Hata ekranı bir oturuma aittir (varsayılan: ana çekirdek); başka oturumun günlüğü
    // yanlış ekranda çıkmasın diye önce o oturumun dosyası, yoksa en yenisi okunur (R2-19).
    let istenen = dizin.join(gunluk_dosya_adi(oturum_id.unwrap_or(VARSAYILAN_OTURUM)));
    let en_yeni = if istenen.is_file() {
        istenen
    } else {
        std::fs::read_dir(&dizin)
            .ok()?
            .filter_map(Result::ok)
            .filter(|giris| {
                let ad = giris.file_name();
                let ad = ad.to_string_lossy();
                ad.starts_with("core-") && ad.ends_with(".log")
            })
            .filter_map(|giris| Some((giris.metadata().ok()?.modified().ok()?, giris.path())))
            .max_by_key(|(zaman, _)| *zaman)?
            .1
    };
    let icerik = std::fs::read(&en_yeni).ok()?;
    let baslangic = icerik.len().saturating_sub(sinir);
    let metin = String::from_utf8_lossy(&icerik[baslangic..])
        .trim()
        .to_string();
    (!metin.is_empty()).then_some(metin)
}

/// `…/Fusion/logs`: çalışma zamanı kökünün (`…/Fusion/runtime`) kardeşi.
pub(crate) fn gunluk_dizini() -> Option<PathBuf> {
    let home = varsayilan_kok().ok()?;
    let runtime = crate::runtime_paths::RuntimePaths::for_current_user(&home).root;
    Some(runtime.parent()?.join("logs"))
}

/// Oturumun çalışma kökünü `asset://` kapsamına eklenecek kök olarak verir (Q1-08).
///
/// Ölçüldü (30 Ekim): kapsam `$HOME/**` idi; yasak listesinde olmayan her yerel görsel
/// arayüzde açılabiliyordu. Statik kapsam artık yalnız Fusion'ın ürettiği klasörleri içerir;
/// proje görselleri, oturumun çalışma kökü açılınca bu fonksiyonla eklenir. Ev dizininin
/// kendisi (proje seçilmemiş oturum) ve dosya sistemi kökü EKLENMEZ: yoksa tüm kısıtlama
/// geri gevşerdi.
fn varlik_kapsami_koku(root: &Path, home: Option<&Path>) -> Option<PathBuf> {
    if root.parent().is_none() || home.is_some_and(|ev| ev == root) {
        return None;
    }
    Some(root.to_path_buf())
}

fn varlik_kapsamina_ekle(app: &AppHandle, root: &Path) {
    let home = varsayilan_kok().ok();
    let Some(kok) = varlik_kapsami_koku(root, home.as_deref()) else {
        return;
    };
    // Eklenemezse oturum yine açılır; yalnız o projenin görselleri önizlenemez.
    let _ = app.asset_protocol_scope().allow_directory(&kok, true);
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
    fn varlik_kapsami_proje_kokunu_ekler_ev_dizinini_eklemez() {
        let ev = Path::new("/Users/ornek");
        assert_eq!(
            varlik_kapsami_koku(Path::new("/Users/ornek/proje"), Some(ev)),
            Some(PathBuf::from("/Users/ornek/proje"))
        );
        // Harici disk gibi ev dizini dışındaki projeler de eklenir.
        assert_eq!(
            varlik_kapsami_koku(Path::new("/Volumes/Disk/proje"), Some(ev)),
            Some(PathBuf::from("/Volumes/Disk/proje"))
        );
        assert_eq!(varlik_kapsami_koku(ev, Some(ev)), None);
        assert_eq!(varlik_kapsami_koku(Path::new("/"), Some(ev)), None);
        assert_eq!(
            varlik_kapsami_koku(Path::new("/tmp/p"), None),
            Some(PathBuf::from("/tmp/p"))
        );
    }

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

    /// Ölçüldü (30 Ekim): kullanıcı kapatınca da okuyucu "süreç kapandı" yayıyordu; arayüz
    /// bilerek kapatılanla çöken oturumu ayıramıyordu (R2-18).
    #[test]
    fn kullanici_kapatmasi_kapanis_nedenini_korur() {
        let manager = SessionManager::new();
        let pid = manager.start_test_child("neden").unwrap();
        manager.stop("neden").unwrap();
        assert_eq!(
            close_if_current(&manager.sessions, "neden", pid).as_deref(),
            Some("kullanıcı kapattı")
        );
        // Başka süreç kimliği (yeniden başlatılmış oturum) bu okuyucuya ait değildir.
        assert_eq!(close_if_current(&manager.sessions, "neden", pid + 1), None);
    }

    #[test]
    fn beklenmedik_cikis_surec_kapandi_nedeniyle_isaretlenir() {
        let manager = SessionManager::new();
        let pid = manager.start_test_child("cokme").unwrap();
        assert_eq!(
            close_if_current(&manager.sessions, "cokme", pid).as_deref(),
            Some("süreç kapandı")
        );
        manager.stop("cokme").unwrap();
    }

    /// Ölçüldü (30 Ekim): `a/b` ve `a_b` aynı `core-a_b.log` dosyasına düşüp birbirini eziyordu (R2-19).
    /// Ölçüldü (30 Ekim): kilit zehirlenince list/send/stop `unwrap` ile paniğe düşüyordu.
    #[test]
    fn zehirlenmis_kilit_oturum_yonetimini_dusurmez() {
        let manager = SessionManager::new();
        let sessions = Arc::clone(&manager.sessions);
        let _ = std::thread::spawn(move || {
            let _guard = sessions.lock().unwrap();
            panic!("kilit tutarken panik");
        })
        .join();
        assert!(manager.sessions.is_poisoned());
        assert!(manager.list().is_empty());
        assert!(manager.stop("yok").is_err());
    }

    #[test]
    fn farkli_oturum_kimlikleri_ayni_gunluk_dosyasina_dusmez() {
        assert_ne!(gunluk_dosya_adi("a/b"), gunluk_dosya_adi("a_b"));
        assert_eq!(gunluk_dosya_adi("varsayilan"), "core-varsayilan.log");
        assert_eq!(gunluk_dosya_adi("a/b"), gunluk_dosya_adi("a/b"));
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
