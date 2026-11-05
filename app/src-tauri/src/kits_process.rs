//! Fusion Kits yan süreci: bağımsız Node sunucusunu uygulamanın çocuğu olarak
//! başlatır, hazır olmasını bekler ve uygulama kapanırken durdurur.
//!
//! Kits ayrı bir modüldür (bkz. `fusion-kits/handoff/BIRLESTIRME.md`); arayüz onu
//! iframe ile gömer. Bu modül yalnız süreç sahipliğini taşır: Kits'in kendi
//! owner token'ı, veritabanı ve `.env` ayarı Kits'e aittir, buradan okunmaz.

use std::io::{Read, Seek, SeekFrom};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

/// Kits `package.json` `engines.node` alt sınırı.
const MIN_NODE_MAJOR: u32 = 24;
/// Derlenmiş sunucu girişi; yoksa Kits henüz derlenmemiştir.
const SERVER_ENTRY: &str = "dist/server/server/index.js";
/// Sunucunun portu dinlemeye başlaması için tanınan süre. Ölçüldü (4 Ekim,
/// 8 GB M1): soğuk açılış 2-4 sn; yük altındaki makine için pay bırakıldı.
const READY_TIMEOUT: Duration = Duration::from_secs(30);
/// Hazırlık yoklaması kısa başlar, her turda ikiye katlanır, üst sınırda kalır. Ölçüldü
/// (31 Ekim, paketli 0.7.19): geçitsiz sunucu 0,2 sn'de, geçitli 1-1,5 sn'de hazır; sabit
/// 150 ms aralık her açılışa ortalama ~75 ms boş bekleme ekliyordu.
const READY_POLL_FIRST: Duration = Duration::from_millis(10);
const READY_POLL_MAX: Duration = Duration::from_millis(100);
/// iframe'i gömebilecek origin'ler: paketli Tauri (macOS / Windows) ve geliştirme.
const HOST_ORIGINS: &str =
    r#"["tauri://localhost","http://tauri.localhost","http://localhost:1420"]"#;

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct KitsStatus {
    pub url: String,
}

const KITS_LOG_FILE: &str = "kits.log";
/// Kits'in dinlediği adresi Fusion çekirdeğine duyuran durum dosyası (P-063).
const KITS_STATE_FILE: &str = "kits-bridge.json";
/// Hazırlık makbuzu için okunan günlük kuyruğu.
const READY_LOG_TAIL: u64 = 256 * 1024;
/// `node --version` yoklamasının en uzun süresi; takılan bir aday tüm başlatmayı bloklamasın.
const NODE_PROBE_TIMEOUT: Duration = Duration::from_secs(5);

/// Kits veri klasörü: Fusion çekirdeğinin `config/paths.py kits_data_dir()` kuralıyla AYNI.
///
/// Unix'te `XDG_DATA_HOME` ayarlıysa oradan, yoksa `~/.local/share`; Windows'ta yerel veri
/// klasörü. Ölçüldü (31 Ekim, inceleme): Tauri `XDG_DATA_HOME`'u yok sayıp `~/.local/share`
/// yazıyordu; Python okurken XDG'yi dikkate alıyordu. XDG ayarlı kullanıcıda Fusion
/// `kits-bridge.json`'ı bulamayıp varsayılan porta düşüyor ve "Kits çalışmıyor" diyordu.
pub fn kits_data_dir(
    home: &Path,
    xdg_data_home: Option<&str>,
    windows_local_data: Option<&Path>,
) -> PathBuf {
    let root = match windows_local_data {
        Some(local) => local.to_path_buf(),
        None => match xdg_data_home
            .map(str::trim)
            .filter(|value| !value.is_empty())
        {
            Some(xdg) => PathBuf::from(xdg),
            None => home.join(".local/share"),
        },
    };
    root.join("fusion-cli").join("kits")
}

struct Running {
    child: Child,
    url: String,
}

#[derive(Default)]
pub struct KitsManager {
    running: Mutex<Option<Running>>,
    /// Node --version is an owned startup child too, before a server exists.
    probe: Mutex<Option<Child>>,
    /// Başlatıcıları sıraya dizer; `running` kilidi bekleme boyunca TUTULMAZ, yoksa uygulama
    /// kapanırken `stop()` 30+ sn bloke olurdu (R2-07).
    start_gate: Mutex<()>,
    /// `stop()` çağrıldı: bekleyen başlatma vazgeçer, hazır olan çocuk yetim bırakılmaz.
    stopping: AtomicBool,
}

impl KitsManager {
    pub fn new() -> Self {
        Self::default()
    }

