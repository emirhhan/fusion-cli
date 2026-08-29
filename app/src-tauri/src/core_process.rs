//! Fusion çekirdeğini alt süreç olarak yönetir ve stdio satırlarını aktarır.
//!
//! Burada ürün mantığı YOKTUR: süreç bulunur, başlatılır, satırlar iki yöne
//! taşınır. Karar veren taraf her zaman arayüzdür.

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};

/// `stop()` çekirdeğin stdin EOF'una tepki verip düzgün çıkması için bu kadar
/// bekler. Pencere kapanış olayı ana döngüde senkron çalıştığından kullanıcıyı
/// uzun süre bekletmemek adına kısa tutulur; süre aşılırsa `kill()` ile
/// zorla sonlandırılır.
const DURDURMA_ZAMAN_ASIMI: Duration = Duration::from_millis(2000);

/// Bekleme sırasında sürecin çıkış yapıp yapmadığını denetleme aralığı.
const YOKLAMA_ARALIGI: Duration = Duration::from_millis(50);

/// Çekirdek hiçbir adayda bulunamazsa kullanıcıya gösterilecek, eyleme dönük
/// tek mesaj. `ui` katmanı olmadığından metin burada sabit durur.
const KURULUM_MESAJI: &str = "Fusion CLI bulunamadı. Devam etmeden önce Fusion CLI'ın kurulu \
     olması gerekir: kurulum belgelerini izleyip `fusion` komutunun çalıştırılabilir \
     olduğundan emin olun.";

pub struct CoreProcess {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
}

impl CoreProcess {
    pub fn new() -> Self {
        Self { child: Mutex::new(None), stdin: Mutex::new(None) }
    }

    /// Çekirdeği başlat. Zaten çalışan bir süreç varsa yenisini AÇMAZ:
    /// `React.StrictMode` dev modunda `useEffect`i mount→unmount→mount olarak
    /// iki kez çalıştırdığından bu komut iki kez çağrılabilir. İkinci çağrıda
    /// yeni bir süreç açmak eskisini yetim bırakır ve iki stdout okuma
    /// thread'i aynı global "cekirdek-satir" olayına yazıp istek kimliklerini
    /// karıştırır. Var olan süreci kullanmaya devam etmek güvenlidir; arayüz
    /// tarafı (App.tsx) ikinci mount'ta zaten eski dinleyicisini bırakır.
    ///
    /// `child` kilidi denetim + fork boyunca AÇIK TUTULUR (tek bir kilitleme
    /// bloğu): aksi halde "hâlâ çalışıyor mu" kontrolü ile sürecin
    /// kaydedilmesi arasında iki eşzamanlı çağrı (yine StrictMode'un çok
    /// hızlı ardışık iki çağrısı) birbirini görmeden ikisi de spawn
    /// edebilir — kontrol+kayıt atomik olmalı.
    pub fn start(&self, app: AppHandle) -> Result<(), String> {
        let mut cocuk_kilit = self.child.lock().unwrap();
        if let Some(cocuk) = cocuk_kilit.as_mut() {
            if matches!(cocuk.try_wait(), Ok(None)) {
                return Ok(());
            }
        }

        let ev_dizini = std::env::var("HOME").ok().map(PathBuf::from);
        let path_degiskeni = std::env::var("PATH").ok();
        let yol = cekirdek_yolunu_bul(
            sidecar_yolu(&app).as_deref(),
            ev_dizini.as_deref(),
            path_degiskeni.as_deref(),
            &dosya_calistirilabilir_mi,
        )
        .ok_or_else(|| KURULUM_MESAJI.to_string())?;

        let mut cocuk = Command::new(yol)
            .arg("app")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("çekirdek başlatılamadı: {e}"))?;

        let cikti = cocuk.stdout.take().ok_or("çekirdek çıktısı alınamadı")?;
        *self.stdin.lock().unwrap() = cocuk.stdin.take();
        *cocuk_kilit = Some(cocuk);
        drop(cocuk_kilit);

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

    /// Pencere kapanınca çekirdeği sonlandır. stdin kapatılarak çekirdeğe
    /// düzgün çıkması için `DURDURMA_ZAMAN_ASIMI` kadar süre tanınır; bu süre
    /// içinde çıkmazsa `kill()` ile zorla sonlandırılır — aksi halde çekirdek
    /// EOF'a tepki vermediğinde uygulama kapanırken süresiz asılı kalırdı.
    pub fn stop(&self) {
        *self.stdin.lock().unwrap() = None; // stdin kapanır, çekirdek düzgün çıkmayı dener
        let Some(mut cocuk) = self.child.lock().unwrap().take() else {
            return;
        };

        let baslangic = Instant::now();
        loop {
            match cocuk.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) => {
                    if baslangic.elapsed() >= DURDURMA_ZAMAN_ASIMI {
                        let _ = cocuk.kill();
                        let _ = cocuk.wait();
                        return;
                    }
                    std::thread::sleep(YOKLAMA_ARALIGI);
                }
                Err(_) => return,
            }
        }
    }
}

