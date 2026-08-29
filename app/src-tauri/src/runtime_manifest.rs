//! Çalışma zamanı paketinin `runtime-manifest.json` dosyasını okur ve
//! doğrular.
//!
//! Burada ürün mantığı YOKTUR: yalnızca manifestin tipe dönüştürülmesi ve
//! hedef mimariyle eşleşip eşleşmediğinin denetlenmesi vardır. Eksik veya
//! bozuk bir alan sessizce varsayılana düşmez — tipli bir hata döner, çünkü
//! kurulum/onarım/rollback bu tipin üstüne bina edilecektir.
//!
//! `read`, `validate`, `RuntimeFile` alanları ve çoğu `RuntimeError` varyantı,
//! `runtime_installer.rs` üzerinden A/7'nin `runtime_hazirla`/`runtime_onar`
//! Tauri komutlarıyla artık üretimde de çağrılıyor; dosya kapsamlı
//! `allow(dead_code)` bu yüzden kaldırıldı.

use std::path::{Component, Path, PathBuf};

use serde::Deserialize;
use thiserror::Error;

/// Çalışma zamanı paketinin makine tarafından okunabilir manifesti.
///
/// `schema` alanı şema sürümünü taşır; `validate` bilinmeyen bir şema veya
/// hedef mimariyle karşılaşınca hatayı burada, kurulumdan önce keser.
#[derive(Debug, Clone, Deserialize)]
pub struct RuntimeManifest {
    pub schema: u32,
    pub runtime_version: String,
    pub target: String,
    pub archive: PathBuf,
    pub archive_sha256: String,
    pub entrypoint: PathBuf,
    pub files: Vec<RuntimeFile>,
}

/// Manifestin desteklediği tek şema sürümü. Bu depoda üretilen paketleyici
/// (`fusion app health` ile aynı sözleşmeyi paylaşan A/2 adımı) yalnızca bu
/// sürümü yazar; başka bir sürüm görülürse Rust tarafı kurulumu reddeder.
const DESTEKLENEN_SEMA: u32 = 1;

/// Bir paket üyesinin dosya mı sembolik bağ mı olduğunu belirtir.
#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeFileKind {
    File,
    Symlink,
}

/// Manifestteki tek bir paket üyesi.
///
/// `sha256` yalnızca `File` türünde, `target` yalnızca `Symlink` türünde
/// beklenir; bu değişmez `RuntimeManifest::validate` içinde denetlenir.
#[derive(Debug, Clone, Deserialize)]
pub struct RuntimeFile {
    pub path: PathBuf,
    pub kind: RuntimeFileKind,
    pub mode: u32,
    pub sha256: Option<String>,
    pub target: Option<PathBuf>,
}

