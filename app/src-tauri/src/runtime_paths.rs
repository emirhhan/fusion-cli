//! macOS'a özgü çalışma zamanı yol modeli.
//!
//! Burada ürün mantığı YOKTUR: yalnızca kurulum/onarım/rollback'in üzerine
//! bina edileceği sabit yol iskeleti vardır. Kök dizin uydurulmaz; Fusion'ın
//! tam macOS uygulaması tasarımında (`docs/superpowers/specs/...`) belirtilen
//! `~/Library/Application Support/Fusion/runtime` yolu birebir kullanılır.
//!
//! `root`, `lock_file`, `version_dir` ve `staging_dir`, `runtime_installer.rs`
//! üzerinden A/7'nin `runtime_hazirla`/`runtime_onar` Tauri komutlarıyla artık
//! üretimde de çağrılıyor; dosya kapsamlı `allow(dead_code)` bu yüzden
//! kaldırıldı.

use std::path::{Path, PathBuf};

/// Çalışma zamanı ile ilgili tüm dosya sistemi yollarını tek yerde toplar.
#[derive(Debug, Clone)]
pub struct RuntimePaths {
    /// Tüm çalışma zamanı sürümlerinin ve kilit/kayıt dosyalarının kökü.
    pub root: PathBuf,
    /// Şu anda etkin olan çalışma zamanı sürümünü işaret eden kayıt dosyası.
    pub active_record: PathBuf,
    /// Eşzamanlı kurulum/onarım denemelerini engelleyen kilit dosyası.
    pub lock_file: PathBuf,
}

impl RuntimePaths {
    /// Verilen ev dizininden macOS çalışma zamanı yol modelini üretir.
    ///
    /// Kök her zaman `~/Library/Application Support/Fusion/runtime`dır;
    /// bu sözleşme dışına çıkan bir çağıran olmamalıdır.
    pub fn for_home(home: &Path) -> Self {
        let root = home
            .join("Library")
            .join("Application Support")
            .join("Fusion")
            .join("runtime");
        Self {
            active_record: root.join("active-runtime.json"),
            lock_file: root.join("runtime.lock"),
            root,
        }
    }

    /// Belirli bir çalışma zamanı sürümünün kurulu olacağı dizin.
    pub fn version_dir(&self, version: &str) -> PathBuf {
        self.root.join(version)
    }

    /// Bir kurulumun tamamlanana kadar yazıldığı geçici, adı çakışmayan
    /// evreleme (staging) dizini. `nonce`, aynı sürümün eşzamanlı iki
    /// kurulum denemesinde çakışmayı önler.
    pub fn staging_dir(&self, version: &str, nonce: u32) -> PathBuf {
        self.root.join(format!(".install-{version}-{nonce}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn macos_runtime_koku_fusion_application_support_altindadir() {
        let paths = RuntimePaths::for_home(Path::new("/Users/ada"));
        assert_eq!(
            paths.root,
            PathBuf::from("/Users/ada/Library/Application Support/Fusion/runtime")
        );
        assert_eq!(paths.active_record, paths.root.join("active-runtime.json"));
        assert_eq!(paths.lock_file, paths.root.join("runtime.lock"));
    }

    #[test]
    fn surum_dizini_kok_altinda_surum_adiyla_olusur() {
        let paths = RuntimePaths::for_home(Path::new("/Users/ada"));
        assert_eq!(paths.version_dir("0.3.0a1"), paths.root.join("0.3.0a1"));
    }

    #[test]
    fn evreleme_dizini_surum_ve_nonce_ile_benzersizdir() {
        let paths = RuntimePaths::for_home(Path::new("/Users/ada"));
        let birinci = paths.staging_dir("0.3.0a1", 1);
        let ikinci = paths.staging_dir("0.3.0a1", 2);
        assert_ne!(birinci, ikinci);
        assert_eq!(birinci, paths.root.join(".install-0.3.0a1-1"));
    }
}
