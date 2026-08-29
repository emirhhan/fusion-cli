//! Fusion çekirdeği alt süreçleri için ortak başlatma ve durdurma kuralları.
//!
//! Oturum sahipliği ve stdio aktarımı `session_manager` içindedir. Burada ürün
//! mantığı YOKTUR: yalnız çalıştırılabilir dosya doğrulanır, komut tanımlanır
//! ve kapanmayan bir alt süreç sınırlı süre sonunda güvenle sonlandırılır.
//! Hangi ikilinin çalıştırılacağına karar veren taraf her zaman `RuntimeManager`
//! (bkz. `runtime_manager.rs`) — bu modül asla sistemdeki `fusion` komutuna,
//! `HOME` altındaki kurulumlara ya da `PATH`'e bakmaz. Sebep: kullanıcının
//! makinesindeki `fusion` başka bir sürüm, yarım kurulum ya da hiç olmayabilir;
//! sessiz bir geri düşüş teşhis edilemeyen hatalar üretir. Ayrıca GUI
//! uygulamaları minimal bir ortamla açılır (`launchctl getenv PATH` çoğu
//! zaman boştur), bu yüzden "sistemde kurulu" varsayımı zaten güvenilmez.
//! Geliştirici Kipi bu kuralın TEK istisnasıdır ve yalnız `lib.rs`'te,
//! açıkça istenmişse devreye girer.

use std::path::{Path, PathBuf};
use std::process::Child;
use std::time::{Duration, Instant};

/// Çekirdeğin stdin EOF'una tepki verip düzgün çıkması için bu kadar
/// bekler. Pencere kapanış olayı ana döngüde senkron çalıştığından kullanıcıyı
/// uzun süre bekletmemek adına kısa tutulur; süre aşılırsa `kill()` ile
/// zorla sonlandırılır.
pub(crate) const DURDURMA_ZAMAN_ASIMI: Duration = Duration::from_millis(2000);

/// Bekleme sırasında sürecin çıkış yapıp yapmadığını denetleme aralığı.
pub(crate) const YOKLAMA_ARALIGI: Duration = Duration::from_millis(50);

/// Oturum yöneticisinin çalıştıracağı komutun saf (yan etkisiz) tanımı. Testler
/// gerçek bir süreç açmadan bu değeri denetler.
#[derive(Debug, PartialEq)]
pub(crate) struct CoreLaunch {
    pub(crate) executable: PathBuf,
    pub(crate) args: Vec<String>,
}

/// Verilen çalışma zamanı ikilisi için başlatma komutunu üretir. Argüman
/// listesi sabittir: çekirdek her zaman uzun ömürlü, stdio üzerinden JSON
/// konuşan `app` alt komutuyla açılır.
pub(crate) fn core_launch(executable: &Path) -> CoreLaunch {
    CoreLaunch {
        executable: executable.to_path_buf(),
        args: vec!["app".to_string()],
    }
}

/// Verilen yolun gerçekten çalıştırılabilir bir çalışma zamanı olduğunu
/// denetler. Başarısızlık PATH aramasına DÜŞMEZ — `RuntimeManager` zaten
/// tek doğrulanmış adayı vermiştir; burada hata varsa kurulum bozuktur ve
/// kullanıcı onarım akışına yönlendirilmelidir.
pub(crate) fn validate_runtime_executable(path: &Path) -> Result<(), String> {
    if dosya_calistirilabilir_mi(path) {
        Ok(())
    } else {
        Err("Çalışma zamanı hazır değil. Ayarlar > Çalışma Zamanı bölümünden onarın.".into())
    }
}

pub(crate) fn stop_child(mut child: Child) {
    let baslangic = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) => {
                if baslangic.elapsed() >= DURDURMA_ZAMAN_ASIMI {
                    let _ = child.kill();
                    let _ = child.wait();
                    return;
                }
                std::thread::sleep(YOKLAMA_ARALIGI);
            }
            Err(_) => return,
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