/// Paketlenmiş sidecar ikilisinin yolu. Paketleme henüz kurulmadığından her
/// zaman `None` döner ve arama sessizce sonraki adaya geçer. Paketleme
/// eklendiğinde burada `app.path()` üzerinden gerçek sidecar yolu çözülecek.
fn sidecar_yolu(_app: &AppHandle) -> Option<PathBuf> {
    None
}

/// Bir yolun var olan ve çalıştırılabilir bir dosya olup olmadığını
/// denetler (Unix'te çalıştırma izni biti dâhil).
fn dosya_calistirilabilir_mi(yol: &Path) -> bool {
    let Ok(meta) = std::fs::metadata(yol) else {
        return false;
    };
    if !meta.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        meta.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        true
    }
}

/// Fusion çekirdeğinin ikili yolunu sırayla arar ve ilk bulunanı döner:
/// 1. Uygulamayla gelen sidecar
/// 2. `<ev>/.local/bin/fusion`
/// 3. `<ev>/.local/share/fusion-cli/venv/bin/fusion`
/// 4. `/opt/homebrew/bin/fusion`, `/usr/local/bin/fusion`
/// 5. `PATH` üzerinde `fusion`
///
/// Saf ve test edilebilir tutmak için dosya sistemine doğrudan bakmaz;
/// `calistirilabilir_mi` yüklemi enjekte edilir.
pub fn cekirdek_yolunu_bul(
    sidecar: Option<&Path>,
    ev_dizini: Option<&Path>,
    path_degiskeni: Option<&str>,
    calistirilabilir_mi: &dyn Fn(&Path) -> bool,
) -> Option<PathBuf> {
    if let Some(p) = sidecar {
        if calistirilabilir_mi(p) {
            return Some(p.to_path_buf());
        }
    }

    if let Some(ev) = ev_dizini {
        for goreli in [".local/bin/fusion", ".local/share/fusion-cli/venv/bin/fusion"] {
            let aday = ev.join(goreli);
            if calistirilabilir_mi(&aday) {
                return Some(aday);
            }
        }
    }

    for sabit in ["/opt/homebrew/bin/fusion", "/usr/local/bin/fusion"] {
        let aday = PathBuf::from(sabit);
        if calistirilabilir_mi(&aday) {
            return Some(aday);
        }
    }

    if let Some(path_str) = path_degiskeni {
        for dizin in std::env::split_paths(path_str) {
            let aday = dizin.join("fusion");
            if calistirilabilir_mi(&aday) {
                return Some(aday);
            }
        }
    }

    None
}

#[cfg(test)]
mod testler {
    use super::*;

    fn sahte_yuklem(var_olanlar: &'static [&'static str]) -> impl Fn(&Path) -> bool {
        move |yol: &Path| var_olanlar.contains(&yol.to_str().unwrap_or(""))
    }

    #[test]
    fn sidecar_varsa_once_o_kullanilir() {
        let sidecar = PathBuf::from("/sidecar/fusion");
        let mevcut = sahte_yuklem(&["/sidecar/fusion", "/home/user/.local/bin/fusion"]);
        let sonuc =
            cekirdek_yolunu_bul(Some(&sidecar), Some(Path::new("/home/user")), None, &mevcut);
        assert_eq!(sonuc, Some(sidecar));
    }

    #[test]
    fn sidecar_yoksa_ev_dizinindeki_local_bin_kullanilir() {
        let mevcut = sahte_yuklem(&["/home/user/.local/bin/fusion"]);
        let sonuc = cekirdek_yolunu_bul(None, Some(Path::new("/home/user")), None, &mevcut);
        assert_eq!(sonuc, Some(PathBuf::from("/home/user/.local/bin/fusion")));
    }

    #[test]
    fn local_bin_yoksa_venv_kullanilir() {
        let mevcut = sahte_yuklem(&["/home/user/.local/share/fusion-cli/venv/bin/fusion"]);
        let sonuc = cekirdek_yolunu_bul(None, Some(Path::new("/home/user")), None, &mevcut);
        assert_eq!(
            sonuc,
            Some(PathBuf::from("/home/user/.local/share/fusion-cli/venv/bin/fusion"))
        );
    }

    #[test]
    fn ev_ve_sabit_yollar_yoksa_path_uzerinden_bulunur() {
        let mevcut = sahte_yuklem(&["/opt/bin/fusion"]);
        let sonuc = cekirdek_yolunu_bul(None, None, Some("/usr/bin:/opt/bin"), &mevcut);
        assert_eq!(sonuc, Some(PathBuf::from("/opt/bin/fusion")));
    }

    #[test]
    fn hicbir_aday_bulunamazsa_none_doner() {
        let mevcut = sahte_yuklem(&[]);
        let sonuc = cekirdek_yolunu_bul(None, None, None, &mevcut);
        assert_eq!(sonuc, None);
    }

    #[test]
    fn sabit_kurulum_yollari_ev_dizininden_sonra_denenir() {
        let mevcut = sahte_yuklem(&["/opt/homebrew/bin/fusion"]);
        let sonuc = cekirdek_yolunu_bul(None, Some(Path::new("/home/user")), None, &mevcut);
        assert_eq!(sonuc, Some(PathBuf::from("/opt/homebrew/bin/fusion")));
    }
}