    /// Çalışan sunucunun adresini döndürür; yoksa başlatır.
    pub fn ensure_started(
        &self,
        home: &Path,
        data_dir: &Path,
        resource_dir: Option<&Path>,
        core: &Path,
    ) -> Result<KitsStatus, String> {
        let _gate = self
            .start_gate
            .lock()
            .map_err(|_| "Kits başlatma kilidi alınamadı.".to_string())?;
        {
            let mut slot = self
                .running
                .lock()
                .map_err(|_| "Kits süreç kilidi alınamadı.".to_string())?;
            if let Some(running) = slot.as_mut() {
                if matches!(child_exited(&mut running.child), Ok(false)) {
                    return Ok(KitsStatus {
                        url: running.url.clone(),
                    });
                }
                terminate_gracefully(&mut running.child);
                *slot = None;
            }
        }
        if self.stopping.load(Ordering::SeqCst) {
            return Err("Uygulama kapanıyor; Kits başlatılmadı.".to_string());
        }
        let kits_dir = find_kits_dir(&kits_dir_candidates(data_dir, resource_dir))?;
        let node = self.find_node(&node_candidates(home, resource_dir))?;
        let port = free_port()?;
        let mut nonce_bytes = [0u8; 16];
        getrandom::fill(&mut nonce_bytes)
            .map_err(|_| "Kits başlangıç kimliği üretilemedi.".to_string())?;
        let nonce = hex::encode(nonce_bytes);
        std::fs::create_dir_all(data_dir)
            .map_err(|error| format!("Kits veri klasörü oluşturulamadı: {error}"))?;
        let _ = std::fs::write(data_dir.join(KITS_LOG_FILE), b"");
        // Model ayarı (.env) Kits'in veri klasöründe durur; paket klasörü her
        // kurulumda yenilendiği için ayar orada tutulmaz. Geliştirme kopyasında
        // klasörün kendi .env dosyası da okunur.
        let workspace = data_dir.join("workspace");
        let sessions = data_dir.join("sessions");
        std::fs::create_dir_all(&workspace)
            .and_then(|_| std::fs::create_dir_all(&sessions))
            .map_err(|_| "Fusion Kits çalışma alanı oluşturulamadı.".to_string())?;
        let env_file = format!("--env-file-if-exists={}", data_dir.join(".env").display());
        let mut command = Command::new(node);
        command
            .args([env_file.as_str(), "--env-file-if-exists=.env", SERVER_ENTRY])
            .current_dir(&kits_dir)
            .env("FUSION_COMMAND", core)
            .env("FUSION_ARGS", r#"["app"]"#)
            .env("FUSION_ROOT", &workspace)
            .env("FUSION_HOME", &sessions)
            .env("FUSION_SHARE_USER_CONFIG", "1")
            .env("FUSION_USER_HOME", home)
            .env("KITS_GATEWAY_MODEL", "auto")
            .env("COPILOTKIT_TELEMETRY_DISABLED", "true")
            .env("HOST", "127.0.0.1")
            .env("PORT", port.to_string())
            .env("KITS_DESKTOP_READY_NONCE", &nonce)
            .env("DATABASE_PATH", data_dir.join("fusion-kits.sqlite"))
            .env("OWNER_ID", "fusion-kits-owner")
            .env("COMPUTER_NAMESPACE", "fusion-kits")
            .env("KITS_HOST_ORIGINS", HOST_ORIGINS)
            // Fusion çekirdeği (CLI aracı/masaüstü oturumu) Kits'in adresini bu dosyadan
            // okur (`config/paths.py kits_state_file()`); Kits yalnız adres ve pid yazar.
            .env("KITS_STATE_FILE", data_dir.join(KITS_STATE_FILE))
            .stdin(Stdio::null())
            .stdout(log_sink(data_dir))
            .stderr(log_sink(data_dir));
        crate::core_process::kendi_grubunda(&mut command);
        let url = format!("http://127.0.0.1:{port}");
        {
            // Publish ownership at spawn, before readiness. stop() never needs
            // the startup worker to finish after the native host has exited.
            let mut slot = self
                .running
                .lock()
                .map_err(|_| "Kits süreç kilidi alınamadı.".to_string())?;
            if self.stopping.load(Ordering::SeqCst) {
                return Err("Uygulama kapanıyor; Kits başlatılmadı.".to_string());
            }
            let child = crate::core_process::pencere_acmadan(&mut command)
                .spawn()
                .map_err(|error| format!("Kits sunucusu başlatılamadı: {error}"))?;
            *slot = Some(Running {
                child,
                url: url.clone(),
            });
        }
        let ready = wait_ready_check(READY_TIMEOUT, &self.stopping, || {
            let mut slot = self
                .running
                .lock()
                .map_err(|_| "Kits süreç kilidi alınamadı.".to_string())?;
            let running = slot
                .as_mut()
                .ok_or_else(|| "Uygulama kapanıyor; Kits durduruldu.".to_string())?;
            check_ready_owned(
                &mut running.child,
                port,
                &data_dir.join(KITS_LOG_FILE),
                &nonce,
            )
        });
        let mut slot = self
            .running
            .lock()
            .map_err(|_| "Kits süreç kilidi alınamadı.".to_string())?;
        if let Err(error) = ready {
            if let Some(mut running) = slot.take() {
                terminate_gracefully(&mut running.child);
            }
            return Err(error);
        }
        if self.stopping.load(Ordering::SeqCst) {
            if let Some(mut running) = slot.take() {
                terminate_gracefully(&mut running.child);
            }
            return Err("Uygulama kapanıyor; Kits durduruldu.".to_string());
        }
        Ok(KitsStatus { url })
    }

    /// Uygulama kapanırken çağrılır. Kits SIGTERM'de kendi çocuklarını kapatır;
    /// süre dolarsa zorla sonlandırılır.
    pub fn stop(&self) {
        self.stopping.store(true, Ordering::SeqCst);
        if let Ok(mut probe) = self.probe.lock() {
            if let Some(mut child) = probe.take() {
                terminate_gracefully(&mut child);
            }
        }
        let Ok(mut slot) = self.running.lock() else {
            return;
        };
        if let Some(mut running) = slot.take() {
            terminate_gracefully(&mut running.child);
        }
    }
}

/// Kits çıktısı `kits.log`'a yazılır; süreç sessizce ölünce ("Failed to fetch")
/// sebebi ancak buradan görülür. Her başlatmada dosya baştan yazılır, büyümez.
/// Açılamazsa çıktı atılır; günlük yüzünden Kits'in açılmaması kabul edilmez.
fn log_sink(data_dir: &Path) -> Stdio {
    std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(data_dir.join(KITS_LOG_FILE))
        .map(Stdio::from)
        .unwrap_or_else(|_| Stdio::null())
}

/// Observe exit without reaping on Unix: the owned leader reserves its PID/PGID
/// until the last group signal. No group signal may be sent after `Child::wait`.
fn child_exited(child: &mut Child) -> std::io::Result<bool> {
    #[cfg(unix)]
    {
        // SAFETY: zero is a valid initial siginfo_t; waitid writes only this value.
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        loop {
            // SAFETY: this is our unreaped child; WNOWAIT preserves ownership.
            let result = unsafe {
                libc::waitid(
                    libc::P_PID,
                    child.id() as libc::id_t,
                    &mut info,
                    libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
                )
            };
            if result == 0 {
                // SAFETY: waitid initialized siginfo_t; zero means no exit yet.
                return Ok(unsafe { info.si_pid() } != 0);
            }
            let error = std::io::Error::last_os_error();
            if error.kind() != std::io::ErrorKind::Interrupted {
                return Err(error);
            }
        }
    }
    #[cfg(not(unix))]
    {
        child.try_wait().map(|status| status.is_some())
    }
}

/// Only children launched with `kendi_grubunda` are admitted here.
fn terminate_gracefully(child: &mut Child) {
    #[cfg(unix)]
    {
        if let Ok(pid) = i32::try_from(child.id()) {
            // SAFETY: the owned unreaped child is its group leader. Signals never
            // include the host group, independently started Kits or name matches.
            unsafe { libc::killpg(pid, libc::SIGTERM) };
        }
        let deadline = Instant::now() + crate::core_process::DURDURMA_ZAMAN_ASIMI;
        while Instant::now() < deadline {
            if !matches!(child_exited(child), Ok(false)) {
                break;
            }
            std::thread::sleep(crate::core_process::YOKLAMA_ARALIGI);
        }
        if let Ok(pid) = i32::try_from(child.id()) {
            // SAFETY: the leader has not been reaped, so the PGID cannot be reused.
            // Even if the leader exited promptly, a descendant may ignore TERM.
            unsafe { libc::killpg(pid, libc::SIGKILL) };
        }
    }
    let _ = child.kill();
    let _ = child.wait();
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReadyReceipt {
    fusion_kits_ready: u8,
    nonce: String,
    port: u16,
    pid: u32,
}

fn ready_receipt_matches(line: &str, nonce: &str, pid: u32, port: u16) -> bool {
    serde_json::from_str::<ReadyReceipt>(line).is_ok_and(|receipt| {
        receipt.fusion_kits_ready == 1
            && receipt.nonce == nonce
            && receipt.pid == pid
            && receipt.port == port
    })
}

fn readiness_logged(log: &Path, nonce: &str, pid: u32, port: u16) -> Result<bool, String> {
    let mut file = match std::fs::File::open(log) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(_) => return Err("Kits başlangıç kaydı açılamadı.".to_string()),
    };
    // Kits açılışta çok yazarsa (npm uyarıları, hata ayıklama) dosya 256 KB'ı aşabilir; bu
    // hata sayılmaz: yalnız SON 256 KB okunur (R2-08). Kesilen ilk yarım satır atılır.
    let length = file
        .metadata()
        .map_err(|_| "Kits başlangıç kaydı okunamadı.".to_string())?
        .len();
    let start = length.saturating_sub(READY_LOG_TAIL);
    file.seek(SeekFrom::Start(start))
        .map_err(|_| "Kits başlangıç kaydı okunamadı.".to_string())?;
    let mut bytes = Vec::new();
    file.take(READY_LOG_TAIL)
        .read_to_end(&mut bytes)
        .map_err(|_| "Kits başlangıç kaydı okunamadı.".to_string())?;
    if start > 0 {
        let first_line = bytes
            .iter()
            .position(|byte| *byte == b'\n')
            .map_or(bytes.len(), |index| index + 1);
        bytes.drain(..first_line);
    }
    // Yazılmakta olan son satır veya yarım UTF-8 sağlıklı çocuğu düşürmez.
    Ok(bytes.split_inclusive(|byte| *byte == b'\n').any(|line| {
        line.ends_with(b"\n")
            && std::str::from_utf8(line)
                .is_ok_and(|text| ready_receipt_matches(text.trim_end(), nonce, pid, port))
    }))
}

#[cfg(test)]
fn wait_ready_owned(
    child: &mut Child,
    port: u16,
    timeout: Duration,
    log: &Path,
    nonce: &str,
    abort: &AtomicBool,
) -> Result<(), String> {
    wait_ready_check(timeout, abort, || {
        check_ready_owned(child, port, log, nonce)
    })
}

fn check_ready_owned(
    child: &mut Child,
    port: u16,
    log: &Path,
    nonce: &str,
) -> Result<bool, String> {
    match child_exited(child) {
        Ok(true) => return Err("Fusion Kits başlatılamadı (sunucu kapandı). Yeniden dene; sorun sürerse Fusion uygulama paketini güncelle.".into()),
        Err(_) => return Err("Kits süreç durumu okunamadı.".to_string()),
        Ok(false) => {},
    }
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    if readiness_logged(log, nonce, child.id(), port)?
        && TcpStream::connect_timeout(&address, READY_POLL_MAX).is_ok()
    {
        return match child_exited(child) {
            Ok(false) => Ok(true),
            _ => Err("Kits sunucusu hazır olurken kapandı.".to_string()),
        };
    }
    Ok(false)
}

fn wait_ready_check(
    timeout: Duration,
    abort: &AtomicBool,
    mut ready: impl FnMut() -> Result<bool, String>,
) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    let mut poll = READY_POLL_FIRST;
    while Instant::now() < deadline {
        if abort.load(Ordering::SeqCst) {
            return Err("Uygulama kapanıyor; Kits beklemesi bırakıldı.".to_string());
        }
        if ready()? {
            return Ok(());
        }
        std::thread::sleep(poll);
        poll = next_poll(poll);
    }
    Err("Kits bağlantısı zamanında doğrulanamadı. Uygulamayla birlikte gelen Kits paketini kullanıp yeniden dene.".to_string())
}

