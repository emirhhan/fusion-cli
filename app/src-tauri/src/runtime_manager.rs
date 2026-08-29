//! Çalışma zamanının sağlığını denetler, etkin sürümü tutar, onarır ve
//! gerektiğinde bilinen sağlıklı bir önceki sürüme geri döner.
//!
//! Kullanıcıda Apple Developer imzası yok; uygulama imzasız dağıtılıyor.
//! Kurulum bozulursa kullanıcı komut satırına inip elle onarım yapamaz —
//! bu modül bozulmayı KENDİSİ görmeli, mümkünse onarmalı, olmuyorsa
//! `active-runtime.json` içindeki bilinen çalışan sürüme dönmelidir.
//! `active-runtime.json` gerçeğin tek kaynağıdır; ona yazım her zaman geçici
//! dosya + `rename` ile atomik yapılır, yoksa yarım yazılmış bir kayıt
//! uygulamayı tümden açılmaz hale getirir.
//!
//! `RuntimeManager::prepare`/`repair`, A/7'de eklenen `runtime_hazirla`/
//! `runtime_onar` Tauri komutları üzerinden üretimde çağrılır; `status`
//! ise `runtime_durum` komutunun temelidir. Bu yüzden dosya kapsamlı
//! `allow(dead_code)` artık YOK — her genel öğenin gerçek bir üretim
//! çağıranı var.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

use crate::runtime_installer::{install, RuntimeProgress, RuntimeResources};
use crate::runtime_manifest::{safe_relative, RuntimeError, RuntimeManifest};
use crate::runtime_paths::RuntimePaths;

/// Sağlık denetiminin 30 saniyede tamamlanmasını bekleriz; bundan uzun
/// süren bir çocuk süreç muhtemelen askıda kalmıştır ve öldürülüp
/// bilinen sağlıklı bir sürüme geri dönülmelidir.
const SAGLIK_ZAMAN_ASIMI: Duration = Duration::from_secs(30);
/// `try_wait` yoklama aralığı; çok sık yoklamak CPU'yu gereksiz meşgul
/// eder, çok seyrek yoklamak zaman aşımını gecikmeli fark ettirir.
const YOKLAMA_ARALIGI: Duration = Duration::from_millis(50);
/// Tanılama günlüğüne yazılacak ham stderr üst sınırı; kullanıcıya asla
/// gösterilmez, yalnızca uygulama tanılamasına gider.
const STDERR_GUNLUK_SINIRI: usize = 8 * 1024;
/// Tanılama günlüğüne yazmadan önce maskelenecek anahtar kelimeler
/// (küçük harfe çevrilmiş metinde aranır).
const HASSAS_ANAHTAR_KELIMELER: [&str; 6] = [
    "token",
    "secret",
    "password",
    "sifre",
    "key",
    "authorization",
];

/// Hazır (kurulmuş ve sağlık denetiminden geçmiş) bir çalışma zamanı.
#[derive(Debug, Clone)]
pub struct RuntimeReady {
    pub version: String,
    pub executable: PathBuf,
    pub source: RuntimeSource,
}

/// Çalışma zamanının nereden geldiği: paketlenmiş sürüm mü, yoksa
/// geliştirici makinesindeki yerel bir kurulum mu.
#[derive(Debug, Clone, PartialEq)]
pub enum RuntimeSource {
    Bundled,
    #[expect(
        dead_code,
        reason = "açık geliştirici runtime seçimi ayarlar ekranı bağlandığında üretilecek"
    )]
    Developer,
}

/// `fusion runtime-health --json` çıktısının Rust tarafındaki karşılığı.
#[derive(Debug, Clone, Deserialize)]
pub struct RuntimeHealthReport {
    pub ok: bool,
    pub version: String,
    pub python: String,
    pub platform: String,
    pub resources_ok: bool,
}

impl RuntimeHealthReport {
    fn is_healthy(&self) -> bool {
        self.ok
            && self.resources_ok
            && !self.version.trim().is_empty()
            && !self.python.trim().is_empty()
            && !self.platform.trim().is_empty()
    }
}

/// Arayüze taşınan, kullanıcıya görünen çalışma zamanı durumu.
#[derive(Debug, Clone, Serialize)]
pub struct RuntimeStatus {
    pub state: String,
    pub version: Option<String>,
    pub message: String,
    pub can_repair: bool,
}

