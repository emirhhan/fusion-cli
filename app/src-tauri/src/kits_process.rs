//! Fusion Kits yan süreci: bağımsız Node sunucusunu uygulamanın çocuğu olarak
//! başlatır, hazır olmasını bekler ve uygulama kapanırken durdurur.
//!
//! Kits ayrı bir modüldür (bkz. `fusion-kits/handoff/BIRLESTIRME.md`); arayüz onu
//! iframe ile gömer. Bu modül yalnız süreç sahipliğini taşır: Kits'in kendi
//! owner token'ı, veritabanı ve `.env` ayarı Kits'e aittir, buradan okunmaz.

use std::io::Read;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
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
const READY_POLL: Duration = Duration::from_millis(150);
/// iframe'i gömebilecek origin'ler: paketli Tauri (macOS / Windows) ve geliştirme.
const HOST_ORIGINS: &str =
    r#"["tauri://localhost","http://tauri.localhost","http://localhost:1420"]"#;

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct KitsStatus {
    pub url: String,
}

const KITS_LOG_FILE: &str = "kits.log";

struct Running {
    child: Child,
    url: String,
}

#[derive(Default)]
pub struct KitsManager {
    running: Mutex<Option<Running>>,
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
        let mut slot = self
            .running
            .lock()
            .map_err(|_| "Kits süreç kilidi alınamadı.".to_string())?;
        if let Some(running) = slot.as_mut() {
            if matches!(running.child.try_wait(), Ok(None)) {
                return Ok(KitsStatus {
                    url: running.url.clone(),
                });
            }
            *slot = None;
        }
        let kits_dir = find_kits_dir(&kits_dir_candidates(data_dir, resource_dir))?;
        let node = find_node(&node_candidates(home, resource_dir))?;
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
            .stdin(Stdio::null())
            .stdout(log_sink(data_dir))
            .stderr(log_sink(data_dir));
        let mut child = crate::core_process::pencere_acmadan(&mut command)
            .spawn()
            .map_err(|error| format!("Kits sunucusu başlatılamadı: {error}"))?;
        if let Err(error) = wait_ready_owned(
            &mut child,
            port,
            READY_TIMEOUT,
            &data_dir.join(KITS_LOG_FILE),
            &nonce,
        ) {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
        let url = format!("http://127.0.0.1:{port}");
        *slot = Some(Running {
            child,
            url: url.clone(),
        });
        Ok(KitsStatus { url })
    }

    /// Uygulama kapanırken çağrılır. Kits SIGTERM'de kendi çocuklarını kapatır;
    /// süre dolarsa zorla sonlandırılır.
    pub fn stop(&self) {
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

fn terminate_gracefully(child: &mut Child) {
    #[cfg(unix)]
    {
        let _ = Command::new("kill")
            .args(["-TERM", &child.id().to_string()])
            .status();
        let deadline = Instant::now() + crate::core_process::DURDURMA_ZAMAN_ASIMI;
        while Instant::now() < deadline {
            if !matches!(child.try_wait(), Ok(None)) {
                return;
            }
            std::thread::sleep(crate::core_process::YOKLAMA_ARALIGI);
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
    let file = match std::fs::File::open(log) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(_) => return Err("Kits başlangıç kaydı açılamadı.".to_string()),
    };
    let mut bytes = Vec::new();
    file.take(256 * 1024 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "Kits başlangıç kaydı okunamadı.".to_string())?;
    if bytes.len() > 256 * 1024 {
        return Err("Kits başlangıç kaydı boyut sınırını aştı.".to_string());
    }
    // Yazılmakta olan son satır veya yarım UTF-8 sağlıklı çocuğu düşürmez.
    Ok(bytes.split_inclusive(|byte| *byte == b'\n').any(|line| {
        line.ends_with(b"\n")
            && std::str::from_utf8(line)
                .is_ok_and(|text| ready_receipt_matches(text.trim_end(), nonce, pid, port))
    }))
}

fn wait_ready_owned(
    child: &mut Child,
    port: u16,
    timeout: Duration,
    log: &Path,
    nonce: &str,
) -> Result<(), String> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(status)) => return Err(format!("Fusion Kits başlatılamadı ({status}). Yeniden dene; sorun sürerse Fusion uygulama paketini güncelle.")),
            Err(_) => return Err("Kits süreç durumu okunamadı.".to_string()),
            Ok(None) => {},
        }
        if readiness_logged(log, nonce, child.id(), port)?
            && TcpStream::connect_timeout(&address, READY_POLL).is_ok()
        {
            return match child.try_wait() {
                Ok(None) => Ok(()),
                _ => Err("Kits sunucusu hazır olurken kapandı.".to_string()),
            };
        }
        std::thread::sleep(READY_POLL);
    }
    Err("Kits bağlantısı zamanında doğrulanamadı. Uygulamayla birlikte gelen Kits paketini kullanıp yeniden dene.".to_string())
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

/// Aranan sıra: açık ayar → uygulamayla gelen paket → uygulama verisine kurulmuş
/// kopya (`<veri>/app`) → geliştirici düzeni (depo yanındaki `fusion-kits`).
fn kits_dir_candidates(data_dir: &Path, resource_dir: Option<&Path>) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = std::env::var_os("FUSION_KITS_DIR") {
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
    if let Some(explicit) = std::env::var_os("FUSION_KITS_NODE") {
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

fn find_node(candidates: &[PathBuf]) -> Result<PathBuf, String> {
    candidates
        .iter()
        .filter(|path| path.is_file())
        .find(|path| node_major(path).is_some_and(|major| major >= MIN_NODE_MAJOR))
        .cloned()
        .ok_or_else(|| {
            format!("Node.js {MIN_NODE_MAJOR} veya üzeri bulunamadı. Kits bunu gerektirir.")
        })
}

fn node_major(node: &Path) -> Option<u32> {
    let output = crate::core_process::pencere_acmadan(Command::new(node).arg("--version"))
        .stdin(Stdio::null())
        .output()
        .ok()?;
    parse_node_major(&String::from_utf8_lossy(&output.stdout))
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

#[cfg(test)]
mod tests {
    use super::*;

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
        let hata = find_node(&[PathBuf::from("/yok/node")]).unwrap_err();
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
        )
        .unwrap_err();
        let _ = child.wait();
        assert!(hata.contains("Fusion Kits başlatılamadı"));
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
}