/// Bir sonraki yoklama aralığı: ikiye katlanır, `READY_POLL_MAX`'ı aşmaz.
fn next_poll(current: Duration) -> Duration {
    current.saturating_mul(2).min(READY_POLL_MAX)
}

fn reserve_port() -> Result<TcpListener, String> {
    TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| format!("Kits için boş port bulunamadı: {error}"))
}

/// En iyi çaba: Node bağlanana kadar portu başka süreç alabilir; hazır olma makbuzla doğrulanır.
fn free_port() -> Result<u16, String> {
    reserve_port()?
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| format!("Kits için boş port bulunamadı: {error}"))
}

/// Geliştirici ortam değişkeni geçersiz kılmaları YALNIZ hata ayıklama derlemesinde etkindir
/// (R2-10): yayında ortam değişkeniyle keyfi Node/JS çalıştırılamaz; çekirdekteki
/// "paketlenmiş olandan başka çalıştırma" ilkesiyle aynı çizgi.
fn developer_override(name: &str) -> Option<std::ffi::OsString> {
    if cfg!(debug_assertions) {
        std::env::var_os(name)
    } else {
        None
    }
}

/// Aranan sıra: açık ayar → uygulamayla gelen paket → uygulama verisine kurulmuş
/// kopya (`<veri>/app`) → geliştirici düzeni (depo yanındaki `fusion-kits`).
fn kits_dir_candidates(data_dir: &Path, resource_dir: Option<&Path>) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = developer_override("FUSION_KITS_DIR") {
        candidates.push(PathBuf::from(explicit));
    }
    // Uygulamayla birlikte gelen paket, elle kurulan kopyadan önce gelir: sürümü
    // uygulamanın sürümüyle birlikte yenilenir.
    if let Some(resources) = resource_dir {
        candidates.push(resources.join("kits").join("app"));
    }
    candidates.push(data_dir.join("app"));
    // Geliştirme derlemesinde Fusion deposunun yanındaki çalışma kopyası.
    if cfg!(debug_assertions) {
        candidates.push(Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../fusion-kits"));
    }
    candidates
}