impl RuntimeStatus {
    pub fn ready(runtime: RuntimeReady) -> Self {
        let message = match runtime.source {
            RuntimeSource::Bundled => "Fusion hazır",
            RuntimeSource::Developer => "Fusion geliştirici çalışma zamanıyla hazır",
        };
        Self {
            state: "hazir".into(),
            version: Some(runtime.version),
            message: message.into(),
            can_repair: false,
        }
    }

    /// Henüz hiçbir sürüm hazırlanmamışken (uygulama daha `prepare`
    /// çağırmadan) gösterilecek durum. Arayüz bu durumu gördüğünde
    /// otomatik olarak `runtime_hazirla` çağırır; bu yüzden `can_repair`
    /// false'tur — kullanıcının elle tetikleyeceği bir onarım değil,
    /// normal ilk kurulum akışıdır.
    fn eksik() -> Self {
        Self {
            state: "eksik".into(),
            version: None,
            message: "Çalışma zamanı henüz hazırlanmadı".into(),
            can_repair: false,
        }
    }
}

/// `~/.../Fusion/runtime/active-runtime.json` dosyasının içeriği.
///
/// Bu kayıt gerçeğin tek kaynağıdır: hangi sürümün etkin olduğunu ve
/// bozulma anında geri dönülecek bir önceki sağlıklı sürümü tutar.
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct ActiveRecord {
    pub schema: u32,
    pub active: String,
    pub previous: Option<String>,
}

impl ActiveRecord {
    pub fn new(active: &str, previous: Option<&str>) -> Self {
        Self {
            schema: 1,
            active: active.into(),
            previous: previous.map(str::to_owned),
        }
    }
}

/// Bir yürütülebilir dosyanın sağlığını denetleyen soyutlama.
///
/// Üretimde `CommandHealthProbe` gerçek ikiliyi çalıştırır; testler bu
/// trait'i sahte bir uygulamayla değiştirip gerçek süreç başlatmadan
/// senaryo kurabilir.
pub trait HealthProbe: Send + Sync {
    fn check(&self, executable: &Path) -> Result<RuntimeHealthReport, RuntimeError>;
}

/// `HealthProbe`'un üretim uygulaması: verilen ikiliyi
/// `runtime-health --json` argümanlarıyla, 30 saniye zaman aşımıyla
/// çalıştırır ve JSON çıktısını doğrular.
pub struct CommandHealthProbe;

impl HealthProbe for CommandHealthProbe {
    fn check(&self, executable: &Path) -> Result<RuntimeHealthReport, RuntimeError> {
        let output = run_with_timeout(
            executable,
            &["runtime-health", "--json"],
            SAGLIK_ZAMAN_ASIMI,
        )?;
        if !output.status.success() {
            return Err(RuntimeError::Health("sağlık komutu başarısız".into()));
        }
        let report: RuntimeHealthReport =
            serde_json::from_slice(&output.stdout).map_err(RuntimeError::HealthDecode)?;
        if !report.is_healthy() {
            return Err(RuntimeError::Health("paket kaynakları eksik".into()));
        }
        Ok(report)
    }
}

/// Verilen çocuk süreci `try_wait` ile yoklayarak çalıştırır; `timeout`
/// içinde çıkmazsa `kill` + `wait` yapıp `RuntimeError::HealthTimeout`
/// döner. stdout/stderr, boru dolup çocuğun tıkanmasını engellemek için
/// ayrı iş parçacıklarında sürekli okunur; stderr en fazla
/// `STDERR_GUNLUK_SINIRI` bayta kadar biriktirilir ve yalnızca tanılama
/// günlüğüne, sır maskesinden geçirilerek yazılır.
fn run_with_timeout(
    executable: &Path,
    args: &[&str],
    timeout: Duration,
) -> Result<std::process::Output, RuntimeError> {
    let mut child = Command::new(executable)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(RuntimeError::Io)?;

    let stdout_pipe = child
        .stdout
        .take()
        .expect("stdout piped olarak istendi, her zaman mevcuttur");
    let stderr_pipe = child
        .stderr
        .take()
        .expect("stderr piped olarak istendi, her zaman mevcuttur");
    let stdout_okuyucu = spawn_reader(stdout_pipe, usize::MAX);
    let stderr_okuyucu = spawn_reader(stderr_pipe, STDERR_GUNLUK_SINIRI);

    let baslangic = Instant::now();
    let sonuc_durumu = loop {
        if let Some(durum) = child.try_wait().map_err(RuntimeError::Io)? {
            break Some(durum);
        }
        if baslangic.elapsed() >= timeout {
            break None;
        }
        std::thread::sleep(YOKLAMA_ARALIGI);
    };

    let Some(status) = sonuc_durumu else {
        let _ = child.kill();
        let _ = child.wait();
        let _ = stdout_okuyucu.join();
        let stderr = stderr_okuyucu.join().unwrap_or_default();
        log_diagnostic_stderr(&stderr);
        return Err(RuntimeError::HealthTimeout);
    };

    let stdout = stdout_okuyucu.join().unwrap_or_default();
    let stderr = stderr_okuyucu.join().unwrap_or_default();
    log_diagnostic_stderr(&stderr);
    Ok(std::process::Output {
        status,
        stdout,
        stderr,
    })
}

