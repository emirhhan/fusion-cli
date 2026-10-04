//! Fusion Kits yan süreci: bağımsız Node sunucusunu uygulamanın çocuğu olarak
//! başlatır, hazır olmasını bekler ve uygulama kapanırken durdurur.
//!
//! Kits ayrı bir modüldür (bkz. `fusion-kits/handoff/BIRLESTIRME.md`); arayüz onu
//! iframe ile gömer. Bu modül yalnız süreç sahipliğini taşır: Kits'in kendi
//! owner token'ı, veritabanı ve `.env` ayarı Kits'e aittir, buradan okunmaz.

use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Serialize;

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
    pub fn ensure_started(&self, home: &Path, data_dir: &Path) -> Result<KitsStatus, String> {
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
        let kits_dir = find_kits_dir(&kits_dir_candidates(data_dir))?;
        let node = find_node(&node_candidates(home))?;
        let port = free_port()?;
        std::fs::create_dir_all(data_dir)
            .map_err(|error| format!("Kits veri klasörü oluşturulamadı: {error}"))?;
        let mut command = Command::new(node);
        command
            .args(["--env-file-if-exists=.env", SERVER_ENTRY])
            .current_dir(&kits_dir)
            .env("HOST", "127.0.0.1")
            .env("PORT", port.to_string())
            .env("DATABASE_PATH", data_dir.join("fusion-kits.sqlite"))
            .env("OWNER_ID", "fusion-kits-owner")
            .env("COMPUTER_NAMESPACE", "fusion-kits")
            .env("KITS_HOST_ORIGINS", HOST_ORIGINS)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        let mut child = crate::core_process::pencere_acmadan(&mut command)
            .spawn()
            .map_err(|error| format!("Kits sunucusu başlatılamadı: {error}"))?;
        if let Err(error) = wait_ready(&mut child, port, READY_TIMEOUT) {
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

fn wait_ready(child: &mut Child, port: u16, timeout: Duration) -> Result<(), String> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!(
                "Kits sunucusu açılırken kapandı ({status}). Kits klasöründe `npm run kits:doctor` çalıştır."
            ));
        }
        if TcpStream::connect_timeout(&address, READY_POLL).is_ok() {
            return Ok(());
        }
        std::thread::sleep(READY_POLL);
    }
    Err("Kits sunucusu zamanında hazır olmadı.".to_string())
}

fn free_port() -> Result<u16, String> {
    TcpListener::bind(("127.0.0.1", 0))
        .and_then(|listener| listener.local_addr())
        .map(|address| address.port())
        .map_err(|error| format!("Kits için boş port bulunamadı: {error}"))
}

/// Aranan sıra: açık ayar → uygulama verisine kurulmuş kopya (`<veri>/app`) →
/// geliştirici düzeni (Fusion deposunun yanındaki `fusion-kits`).
fn kits_dir_candidates(data_dir: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = std::env::var_os("FUSION_KITS_DIR") {
        candidates.push(PathBuf::from(explicit));
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
            "Fusion Kits kurulu değil ya da derlenmemiş. Kits klasöründe `npm run kits:start` ile bir kez derle."
                .to_string()
        })
}

fn node_candidates(home: &Path) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = std::env::var_os("FUSION_KITS_NODE") {
        candidates.push(PathBuf::from(explicit));
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
            .contains("derlenmemiş"));
    }

    #[test]
    fn olmayan_node_adaylari_hata_verir() {
        let hata = find_node(&[PathBuf::from("/yok/node")]).unwrap_err();
        assert!(hata.contains("Node.js 24"));
    }

    #[test]
    fn bos_port_gercekten_baglanabilir() {
        let port = free_port().unwrap();
        assert!(TcpListener::bind(("127.0.0.1", port)).is_ok());
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
        let hata = wait_ready(&mut child, port, Duration::from_secs(10)).unwrap_err();
        let _ = child.wait();
        assert!(hata.contains("kapandı"));
    }

    #[test]
    fn host_origin_listesi_gecerli_json_dizisidir() {
        let origins: Vec<String> = serde_json::from_str(HOST_ORIGINS).unwrap();
        assert!(origins.contains(&"tauri://localhost".to_string()));
        assert!(origins
            .iter()
            .all(|origin| !origin.contains('*') && !origin.contains('?')));
    }
}