fn find_kits_dir(candidates: &[PathBuf]) -> Result<PathBuf, String> {
    candidates
        .iter()
        .find(|dir| dir.join(SERVER_ENTRY).is_file())
        .cloned()
        .ok_or_else(|| {
            "Bu Fusion paketinde Kits bileşeni bulunamadı. Kits içeren Fusion paketini yükleyip yeniden dene."
                .to_string()
        })
}

fn node_candidates(home: &Path, resource_dir: Option<&Path>) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = developer_override("FUSION_KITS_NODE") {
        candidates.push(PathBuf::from(explicit));
    }
    // Uygulamayla birlikte gelen Node: kullanıcının makinesinde Node kurulu olmayabilir.
    if let Some(resources) = resource_dir {
        candidates.push(resources.join("kits").join(node_name()));
    }
    if let Some(path) = std::env::var_os("PATH") {
        candidates.extend(std::env::split_paths(&path).map(|dir| dir.join(node_name())));
    }
    // GUI uygulamaları kabuğun PATH'ini görmez; yaygın kurulum yerleri ayrıca denenir.
    for dir in ["/opt/homebrew/bin", "/usr/local/bin"] {
        candidates.push(Path::new(dir).join(node_name()));
    }
    candidates.push(home.join(".local/bin").join(node_name()));
    // `npm run kits:start` Node 24'ü npx önbelleğine indirir.
    if let Ok(entries) = std::fs::read_dir(home.join(".npm/_npx")) {
        candidates.extend(
            entries
                .flatten()
                .map(|entry| entry.path().join("node_modules/.bin").join(node_name())),
        );
    }
    candidates
}

fn node_name() -> &'static str {
    if cfg!(windows) {
        "node.exe"
    } else {
        "node"
    }
}

impl KitsManager {
    fn find_node(&self, candidates: &[PathBuf]) -> Result<PathBuf, String> {
        for path in candidates {
            if self.stopping.load(Ordering::SeqCst) {
                return Err("Uygulama kapanıyor; Node yoklaması iptal edildi.".into());
            }
            if path.is_file()
                && self
                    .node_major_within(path, NODE_PROBE_TIMEOUT)
                    .is_some_and(|major| major >= MIN_NODE_MAJOR)
            {
                if self.stopping.load(Ordering::SeqCst) {
                    return Err("Uygulama kapanıyor; Node yoklaması iptal edildi.".into());
                }
                return Ok(path.clone());
            }
        }
        if self.stopping.load(Ordering::SeqCst) {
            return Err("Uygulama kapanıyor; Node yoklaması iptal edildi.".into());
        }
        Err(format!(
            "Node.js {MIN_NODE_MAJOR} veya üzeri bulunamadı. Kits bunu gerektirir."
        ))
    }

    fn node_major_within(&self, node: &Path, timeout: Duration) -> Option<u32> {
        // A regular anonymous file avoids a blocking pipe read if the probe
        // exits while a descendant still holds stdout. Only a short version is read.
        let mut output = tempfile::tempfile().ok()?;
        let mut command = Command::new(node);
        command
            .arg("--version")
            .stdin(Stdio::null())
            .stdout(Stdio::from(output.try_clone().ok()?))
            .stderr(Stdio::null());
        crate::core_process::kendi_grubunda(&mut command);
        {
            let mut slot = self.probe.lock().ok()?;
            // Admission and publication serialize with stop, as for the server.
            if self.stopping.load(Ordering::SeqCst) {
                return None;
            }
            *slot = Some(
                crate::core_process::pencere_acmadan(&mut command)
                    .spawn()
                    .ok()?,
            );
        }
        let deadline = Instant::now() + timeout;
        loop {
            let mut slot = self.probe.lock().ok()?;
            let child = slot.as_mut()?;
            let exited = child_exited(child);
            if matches!(exited, Ok(true)) && !self.stopping.load(Ordering::SeqCst) {
                let mut child = slot.take()?;
                terminate_gracefully(&mut child);
                break;
            }
            if !matches!(exited, Ok(false))
                || Instant::now() >= deadline
                || self.stopping.load(Ordering::SeqCst)
            {
                let mut child = slot.take()?;
                terminate_gracefully(&mut child);
                return None;
            }
            drop(slot);
            std::thread::sleep(Duration::from_millis(20));
        }
        output.seek(SeekFrom::Start(0)).ok()?;
        let mut version = String::new();
        output.take(256).read_to_string(&mut version).ok()?;
        parse_node_major(&version)
    }
}

