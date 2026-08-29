//! Fusion çekirdeğini alt süreç olarak yönetir ve stdio satırlarını aktarır.
//!
//! Burada ürün mantığı YOKTUR: süreç bulunur, başlatılır, satırlar iki yöne
//! taşınır. Karar veren taraf her zaman arayüzdür.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter};

pub struct CoreProcess {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
}

impl CoreProcess {
    pub fn new() -> Self {
        Self { child: Mutex::new(None), stdin: Mutex::new(None) }
    }

    /// Çekirdeği başlat. Önce paketlenmiş sidecar, bulunamazsa sistemdeki
    /// `fusion` komutu denenir; ikisi de yoksa hata döner ve arayüz kurulum
    /// yönergesi gösterir.
    pub fn start(&self, app: AppHandle) -> Result<(), String> {
        let mut cocuk = Command::new("fusion")
            .arg("app")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("çekirdek başlatılamadı: {e}"))?;

        let cikti = cocuk.stdout.take().ok_or("çekirdek çıktısı alınamadı")?;
        *self.stdin.lock().unwrap() = cocuk.stdin.take();
        *self.child.lock().unwrap() = Some(cocuk);

        std::thread::spawn(move || {
            for satir in BufReader::new(cikti).lines() {
                match satir {
                    Ok(s) => {
                        let _ = app.emit("cekirdek-satir", s);
                    }
                    Err(_) => break,
                }
            }
            let _ = app.emit("cekirdek-kapandi", ());
        });
        Ok(())
    }

    /// Arayüzden gelen satırı çekirdeğe yaz.
    pub fn send(&self, satir: String) -> Result<(), String> {
        let mut kilit = self.stdin.lock().unwrap();
        let giris = kilit.as_mut().ok_or("çekirdek çalışmıyor")?;
        writeln!(giris, "{satir}").map_err(|e| format!("yazılamadı: {e}"))?;
        giris.flush().map_err(|e| format!("boşaltılamadı: {e}"))
    }

    /// Pencere kapanınca çekirdeği sonlandır.
    pub fn stop(&self) {
        *self.stdin.lock().unwrap() = None; // stdin kapanır, çekirdek düzgün çıkar
        if let Some(mut c) = self.child.lock().unwrap().take() {
            let _ = c.wait();
        }
    }
}
