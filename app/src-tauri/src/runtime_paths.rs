//! macOS'a özgü çalışma zamanı yol modeli.
//!
//! Burada ürün mantığı YOKTUR: yalnızca kurulum/onarım/rollback'in üzerine
//! bina edileceği sabit yol iskeleti vardır. Kök dizin uydurulmaz; Fusion'ın
//! tam macOS uygulaması tasarımında (`geliştirme belgeleri`) belirtilen
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
    /// Verilen ev dizininden platformun çalışma zamanı yol modelini üretir.
    ///
    /// macOS'ta kök `~/Library/Application Support/Fusion/runtime`,
    /// Windows'ta `%LOCALAPPDATA%\Fusion\runtime`dır. Windows'ta LOCAL seçildi:
    /// çalışma zamanı yüz megabaytlarca makineye özel ikili taşır ve gezici
    /// (roaming) profile girerse her oturum açılışında ağ üzerinden kopyalanır.
    /// Bu sözleşme dışına çıkan bir çağıran olmamalıdır.
    pub fn for_home(home: &Path) -> Self {
        let root = if cfg!(windows) {
            home.join("AppData")
                .join("Local")
                .join("Fusion")
                .join("runtime")
        } else {
            home.join("Library")
                .join("Application Support")
                .join("Fusion")
                .join("runtime")
        };
        Self::from_root(root)
    }

    /// Üretim girişi: Windows'ta kök gerçek `%LOCALAPPDATA%`dan alınır. `home\AppData\Local`
    /// varsayımı OneDrive/yeniden yönlendirilmiş profil ve özel `LOCALAPPDATA` kurulumlarında
    /// Tauri'nin `local_data_dir()`'ından (Kits bunu kullanır) farklı bir yere işaret ediyordu
    /// (Q1-12). Test ve kurulum kodları ortamdan bağımsız kalsın diye `for_home` saf kalır.
    pub fn for_current_user(home: &Path) -> Self {
        Self::for_home_with_local(home, std::env::var_os("LOCALAPPDATA").as_deref())
    }

    /// `for_home` + isteğe bağlı gerçek yerel veri dizini (yalnız Windows'ta etkilidir).
    pub fn for_home_with_local(home: &Path, local_app_data: Option<&std::ffi::OsStr>) -> Self {
        if cfg!(windows) {
            if let Some(local) = local_app_data
                .map(PathBuf::from)
                .filter(|path| path.is_absolute())
            {
                let root = local.join("Fusion").join("runtime");
                return Self::from_root(root);
            }
        }
        Self::for_home(home)
    }

    fn from_root(root: PathBuf) -> Self {
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

    #[cfg(not(windows))]
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

    /// Windows'ta çalışma zamanı GEZİCİ profile girmemeli: yüz megabaytlık
    /// makineye özel ikili her oturum açılışında ağ üzerinden kopyalanırdı.
    #[cfg(windows)]
    #[test]
    fn windows_runtime_koku_local_appdata_altindadir() {
        let paths = RuntimePaths::for_home(Path::new("C:\\Users\\ada"));
        assert_eq!(
            paths.root,
            PathBuf::from("C:\\Users\\ada\\AppData\\Local\\Fusion\\runtime")
        );
        assert_eq!(paths.active_record, paths.root.join("active-runtime.json"));
        assert_eq!(paths.lock_file, paths.root.join("runtime.lock"));
    }

    /// Ölçüldü (30 Ekim): Windows kökü hep `home\AppData\Local` idi; yeniden yönlendirilmiş
    /// `%LOCALAPPDATA%` ile Kits (`local_data_dir`) ve çalışma zamanı ayrı yerlere yazıyordu.
    #[cfg(windows)]
    #[test]
    fn windows_gercek_localappdata_kullanir() {
        let paths = RuntimePaths::for_home_with_local(
            Path::new("C:\\Users\\ada"),
            Some(std::ffi::OsStr::new("D:\\Yerel")),
        );
        assert_eq!(paths.root, PathBuf::from("D:\\Yerel\\Fusion\\runtime"));
        let yedek = RuntimePaths::for_home_with_local(Path::new("C:\\Users\\ada"), None);
        assert_eq!(
            yedek.root,
            PathBuf::from("C:\\Users\\ada\\AppData\\Local\\Fusion\\runtime")
        );
    }

    #[cfg(not(windows))]
    #[test]
    fn macos_localappdata_degiskenini_yok_sayar() {
        let paths = RuntimePaths::for_home_with_local(
            Path::new("/Users/ada"),
            Some(std::ffi::OsStr::new("/baska")),
        );
        assert_eq!(
            paths.root,
            RuntimePaths::for_home(Path::new("/Users/ada")).root
        );
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