fn parse_node_major(version: &str) -> Option<u32> {
    version
        .trim()
        .strip_prefix('v')?
        .split('.')
        .next()?
        .parse()
        .ok()
}

#[cfg(all(test, unix))]
pub(crate) mod test_support {
    use super::*;
    use std::io::{BufRead, BufReader};
    use std::sync::Arc;

    /// Only this fixture's shell and its child are signalled; no process lookup.
    pub(crate) struct OwnedKitsFixture {
        pub(crate) manager: Arc<KitsManager>,
        descendant: i32,
    }

    impl OwnedKitsFixture {
        pub(crate) fn new(manager: Arc<KitsManager>) -> Self {
            Self::with_script(manager, "trap 'kill \"$runtime_pid\"; wait \"$runtime_pid\"; exit 0' TERM; sleep 30 & runtime_pid=$!; echo $runtime_pid; wait $runtime_pid")
        }

        pub(crate) fn with_script(manager: Arc<KitsManager>, script: &str) -> Self {
            let mut command = Command::new("/bin/sh");
            command
                .args(["-c", script])
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .stderr(Stdio::null());
            let mut child = crate::core_process::kendi_grubunda(&mut command)
                .spawn()
                .expect("owned Kits fixture starts");
            let mut line = String::new();
            BufReader::new(child.stdout.take().unwrap())
                .read_line(&mut line)
                .expect("fixture child ready");
            let descendant = line.trim().parse().expect("fixture descendant PID");
            *manager.running.lock().unwrap() = Some(Running {
                child,
                url: "http://127.0.0.1:1".into(),
            });
            Self {
                manager,
                descendant,
            }
        }

        pub(crate) fn is_running(&self) -> bool {
            self.manager
                .running
                .lock()
                .unwrap()
                .as_mut()
                .is_some_and(|running| matches!(child_exited(&mut running.child), Ok(false)))
        }

        pub(crate) fn descendant_alive(&self) -> bool {
            // SAFETY: signal 0 observes the PID published by this fixture only.
            unsafe { libc::kill(self.descendant, 0) == 0 }
        }
    }

    impl Drop for OwnedKitsFixture {
        fn drop(&mut self) {
            self.manager.stop();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    #[test]
    fn stop_during_version_probe_cleans_owned_probe_and_descendant_before_return() {
        use std::{os::unix::fs::PermissionsExt, sync::Arc};
        let temp = tempfile::tempdir().unwrap();
        let resources = temp.path().join("resources");
        let entry = resources.join("kits/app").join(SERVER_ENTRY);
        std::fs::create_dir_all(entry.parent().unwrap()).unwrap();
        std::fs::write(entry, "fixture").unwrap();
        let marker = temp.path().join("version-probe.pids");
        let node = resources.join("kits/node");
        let quoted_marker = marker.to_string_lossy().replace('\'', "'\\''");
        std::fs::write(&node, format!("#!/bin/sh\nif [ \"$1\" = --version ]; then sleep 2 & runtime_pid=$!; echo $$ $runtime_pid > '{quoted_marker}'; wait $runtime_pid; echo v24.0.0; exit 0; fi\nexit 3\n")).unwrap();
        std::fs::set_permissions(&node, std::fs::Permissions::from_mode(0o755)).unwrap();
        let home = temp.path().join("home");
        let data = temp.path().join("data");
        let manager = Arc::new(KitsManager::new());
        let sentinel = test_support::OwnedKitsFixture::new(Arc::new(KitsManager::new()));
        let starter = manager.clone();
        let worker = std::thread::spawn(move || {
            starter.ensure_started(&home, &data, Some(&resources), Path::new("/unused-core"))
        });
        let deadline = Instant::now() + Duration::from_secs(2);
        while !marker.exists() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(5));
        }
        let pids: Vec<i32> = std::fs::read_to_string(marker)
            .unwrap()
            .split_whitespace()
            .map(|v| v.parse().unwrap())
            .collect();
        assert_eq!(pids.len(), 2);
        let started = Instant::now();
        manager.stop();
        let survivors: Vec<bool> = pids
            .iter()
            .map(|pid| unsafe { libc::kill(*pid, 0) == 0 })
            .collect();
        let elapsed = started.elapsed();
        // Join before asserting so the old buggy probe self-expires on RED.
        assert!(worker.join().unwrap().unwrap_err().contains("kapanıyor"));
        assert!(
            survivors.iter().all(|alive| !alive),
            "stop returned while owned version probe or descendant was alive: {survivors:?}"
        );
        assert!(elapsed < Duration::from_secs(3));
        assert!(sentinel.is_running());
        assert!(sentinel.descendant_alive());
        let later_marker = temp.path().join("later-probe-ran");
        let later_node = temp.path().join("later-node");
        let quoted_marker = later_marker.to_string_lossy().replace('\'', "'\\''");
        std::fs::write(
            &later_node,
            format!("#!/bin/sh\necho ran > '{quoted_marker}'\necho v24.0.0\n"),
        )
        .unwrap();
        std::fs::set_permissions(&later_node, std::fs::Permissions::from_mode(0o755)).unwrap();
        assert!(manager
            .find_node(&[later_node])
            .unwrap_err()
            .contains("kapanıyor"));
        assert!(!later_marker.exists(), "a new probe started after stop");
    }

    #[cfg(unix)]
    #[test]
    #[ignore = "Only the owning readiness lifecycle test starts this child"]
    fn owned_node_fixture_server() {
        let port: u16 = std::env::var("PORT").unwrap().parse().unwrap();
        let listener = TcpListener::bind(("127.0.0.1", port)).unwrap();
        let mut child = Command::new("sleep").arg("30").spawn().unwrap();
        let marker = format!("{}.child", std::env::var("DATABASE_PATH").unwrap());
        std::fs::write(marker, child.id().to_string()).unwrap();
        println!(
            "{}",
            serde_json::json!({
                "fusion_kits_ready": 1,
                "nonce": std::env::var("KITS_DESKTOP_READY_NONCE").unwrap(),
                "pid": std::process::id(), "port": port
            })
        );
        listener.set_nonblocking(true).unwrap();
        let deadline = Instant::now() + Duration::from_secs(30);
        while Instant::now() < deadline {
            let _ = listener.accept();
            std::thread::sleep(Duration::from_millis(10));
        }
        let _ = child.kill();
        let _ = child.wait();
    }

