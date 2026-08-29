//! Fusion çekirdeğini alt süreç olarak yönetir ve stdio satırlarını aktarır.
//!
//! Burada ürün mantığı YOKTUR: süreç başlatılır, satırlar iki yöne taşınır.
//! Hangi ikilinin çalıştırılacağına karar veren taraf her zaman `RuntimeManager`
//! (bkz. `runtime_manager.rs`) — bu modül asla sistemdeki `fusion` komutuna,
//! `HOME` altındaki kurulumlara ya da `PATH`'e bakmaz. Sebep: kullanıcının
//! makinesindeki `fusion` başka bir sürüm, yarım kurulum ya da hiç olmayabilir;
//! sessiz bir geri düşüş teşhis edilemeyen hatalar üretir. Ayrıca GUI
//! uygulamaları minimal bir ortamla açılır (`launchctl getenv PATH` çoğu
//! zaman boştur), bu yüzden "sistemde kurulu" varsayımı zaten güvenilmez.
//! Geliştirici Kipi bu kuralın TEK istisnasıdır ve yalnız `lib.rs`'te,
//! açıkça istenmişse devreye girer.

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

pub struct CoreProcess {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
}

/// `start()`'ın çalıştıracağı komutun saf (yan etkisiz) tanımı. Testler
/// gerçek bir süreç açmadan bu değeri denetler.
#[derive(Debug, PartialEq)]
struct CoreLaunch {
    executable: PathBuf,
    args: Vec<String>,
}

/// Verilen çalışma zamanı ikilisi için başlatma komutunu üretir. Argüman
/// listesi sabittir: çekirdek her zaman uzun ömürlü, stdio üzerinden JSON
/// konuşan `app` alt komutuyla açılır.
fn core_launch(executable: &Path) -> CoreLaunch {
    CoreLaunch {
        executable: executable.to_path_buf(),
        args: vec!["app".to_string()],
    }
}

/// Verilen yolun gerçekten çalıştırılabilir bir çalışma zamanı olduğunu
/// denetler. Başarısızlık PATH aramasına DÜŞMEZ — `RuntimeManager` zaten
/// tek doğrulanmış adayı vermiştir; burada hata varsa kurulum bozuktur ve
/// kullanıcı onarım akışına yönlendirilmelidir.
fn validate_runtime_executable(path: &Path) -> Result<(), String> {
    if dosya_calistirilabilir_mi(path) {
        Ok(())
    } else {
        Err("Çalışma zamanı hazır değil. Ayarlar > Çalışma Zamanı bölümünden onarın.".into())
    }
}

impl CoreProcess {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            stdin: Mutex::new(None),
        }
    }

    /// Çekirdeği verilen, önceden doğrulanmış çalışma zamanı ikilisiyle
    /// başlat. Zaten çalışan bir süreç varsa yenisini AÇMAZ:
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
    pub fn start(&self, app: AppHandle, executable: &Path) -> Result<(), String> {
        let mut cocuk_kilit = self.child.lock().unwrap();
        if let Some(cocuk) = cocuk_kilit.as_mut() {
            if matches!(cocuk.try_wait(), Ok(None)) {
                return Ok(());
            }
        }

        validate_runtime_executable(executable)?;
        let launch = core_launch(executable);

        // stderr şimdilik `Stdio::null()`: sır sızıntısını ve sınırsız günlük
        // büyümesini önler. Yapılandırılmış, maskeli tanılama günlükleri
        // F aşamasındaki tanılama sınırında eklenecek. Stdout yalnız JSON
        // protokolüne ayrılmış kalır, başka hiçbir akış onunla karışmaz.
        let mut cocuk = Command::new(&launch.executable)
            .args(&launch.args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| format!("Fusion çalışma zamanı başlatılamadı: {error}"))?;

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

#[cfg(test)]
mod testler {
    use super::*;

    #[test]
    fn cekirdek_komutu_yalniz_verilen_runtimei_kullanir() {
        let launch = core_launch(Path::new(
            "/Application Support/Fusion/runtime/0.3.0a1/fusion",
        ));
        assert_eq!(
            launch.executable,
            PathBuf::from("/Application Support/Fusion/runtime/0.3.0a1/fusion")
        );
        assert_eq!(launch.args, vec!["app"]);
    }

    #[test]
    fn paketli_runtime_yolu_yoksa_path_aramasi_yapilmaz() {
        let missing = Path::new("/missing/fusion");
        let error = validate_runtime_executable(missing).unwrap_err();
        assert!(error.contains("Çalışma zamanı hazır değil"));
    }

    #[test]
    fn calistirilabilir_dosya_dogrulamadan_gecer() {
        let gecici = tempfile::NamedTempFile::new().expect("geçici dosya oluşturulamadı");
        let mut izinler = std::fs::metadata(gecici.path()).unwrap().permissions();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            izinler.set_mode(0o755);
        }
        std::fs::set_permissions(gecici.path(), izinler).unwrap();

        assert!(validate_runtime_executable(gecici.path()).is_ok());
    }

    #[test]
    fn calistirma_izni_olmayan_dosya_reddedilir() {
        let gecici = tempfile::NamedTempFile::new().expect("geçici dosya oluşturulamadı");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut izinler = std::fs::metadata(gecici.path()).unwrap().permissions();
            izinler.set_mode(0o644);
            std::fs::set_permissions(gecici.path(), izinler).unwrap();

            let error = validate_runtime_executable(gecici.path()).unwrap_err();
            assert!(error.contains("Çalışma zamanı hazır değil"));
        }
    }
}