/// Bir boruyu ayrı bir iş parçacığında sonuna kadar okur; `limit`'e kadar
/// olan bayt biriktirilir, fazlası atılır ama boru yine de tüketilerek
/// çocuk sürecin tıkanması engellenir.
fn spawn_reader<R: std::io::Read + Send + 'static>(
    mut pipe: R,
    limit: usize,
) -> std::thread::JoinHandle<Vec<u8>> {
    std::thread::spawn(move || {
        let mut buffer = Vec::new();
        let mut parca = [0u8; 4096];
        loop {
            match pipe.read(&mut parca) {
                Ok(0) => break,
                Ok(okunan) => {
                    if buffer.len() < limit {
                        let alinacak = (limit - buffer.len()).min(okunan);
                        buffer.extend_from_slice(&parca[..alinacak]);
                    }
                }
                Err(_) => break,
            }
        }
        buffer
    })
}

/// Tanılama metnindeki olası sırları maskeler: anahtar kelimelerden
/// birini içeren her kelime `***` ile değiştirilir.
fn mask_secrets(text: &str) -> String {
    text.split_whitespace()
        .map(|kelime| {
            let kucuk = kelime.to_ascii_lowercase();
            if HASSAS_ANAHTAR_KELIMELER
                .iter()
                .any(|anahtar| kucuk.contains(anahtar))
            {
                "***"
            } else {
                kelime
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

/// Çocuk sürecin stderr'ini yalnızca uygulama tanılama günlüğüne yazar;
/// kullanıcıya görünen hiçbir hata metnine ham stderr eklenmez.
fn log_diagnostic_stderr(bytes: &[u8]) {
    if bytes.is_empty() {
        return;
    }
    let sinirli = &bytes[..bytes.len().min(STDERR_GUNLUK_SINIRI)];
    let metin = String::from_utf8_lossy(sinirli);
    eprintln!("[fusion][runtime-health] {}", mask_secrets(&metin));
}

/// Sağlık, etkin sürüm, onarım ve rollback'i tek yerde toplayan yönetici.
///
/// `prepare`/`repair` çağrıldıktan sonra `status`/`executable` en son
/// başarılı sonucu yansıtır; `executable`, hiçbir sağlıklı çalışma zamanı
/// hazırlanmadan çağrılırsa `RuntimeError::NoHealthyRuntime` döner.
///
/// `Clone` derive edilir: paylaşılan durum (`hazir`) `Arc<Mutex<..>>`
/// içinde tutulur, böylece Tauri komutları `tauri::State` yaşam süresini
/// `async`/`spawn_blocking` sınırının ötesine taşımadan yöneticinin
/// sahipli bir klonunu alıp arka plan iş parçacığına gönderebilir.
#[derive(Clone)]
pub struct RuntimeManager {
    resources: RuntimeResources,
    paths: RuntimePaths,
    expected_target: String,
    probe: Arc<dyn HealthProbe>,
    hazir: Arc<Mutex<Option<RuntimeReady>>>,
}

impl RuntimeManager {
    pub fn new(
        resources: RuntimeResources,
        paths: RuntimePaths,
        expected_target: impl Into<String>,
        probe: Arc<dyn HealthProbe>,
    ) -> Self {
        Self {
            resources,
            paths,
            expected_target: expected_target.into(),
            probe,
            hazir: Arc::new(Mutex::new(None)),
        }
    }

    /// Çalışma zamanını kullanıma hazırlar.
    ///
    /// Paket içindeki sürüm, eski ama sağlıklı aktif sürümden ÖNCE
    /// denenir: böylece uygulama güncellemesi yeni runtime'ı gerçekten
    /// kurar, ama yeni paket bozuksa eski sağlıklı sürüm korunur.
    pub fn prepare(
        &self,
        progress: impl FnMut(RuntimeProgress),
    ) -> Result<RuntimeReady, RuntimeError> {
        let record = self.read_active()?;
        let packaged_version =
            RuntimeManifest::read(&self.resources.manifest_path)?.runtime_version;

        if record
            .as_ref()
            .is_some_and(|item| item.active == packaged_version)
        {
            if let Ok(active) = self.healthy_version(&packaged_version) {
                self.remember(active.clone());
                return Ok(active);
            }
        }

        match install(
            &self.resources,
            &self.paths,
            &self.expected_target,
            |executable| self.probe.check(executable).map(|_| ()),
            progress,
        ) {
            Ok(installed) => {
                let previous = record.as_ref().and_then(|item| {
                    if item.active != installed.version {
                        Some(item.active.as_str())
                    } else {
                        item.previous.as_deref()
                    }
                });
                self.write_active_atomic(&ActiveRecord::new(&installed.version, previous))?;
                let ready = RuntimeReady {
                    version: installed.version,
                    executable: installed.executable,
                    source: RuntimeSource::Bundled,
                };
                self.remember(ready.clone());
                Ok(ready)
            }
            Err(install_error) => self.fallback_or_error(record, install_error),
        }
    }

    /// Paket sürümünü, installer'ın aynı-sürüm karantina yoluyla, kullanıcı
    /// verisine dokunmadan yeniden kurar. Sağlık denetimi geçmeden etkin
    /// kaydı DEĞİŞTİRMEZ.
    pub fn repair(
        &self,
        progress: impl FnMut(RuntimeProgress),
    ) -> Result<RuntimeReady, RuntimeError> {
        let record = self.read_active()?;
        let installed = install(
            &self.resources,
            &self.paths,
            &self.expected_target,
            |executable| self.probe.check(executable).map(|_| ()),
            progress,
        )?;

        let previous = record.as_ref().and_then(|item| {
            if item.active != installed.version {
                Some(item.active.as_str())
            } else {
                item.previous.as_deref()
            }
        });
        self.write_active_atomic(&ActiveRecord::new(&installed.version, previous))?;
        let ready = RuntimeReady {
            version: installed.version,
            executable: installed.executable,
            source: RuntimeSource::Bundled,
        };
        self.remember(ready.clone());
        Ok(ready)
    }

    /// Arayüzün gösterebileceği güncel durumu döner; ağ çağrısı yapmaz,
    /// yalnızca en son `prepare`/`repair` sonucunu yansıtır.
    pub fn status(&self) -> RuntimeStatus {
        match self.hazir.lock().unwrap().clone() {
            Some(ready) => RuntimeStatus::ready(ready),
            None => RuntimeStatus::eksik(),
        }
    }

    /// `prepare`/`repair` sonrası hazır çalışma zamanının yolunu döner.
    pub fn executable(&self) -> Result<PathBuf, RuntimeError> {
        self.hazir
            .lock()
            .unwrap()
            .clone()
            .map(|ready| ready.executable)
            .ok_or(RuntimeError::NoHealthyRuntime)
    }

    fn remember(&self, ready: RuntimeReady) {
        *self.hazir.lock().unwrap() = Some(ready);
    }

    /// Kurulum başarısız olunca aktif kayıttaki sürümleri (önce mevcut
    /// aktif, sonra bir önceki) sırayla dener; ilk sağlıklı olanı etkin
    /// yapıp döner. Hiçbiri sağlıklı değilse asıl kurulum hatasını döner.
    fn fallback_or_error(
        &self,
        record: Option<ActiveRecord>,
        error: RuntimeError,
    ) -> Result<RuntimeReady, RuntimeError> {
        for version in record
            .into_iter()
            .flat_map(|item| [Some(item.active), item.previous])
            .flatten()
        {
            if let Ok(ready) = self.healthy_version(&version) {
                self.write_active_atomic(&ActiveRecord::new(&version, None))?;
                self.remember(ready.clone());
                return Ok(ready);
            }
        }
        Err(error)
    }

    /// Verilen sürümün diskte kurulu olduğunu ve sağlık denetiminden
    /// geçtiğini doğrular; ikisinden biri sağlanmazsa hata döner.
    fn healthy_version(&self, version: &str) -> Result<RuntimeReady, RuntimeError> {
        let manifest = RuntimeManifest::read(&self.resources.manifest_path)?;
        let entrypoint = safe_relative(&manifest.entrypoint)?;
        let executable = self.paths.version_dir(version).join(entrypoint);
        if !executable.exists() {
            return Err(RuntimeError::NoHealthyRuntime);
        }
        self.probe.check(&executable)?;
        Ok(RuntimeReady {
            version: version.to_string(),
            executable,
            source: RuntimeSource::Bundled,
        })
    }

    /// `active-runtime.json`'ı okur; dosya yoksa `Ok(None)` döner (henüz
    /// hiçbir sürüm etkinleştirilmemiş demektir), bozuksa tipli bir hata
    /// döner — asla sessizce "aktif kayıt yok" gibi davranmaz.
    fn read_active(&self) -> Result<Option<ActiveRecord>, RuntimeError> {
        match std::fs::read_to_string(&self.paths.active_record) {
            Ok(icerik) => {
                let record =
                    serde_json::from_str(&icerik).map_err(RuntimeError::ActiveRecordDecode)?;
                Ok(Some(record))
            }
            Err(hata) if hata.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(hata) => Err(RuntimeError::Io(hata)),
        }
    }

    /// Etkin kaydı, aynı dizindeki geçici bir dosyaya yazıp `sync_all`
    /// yaptıktan sonra `rename` ederek atomik biçimde günceller. Böylece
    /// yarım yazılmış bir kayıt asla `active-runtime.json` adında
    /// görünmez.
    fn write_active_atomic(&self, record: &ActiveRecord) -> Result<(), RuntimeError> {
        std::fs::create_dir_all(&self.paths.root).map_err(RuntimeError::Io)?;
        let gecici = self
            .paths
            .root
            .join(format!("active-runtime.json.tmp-{}", std::process::id()));
        let icerik = serde_json::to_vec_pretty(record).map_err(RuntimeError::ActiveRecordEncode)?;
        {
            use std::io::Write;
            let mut dosya = std::fs::File::create(&gecici).map_err(RuntimeError::Io)?;
            dosya.write_all(&icerik).map_err(RuntimeError::Io)?;
            dosya.sync_all().map_err(RuntimeError::Io)?;
        }
        std::fs::rename(&gecici, &self.paths.active_record).map_err(RuntimeError::Io)?;
        Ok(())
    }
}

impl RuntimeResources {
    /// Uygulamanın paketlenmiş kaynak dizininden `runtime-manifest.json`
    /// ve `fusion-runtime.tar.gz` yollarını çözer.
    pub fn from_app(app: &AppHandle) -> Result<Self, RuntimeError> {
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|hata| RuntimeError::ResourceDir(hata.to_string()))?;
        let runtime_dir = resource_dir.join("runtime");
        Ok(Self {
            manifest_path: runtime_dir.join("runtime-manifest.json"),
            archive_path: runtime_dir.join("fusion-runtime.tar.gz"),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;
    use std::os::unix::fs::PermissionsExt;

    const TEST_TARGET: &str = "aarch64-apple-darwin";
    const PAKET_SURUMU: &str = "0.3.0a1";

    /// Sahte sağlık probu: gerçek süreç başlatmadan, verilen yürütülebilir
    /// dosyanın içeriğindeki sürüm işaretine göre geçer/kalır kararı verir.
    /// `pass`/`fail` fixture'dan çağrılıp senaryo kurar; işaretlenmemiş
    /// sürümler varsayılan olarak SAĞLIKLI kabul edilir (onarım testinde
    /// olduğu gibi, yeniden kurulan bir sürümün baştan sağlıklı olması
    /// beklenir).
    struct FakeProbe {
        sonuclar: Mutex<HashMap<String, bool>>,
    }

    impl FakeProbe {
        fn new() -> Arc<Self> {
            Arc::new(Self {
                sonuclar: Mutex::new(HashMap::new()),
            })
        }

        fn pass(&self, version: &str) {
            self.sonuclar
                .lock()
                .unwrap()
                .insert(version.to_string(), true);
        }

        fn fail(&self, version: &str) {
            self.sonuclar
                .lock()
                .unwrap()
                .insert(version.to_string(), false);
        }
    }

    impl HealthProbe for FakeProbe {
        fn check(&self, executable: &Path) -> Result<RuntimeHealthReport, RuntimeError> {
            let icerik = std::fs::read_to_string(executable).map_err(RuntimeError::Io)?;
            let version = extract_version_marker(&icerik);
            let basarisiz = matches!(self.sonuclar.lock().unwrap().get(&version), Some(false));
            if basarisiz {
                return Err(RuntimeError::Health(format!(
                    "sahte prob {version} için sağlıksız işaretledi"
                )));
            }
            Ok(RuntimeHealthReport {
                ok: true,
                version,
                python: "3.11.0".into(),
                platform: "test".into(),
                resources_ok: true,
            })
        }
    }

    fn extract_version_marker(content: &str) -> String {
        content
            .lines()
            .find_map(|line| line.trim().strip_prefix("echo fusion-"))
            .unwrap_or("bilinmeyen")
            .to_string()
    }

    #[test]
    fn saglik_raporu_tum_sozlesmeyi_dogrular() {
        let mut report = RuntimeHealthReport {
            ok: true,
            version: "0.3.0a1".into(),
            python: "3.11.0".into(),
            platform: "macOS-arm64".into(),
            resources_ok: true,
        };
        assert!(report.is_healthy());

        report.resources_ok = false;
        assert!(!report.is_healthy());
        report.resources_ok = true;
        report.python.clear();
        assert!(!report.is_healthy());
    }

    struct ManagerFixture {
        _temp: tempfile::TempDir,
        paths: RuntimePaths,
        manager: RuntimeManager,
        probe: Arc<FakeProbe>,
        application_support: PathBuf,
    }

    impl ManagerFixture {
        fn new() -> Self {
            let temp = tempfile::tempdir().expect("geçici dizin oluşturulamadı");
            let paths = RuntimePaths::for_home(temp.path());
            std::fs::create_dir_all(&paths.root).unwrap();
            let application_support = paths
                .root
                .parent()
                .expect("runtime kökünün bir üst dizini vardır")
                .to_path_buf();

            let manifest_path = temp.path().join("runtime-manifest.json");
            let archive_path = temp.path().join("fusion-runtime.tar.gz");
            write_fixture_package(&archive_path, &manifest_path, PAKET_SURUMU);

            let probe = FakeProbe::new();
            let manager = RuntimeManager::new(
                RuntimeResources {
                    manifest_path,
                    archive_path,
                },
                paths.clone(),
                TEST_TARGET,
                probe.clone(),
            );

            Self {
                _temp: temp,
                paths,
                manager,
                probe,
                application_support,
            }
        }

        fn with_active(version: &str) -> Self {
            let fixture = Self::new();
            fixture.install_existing_version(version);
            fixture.write_active_record(version, None);
            fixture
        }

        fn with_record(active: &str, previous: Option<&str>) -> Self {
            let fixture = Self::new();
            fixture.install_existing_version(active);
            if let Some(onceki) = previous {
                fixture.install_existing_version(onceki);
            }
            fixture.write_active_record(active, previous);
            fixture
        }

        fn with_corrupt_packaged_version() -> Self {
            let fixture = Self::new();
            let bozuk_dizin = fixture.paths.version_dir(PAKET_SURUMU);
            std::fs::create_dir_all(&bozuk_dizin).unwrap();
            std::fs::write(bozuk_dizin.join("fusion"), b"bozuk ikili").unwrap();
            fixture.write_active_record(PAKET_SURUMU, None);
            fixture
        }

        fn install_existing_version(&self, version: &str) {
            let dizin = self.paths.version_dir(version);
            std::fs::create_dir_all(&dizin).unwrap();
            let executable = dizin.join("fusion");
            std::fs::write(&executable, format!("#!/bin/sh\necho fusion-{version}\n")).unwrap();
            let mut izinler = std::fs::metadata(&executable).unwrap().permissions();
            izinler.set_mode(0o755);
            std::fs::set_permissions(&executable, izinler).unwrap();
        }

        fn write_active_record(&self, active: &str, previous: Option<&str>) {
            let record = ActiveRecord::new(active, previous);
            std::fs::write(
                &self.paths.active_record,
                serde_json::to_vec_pretty(&record).unwrap(),
            )
            .unwrap();
        }

        fn active_record(&self) -> ActiveRecord {
            let icerik = std::fs::read_to_string(&self.paths.active_record).unwrap();
            serde_json::from_str(&icerik).unwrap()
        }
    }

    /// Testler için gerçek, küçük bir gzip/tar paket arşivi ve eşleşen
    /// manifest üretir; kurulum kodunu hiçbir yerde mocklamaz.
    fn write_fixture_package(archive_path: &Path, manifest_path: &Path, version: &str) {
        let content = format!("#!/bin/sh\necho fusion-{version}\n");
        let archive_bytes = build_tar_gz("fusion", content.as_bytes(), 0o755);
        std::fs::write(archive_path, &archive_bytes).unwrap();
        let archive_hash = sha256_hex(&archive_bytes);
        let file_hash = sha256_hex(content.as_bytes());

        let manifest = serde_json::json!({
            "schema": 1,
            "runtime_version": version,
            "target": TEST_TARGET,
            "archive": "fusion-runtime.tar.gz",
            "archive_sha256": archive_hash,
            "entrypoint": "fusion",
            "files": [{
                "path": "fusion",
                "kind": "file",
                "mode": 0o755,
                "sha256": file_hash,
                "target": null,
            }],
        });
        std::fs::write(manifest_path, serde_json::to_vec_pretty(&manifest).unwrap()).unwrap();
    }

    fn build_tar_gz(name: &str, content: &[u8], mode: u32) -> Vec<u8> {
        let buffer = Vec::new();
        let encoder = flate2::write::GzEncoder::new(buffer, flate2::Compression::default());
        let mut builder = tar::Builder::new(encoder);
        let mut header = tar::Header::new_gnu();
        header.set_path(name).unwrap();
        header.set_size(content.len() as u64);
        header.set_mode(mode);
        header.set_cksum();
        builder.append(&header, content).unwrap();
        let encoder = builder.into_inner().unwrap();
        encoder.finish().unwrap()
    }

    fn sha256_hex(bytes: &[u8]) -> String {
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update(bytes);
        hex::encode(hasher.finalize())
    }

    #[test]
    fn yeni_surum_saglikliysa_etkin_previous_eski_surum_olur() {
        let fixture = ManagerFixture::with_active("0.2.9");
        fixture.probe.pass("0.3.0a1");
        let ready = fixture.manager.prepare(|_| {}).unwrap();
        assert_eq!(ready.version, "0.3.0a1");
        assert_eq!(
            fixture.active_record(),
            ActiveRecord::new("0.3.0a1", Some("0.2.9"))
        );
    }

    #[test]
    fn yeni_surum_sagliksizsa_aktif_kayit_degismez() {
        let fixture = ManagerFixture::with_active("0.2.9");
        fixture.probe.fail("0.3.0a1");
        fixture.probe.pass("0.2.9");
        let ready = fixture.manager.prepare(|_| {}).unwrap();
        assert_eq!(ready.version, "0.2.9");
        assert_eq!(fixture.active_record().active, "0.2.9");
    }

    #[test]
    fn aktif_runtime_bozuksa_onceki_saglikli_surume_doner() {
        let fixture = ManagerFixture::with_record("0.3.0a1", Some("0.2.9"));
        fixture.probe.fail("0.3.0a1");
        fixture.probe.pass("0.2.9");
        let ready = fixture.manager.prepare(|_| {}).unwrap();
        assert_eq!(ready.version, "0.2.9");
        assert_eq!(fixture.active_record().active, "0.2.9");
    }

    #[test]
    fn repair_kullanici_verisine_dokunmadan_paket_surumu_yeniden_kurar() {
        let fixture = ManagerFixture::with_corrupt_packaged_version();
        let user_config = fixture.application_support.join("config.yaml");
        std::fs::write(&user_config, "keep").unwrap();
        fixture.manager.repair(|_| {}).unwrap();
        assert_eq!(std::fs::read_to_string(user_config).unwrap(), "keep");
    }

    #[test]
    fn saglikli_calisma_zamani_hazirlanmadan_executable_hata_doner() {
        let fixture = ManagerFixture::with_active("0.2.9");
        assert!(matches!(
            fixture.manager.executable(),
            Err(RuntimeError::NoHealthyRuntime)
        ));
    }

    #[test]
    fn hazirlanmis_calisma_zamani_status_hazir_doner() {
        let fixture = ManagerFixture::with_active("0.2.9");
        fixture.probe.pass("0.3.0a1");
        let ready = fixture.manager.prepare(|_| {}).unwrap();
        assert_eq!(fixture.manager.executable().unwrap(), ready.executable);
        assert_eq!(fixture.manager.status().state, "hazir");
    }
}