    #[cfg(unix)]
    #[test]
    fn ready_owned_server_is_reused_then_group_stopped_and_reaped() {
        use std::os::unix::fs::PermissionsExt;
        let temp = tempfile::tempdir().unwrap();
        let resources = temp.path().join("resources");
        let entry = resources.join("kits/app").join(SERVER_ENTRY);
        std::fs::create_dir_all(entry.parent().unwrap()).unwrap();
        std::fs::write(entry, "fixture").unwrap();
        let node = resources.join("kits/node");
        let executable = std::env::current_exe()
            .unwrap()
            .to_string_lossy()
            .replace('\'', "'\\''");
        std::fs::write(&node, format!("#!/bin/sh\nif [ \"$1\" = --version ]; then echo v24.0.0; exit 0; fi\nexec '{executable}' --ignored --exact kits_process::tests::owned_node_fixture_server --nocapture\n")).unwrap();
        std::fs::set_permissions(&node, std::fs::Permissions::from_mode(0o755)).unwrap();
        let manager = KitsManager::new();
        let home = temp.path().join("home");
        let data = temp.path().join("data");
        let first = manager
            .ensure_started(&home, &data, Some(&resources), Path::new("/unused-core"))
            .unwrap();
        let leader = manager.running.lock().unwrap().as_ref().unwrap().child.id();
        assert_eq!(
            manager
                .ensure_started(&home, &data, Some(&resources), Path::new("/unused-core"))
                .unwrap(),
            first
        );
        assert_eq!(
            manager.running.lock().unwrap().as_ref().unwrap().child.id(),
            leader
        );
        let descendant: i32 = std::fs::read_to_string(data.join("fusion-kits.sqlite.child"))
            .unwrap()
            .parse()
            .unwrap();
        manager.stop();
        manager.stop();
        let deadline = Instant::now() + Duration::from_millis(300);
        while unsafe { libc::kill(descendant, 0) == 0 } && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        assert!(manager.running.lock().unwrap().is_none());
        assert_ne!(unsafe { libc::kill(descendant, 0) }, 0);
        // waitpid must report ECHILD: production stop already reaped the leader.
        assert_eq!(
            unsafe { libc::waitpid(leader as i32, std::ptr::null_mut(), libc::WNOHANG) },
            -1
        );
        assert_eq!(
            std::io::Error::last_os_error().raw_os_error(),
            Some(libc::ECHILD)
        );
    }