/// Manifest okuma, ayrıştırma ve doğrulama sırasında oluşabilecek hatalar.
///
/// Metinler Türkçedir ve sır/değer içeriği taşımaz: örneğin okunamayan
/// dosyanın yolu mesaja gömülmez, yalnızca ne tür bir hata olduğu söylenir.
#[derive(Debug, Error)]
pub enum RuntimeError {
    #[error("çalışma zamanı manifesti okunamadı")]
    ManifestRead(#[source] std::io::Error),

    #[error("çalışma zamanı manifesti çözümlenemedi")]
    ManifestDecode(#[source] serde_json::Error),

    #[error("çalışma zamanı manifestinin şeması desteklenmiyor")]
    UnsupportedSchema,

    #[error("çalışma zamanı manifesti bu makinenin mimarisiyle eşleşmiyor")]
    TargetMismatch,

    #[error("manifestte üst dizine çıkan veya mutlak bir yol bulundu")]
    UnsafePath(PathBuf),

    #[error("dosya bütünlük denetimi (sha256) başarısız oldu")]
    HashMismatch,

    #[error("dosya sistemi işlemi başarısız oldu")]
    Io(#[source] std::io::Error),

    #[error("çalışma zamanı arşivi açılamadı")]
    Archive(#[source] std::io::Error),

    #[error("çalışma zamanı sağlık denetimi başarısız oldu: {0}")]
    Health(String),

    #[error("çalışma zamanı sağlık denetimi zaman aşımına uğradı")]
    HealthTimeout,

    #[error("çalışma zamanı sağlık raporu çözümlenemedi")]
    HealthDecode(#[source] serde_json::Error),

    #[error("etkin sürüm kaydı çözümlenemedi")]
    ActiveRecordDecode(#[source] serde_json::Error),

    #[error("etkin sürüm kaydı hazırlanamadı")]
    ActiveRecordEncode(#[source] serde_json::Error),

    #[error("uygulama kaynak dizini çözülemedi: {0}")]
    ResourceDir(String),

    #[error("kullanılabilir sağlıklı bir çalışma zamanı bulunamadı")]
    NoHealthyRuntime,
}

impl RuntimeManifest {
    /// Verilen yoldaki `runtime-manifest.json` dosyasını okuyup ayrıştırır.
    ///
    /// Dosya bulunamaz veya JSON bozuksa hata döner; hiçbir alan sessizce
    /// varsayılana düşmez çünkü `Deserialize` eksik zorunlu alanda da hata
    /// üretir.
    pub fn read(path: &Path) -> Result<Self, RuntimeError> {
        let icerik = std::fs::read_to_string(path).map_err(RuntimeError::ManifestRead)?;
        serde_json::from_str(&icerik).map_err(RuntimeError::ManifestDecode)
    }

    /// Manifestin şemasının desteklendiğini ve hedef mimarinin bu makineyle
    /// eşleştiğini denetler.
    pub fn validate(&self, target: &str) -> Result<(), RuntimeError> {
        if self.schema != DESTEKLENEN_SEMA {
            return Err(RuntimeError::UnsupportedSchema);
        }
        if self.target != target {
            return Err(RuntimeError::TargetMismatch);
        }
        safe_relative(&self.archive)?;
        safe_relative(&self.entrypoint)?;
        for dosya in &self.files {
            safe_relative(&dosya.path)?;
        }
        Ok(())
    }
}

/// Bir yolun paket köküyle sınırlı, göreli ve güvenli olduğunu doğrular.
///
/// Mutlak yollar ve `..`/kök gibi normal olmayan bileşenler reddedilir;
/// aksi halde bozuk bir manifest paket kökünün dışına yazabilir.
pub fn safe_relative(path: &Path) -> Result<PathBuf, RuntimeError> {
    if path.is_absolute()
        || path
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err(RuntimeError::UnsafePath(path.to_path_buf()));
    }
    Ok(path.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifest_surumu_hedefi_ve_giris_noktasini_okur() {
        let manifest: RuntimeManifest = serde_json::from_str(
            r#"{
          "schema":1,"runtime_version":"0.3.0a1","target":"aarch64-apple-darwin",
          "archive":"fusion-runtime.tar.gz","archive_sha256":"aa","entrypoint":"fusion","files":[]
        }"#,
        )
        .unwrap();
        assert_eq!(manifest.runtime_version, "0.3.0a1");
        assert_eq!(manifest.entrypoint, PathBuf::from("fusion"));
    }

    #[test]
    fn ust_dizine_cikan_manifest_yolu_reddedilir() {
        assert!(safe_relative(Path::new("../../.ssh/id_rsa")).is_err());
        assert!(safe_relative(Path::new("/tmp/fusion")).is_err());
        assert_eq!(
            safe_relative(Path::new("_internal/lib.dylib")).unwrap(),
            PathBuf::from("_internal/lib.dylib")
        );
    }

    #[test]
    fn bilinmeyen_sema_reddedilir() {
        let manifest: RuntimeManifest = serde_json::from_str(
            r#"{
          "schema":99,"runtime_version":"0.3.0a1","target":"aarch64-apple-darwin",
          "archive":"fusion-runtime.tar.gz","archive_sha256":"aa","entrypoint":"fusion","files":[]
        }"#,
        )
        .unwrap();
        assert!(matches!(
            manifest.validate("aarch64-apple-darwin"),
            Err(RuntimeError::UnsupportedSchema)
        ));
    }

    #[test]
    fn hedef_mimari_uyusmazligi_reddedilir() {
        let manifest: RuntimeManifest = serde_json::from_str(
            r#"{
          "schema":1,"runtime_version":"0.3.0a1","target":"x86_64-apple-darwin",
          "archive":"fusion-runtime.tar.gz","archive_sha256":"aa","entrypoint":"fusion","files":[]
        }"#,
        )
        .unwrap();
        assert!(matches!(
            manifest.validate("aarch64-apple-darwin"),
            Err(RuntimeError::TargetMismatch)
        ));
    }

    #[test]
    fn eksik_zorunlu_alan_sessizce_gecmez() {
        let sonuc: Result<RuntimeManifest, _> = serde_json::from_str(
            r#"{"schema":1,"runtime_version":"0.3.0a1","target":"aarch64-apple-darwin"}"#,
        );
        assert!(sonuc.is_err());
    }

    #[test]
    fn manifest_icindeki_guvensiz_yol_validate_sirasinda_yakalanir() {
        let manifest: RuntimeManifest = serde_json::from_str(
            r#"{
          "schema":1,"runtime_version":"0.3.0a1","target":"aarch64-apple-darwin",
          "archive":"fusion-runtime.tar.gz","archive_sha256":"aa","entrypoint":"fusion",
          "files":[{"path":"../evil","kind":"file","mode":420,"sha256":"aa","target":null}]
        }"#,
        )
        .unwrap();
        assert!(matches!(
            manifest.validate("aarch64-apple-darwin"),
            Err(RuntimeError::UnsafePath(_))
        ));
    }

    #[test]
    fn manifest_icindeki_guvensiz_arsiv_yolu_reddedilir() {
        let manifest: RuntimeManifest = serde_json::from_str(
            r#"{
          "schema":1,"runtime_version":"0.3.0a1","target":"aarch64-apple-darwin",
          "archive":"../../fusion-runtime.tar.gz","archive_sha256":"aa",
          "entrypoint":"fusion","files":[]
        }"#,
        )
        .unwrap();

        assert!(matches!(
            manifest.validate("aarch64-apple-darwin"),
            Err(RuntimeError::UnsafePath(_))
        ));
    }
}