    #[cfg(unix)]
    #[test]
    fn owned_kits_stop_cleans_descendant_after_leader_exits_or_ignores_term() {
        use std::sync::Arc;
        for trap in ["trap 'exit 0' TERM", "trap '' TERM"] {
            let manager = Arc::new(KitsManager::new());
            // The descendant ignores TERM but self-expires, even with the old buggy cleanup.
            let fixture = test_support::OwnedKitsFixture::with_script(manager.clone(), &format!(
                "{trap}; /bin/sh -c 'trap \"\" TERM; echo $$; exec sleep 3' & runtime_pid=$!; wait $runtime_pid"
            ));
            let started = Instant::now();
            manager.stop();
            manager.stop();
            let deadline = Instant::now() + Duration::from_millis(300);
            while fixture.descendant_alive() && Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(10));
            }
            let survivor = fixture.descendant_alive();
            // Let the deliberately self-expiring child finish before a failing assertion.
            if survivor {
                std::thread::sleep(Duration::from_secs(4));
            }
            assert!(!survivor, "owned runtime survived Kits stop ({trap})");
            assert!(!fixture.is_running());
            assert!(started.elapsed() < Duration::from_secs(3));
        }
    }

    #[cfg(unix)]
    #[test]
    fn startup_cancellation_cleans_owned_descendant_before_readiness() {
        use std::{os::unix::fs::PermissionsExt, sync::Arc};
        assert!(
            developer_override("FUSION_KITS_DIR").is_none(),
            "test needs no developer Kits override"
        );
        assert!(
            developer_override("FUSION_KITS_NODE").is_none(),
            "test needs no developer Node override"
        );
        let temp = tempfile::tempdir().unwrap();
        let resources = temp.path().join("resources");
        let entry = resources.join("kits/app").join(SERVER_ENTRY);
        std::fs::create_dir_all(entry.parent().unwrap()).unwrap();
        std::fs::write(entry, "fixture").unwrap();
        let node = resources.join("kits/node");
        // No TERM handler or readiness receipt: the same early-startup window as
        // the packaged Node server while it awaits its gateway runtime.
        std::fs::write(&node, "#!/bin/sh\nif [ \"$1\" = --version ]; then echo v24.0.0; exit 0; fi\nsleep 3 & runtime_pid=$!\necho $runtime_pid > \"$DATABASE_PATH.child\"\nwait $runtime_pid\n").unwrap();
        std::fs::set_permissions(&node, std::fs::Permissions::from_mode(0o755)).unwrap();
        let home = temp.path().join("home");
        let data = temp.path().join("data");
        let marker = data.join("fusion-kits.sqlite.child");
        let manager = Arc::new(KitsManager::new());
        let worker_manager = manager.clone();
        let worker = std::thread::spawn(move || {
            worker_manager.ensure_started(&home, &data, Some(&resources), Path::new("/unused-core"))
        });
        let deadline = Instant::now() + Duration::from_secs(2);
        while !marker.exists() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(5));
        }
        let started = Instant::now();
        let pid: i32 = std::fs::read_to_string(&marker)
            .unwrap()
            .trim()
            .parse()
            .unwrap();
        manager.stop();
        let pending_when_stop_returned = unsafe { libc::kill(pid, 0) == 0 };
        assert!(worker.join().unwrap().unwrap_err().contains("kapanıyor"));
        let deadline = Instant::now() + Duration::from_millis(300);
        // SAFETY: signal 0 observes only the descendant published by our fixture.
        while unsafe { libc::kill(pid, 0) == 0 } && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        let survivor = unsafe { libc::kill(pid, 0) == 0 };
        if survivor {
            std::thread::sleep(Duration::from_secs(4));
        }
        assert!(
            !survivor,
            "startup cancellation left its owned runtime alive"
        );
        assert!(started.elapsed() < Duration::from_secs(3));
        assert!(
            !pending_when_stop_returned,
            "stop returned while startup cleanup still needed its background worker"
        );
        manager.stop();
    }

    #[cfg(unix)]
    #[test]
    fn readiness_timeout_keeps_child_owned_until_group_cleanup_and_reap() {
        use std::sync::Arc;
        let manager = Arc::new(KitsManager::new());
        let fixture = test_support::OwnedKitsFixture::new(manager.clone());
        let temp = tempfile::tempdir().unwrap();
        let log = temp.path().join("empty.log");
        std::fs::write(&log, "").unwrap();
        let result = {
            let mut slot = manager.running.lock().unwrap();
            wait_ready_owned(
                &mut slot.as_mut().unwrap().child,
                free_port().unwrap(),
                Duration::from_millis(30),
                &log,
                "fixture",
                &AtomicBool::new(false),
            )
        };
        assert!(result.unwrap_err().contains("zamanında"));
        manager.stop();
        manager.stop();
        assert!(!fixture.is_running());
        assert!(!fixture.descendant_alive());
    }

    #[test]
    fn kits_veri_klasoru_python_ile_ayni_kurali_izler() {
        let home = Path::new("/Users/ali");
        assert_eq!(
            kits_data_dir(home, None, None),
            PathBuf::from("/Users/ali/.local/share/fusion-cli/kits")
        );
        assert_eq!(
            kits_data_dir(home, Some("/tmp/xdg"), None),
            PathBuf::from("/tmp/xdg/fusion-cli/kits")
        );
        // Boş XDG değeri ayarsız sayılır (Python `os.environ.get(...) or` ile aynı).
        assert_eq!(
            kits_data_dir(home, Some("  "), None),
            PathBuf::from("/Users/ali/.local/share/fusion-cli/kits")
        );
        assert_eq!(
            kits_data_dir(home, Some("/tmp/xdg"), Some(Path::new("C:\\Local"))),
            PathBuf::from("C:\\Local").join("fusion-cli").join("kits")
        );
    }

    #[test]
    fn node_surumu_ana_numarasi_ayristirilir() {
        assert_eq!(parse_node_major("v24.21.0\n"), Some(24));
        assert_eq!(parse_node_major("v22.23.1"), Some(22));
        assert_eq!(parse_node_major("24.1.0"), None);
        assert_eq!(parse_node_major(""), None);
    }

    #[test]
    fn derlenmemis_klasor_atlanir_ilk_derlenmis_secilir() {
        let bos = tempfile::tempdir().unwrap();
        let hazir = tempfile::tempdir().unwrap();
        let giris = hazir.path().join(SERVER_ENTRY);
        std::fs::create_dir_all(giris.parent().unwrap()).unwrap();
        std::fs::write(&giris, "").unwrap();

        let secilen =
            find_kits_dir(&[bos.path().to_path_buf(), hazir.path().to_path_buf()]).unwrap();

        assert_eq!(secilen, hazir.path());
        assert!(find_kits_dir(&[bos.path().to_path_buf()])
            .unwrap_err()
            .contains("Kits bileşeni bulunamadı"));
    }

    #[test]
    fn olmayan_node_adaylari_hata_verir() {
        let hata = KitsManager::new()
            .find_node(&[PathBuf::from("/yok/node")])
            .unwrap_err();
        assert!(hata.contains("Node.js 24"));
    }

    #[test]
    fn port_rezervasyonu_acikken_baska_listener_baglanamaz() {
        let listener = reserve_port().unwrap();
        let address = listener.local_addr().unwrap();
        assert!(address.ip().is_loopback());
        assert_ne!(address.port(), 0);
        assert_eq!(
            TcpListener::bind(address).unwrap_err().kind(),
            std::io::ErrorKind::AddrInUse
        );
    }

    #[test]
    fn erken_kapanan_surec_hazir_sayilmaz() {
        let mut child = Command::new(std::env::current_exe().unwrap())
            .arg("--version-yok-boyle-bir-test")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let port = free_port().unwrap();
        let temp = tempfile::tempdir().unwrap();
        let hata = wait_ready_owned(
            &mut child,
            port,
            Duration::from_secs(10),
            &temp.path().join("kits.log"),
            "test-nonce",
            &AtomicBool::new(false),
        )
        .unwrap_err();
        let _ = child.wait();
        assert!(hata.contains("Fusion Kits başlatılamadı"));
    }

    #[test]
    fn hazirlik_yoklamasi_kisa_baslar_ve_ust_sinirda_kalir() {
        let mut poll = READY_POLL_FIRST;
        let mut seen = vec![poll];
        for _ in 0..6 {
            poll = next_poll(poll);
            seen.push(poll);
        }
        let ms: Vec<u128> = seen.iter().map(Duration::as_millis).collect();
        assert_eq!(ms, vec![10, 20, 40, 80, 100, 100, 100]);
    }

    #[test]
    fn host_origin_listesi_gecerli_json_dizisidir() {
        let origins: Vec<String> = serde_json::from_str(HOST_ORIGINS).unwrap();
        assert!(origins.contains(&"tauri://localhost".to_string()));
        assert!(origins
            .iter()
            .all(|origin| !origin.contains('*') && !origin.contains('?')));
    }
    #[test]
    fn hazirlik_makbuzu_nonce_pid_port_sahibine_baglidir() {
        let receipt = r#"{"fusion_kits_ready":1,"nonce":"test-nonce","pid":123,"port":4411}"#;
        assert!(ready_receipt_matches(receipt, "test-nonce", 123, 4411));
        assert!(!ready_receipt_matches(receipt, "other", 123, 4411));
        assert!(!ready_receipt_matches(receipt, "test-nonce", 124, 4411));
        assert!(!ready_receipt_matches(receipt, "test-nonce", 123, 4412));
        assert!(!ready_receipt_matches("{}", "test-nonce", 123, 4411));
    }

    #[test]
    #[ignore = "Yalnız sahiplik testinin açıkça başlattığı çocuk süreç"]
    fn hazirlik_cocuk_bekleyici() {
        std::thread::sleep(Duration::from_secs(10));
    }

    #[test]
    fn baska_tcp_dinleyicisi_kits_hazirligi_sayilmaz() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let temp = tempfile::tempdir().unwrap();
        let log = temp.path().join("kits.log");
        std::fs::write(&log, b"").unwrap();
        let mut child = Command::new(std::env::current_exe().unwrap())
            .args([
                "--ignored",
                "--exact",
                "kits_process::tests::hazirlik_cocuk_bekleyici",
            ])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let result = wait_ready_owned(
            &mut child,
            port,
            Duration::from_millis(300),
            &log,
            "test-nonce",
            &AtomicBool::new(false),
        );
        let _ = child.kill();
        let _ = child.wait();
        assert!(
            result.is_err(),
            "Başka TCP sunucusu Kits olarak kabul edildi"
        );
    }
    #[test]
    fn yarim_utf8_gunluk_hazirlik_kontrolunu_bozmaz() {
        let temp = tempfile::tempdir().unwrap();
        let log = temp.path().join("kits.log");
        std::fs::write(&log, [b'b', 0xc3]).unwrap();
        assert_eq!(readiness_logged(&log, "test", 123, 4411), Ok(false));
        let mut data = vec![255u8, 10u8];
        data.extend_from_slice(br#"{"fusion_kits_ready":1,"nonce":"test","pid":123,"port":4411}"#);
        data.push(10);
        std::fs::write(&log, data).unwrap();
        assert_eq!(readiness_logged(&log, "test", 123, 4411), Ok(true));
    }

    #[test]
    fn buyuk_gunluk_hazir_sureci_dusurmez_makbuz_kuyrukta_bulunur() {
        // Ölçüldü (30 Ekim): 256 KB'ı aşan günlük 'boyut sınırını aştı' hatasıyla başlatmayı iptal ediyordu.
        let temp = tempfile::tempdir().unwrap();
        let log = temp.path().join("kits.log");
        let mut data = vec![b'x'; 600 * 1024];
        data.push(b'\n');
        data.extend_from_slice(br#"{"fusion_kits_ready":1,"nonce":"test","pid":123,"port":4411}"#);
        data.push(b'\n');
        std::fs::write(&log, &data).unwrap();
        assert_eq!(readiness_logged(&log, "test", 123, 4411), Ok(true));
        assert_eq!(readiness_logged(&log, "baska", 123, 4411), Ok(false));
    }

    #[test]
    fn kesilen_ilk_satir_kuyruk_okumasinda_atilir() {
        let temp = tempfile::tempdir().unwrap();
        let log = temp.path().join("kits.log");
        // Makbuzun yarısı kuyruk sınırının dışında kalır: yarım satır makbuz sayılmaz.
        let mut data = br#"{"fusion_kits_ready":1,"nonce":"test","pid":123,"port":4411}"#.to_vec();
        data.push(b'\n');
        data.extend(std::iter::repeat_n(b'y', 300 * 1024));
        data.push(b'\n');
        std::fs::write(&log, &data).unwrap();
        assert_eq!(readiness_logged(&log, "test", 123, 4411), Ok(false));
    }

    #[test]
    fn kapanis_istenince_hazirlik_beklemesi_hemen_birakilir() {
        let temp = tempfile::tempdir().unwrap();
        let log = temp.path().join("kits.log");
        std::fs::write(&log, b"").unwrap();
        let mut child = Command::new(std::env::current_exe().unwrap())
            .args([
                "--ignored",
                "--exact",
                "kits_process::tests::hazirlik_cocuk_bekleyici",
            ])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        let baslangic = Instant::now();
        let sonuc = wait_ready_owned(
            &mut child,
            free_port().unwrap(),
            Duration::from_secs(30),
            &log,
            "test-nonce",
            &AtomicBool::new(true),
        );
        let _ = child.kill();
        let _ = child.wait();
        assert!(sonuc.unwrap_err().contains("kapanıyor"));
        assert!(baslangic.elapsed() < Duration::from_secs(2));
    }

    #[cfg(unix)]
    #[test]
    fn takilan_node_adayi_zaman_asiminda_atlanir() {
        // Ölçüldü (30 Ekim): `node --version` zaman aşımsızdı; takılan aday başlatmayı bloklardı.
        use std::os::unix::fs::PermissionsExt;
        let temp = tempfile::tempdir().unwrap();
        let betik = temp.path().join("node");
        std::fs::write(&betik, "#!/bin/sh\nexec sleep 30\n").unwrap();
        std::fs::set_permissions(&betik, std::fs::Permissions::from_mode(0o755)).unwrap();
        let baslangic = Instant::now();
        assert_eq!(
            KitsManager::new().node_major_within(&betik, Duration::from_millis(300)),
            None
        );
        assert!(baslangic.elapsed() < Duration::from_secs(5));
    }

    #[test]
    fn durdurma_baslatmadan_once_istenmisse_baslatma_reddedilir() {
        let yonetici = KitsManager::new();
        yonetici.stop();
        let temp = tempfile::tempdir().unwrap();
        let hata = yonetici
            .ensure_started(temp.path(), temp.path(), None, Path::new("/yok"))
            .unwrap_err();
        assert!(hata.contains("kapanıyor"));
    }
}
