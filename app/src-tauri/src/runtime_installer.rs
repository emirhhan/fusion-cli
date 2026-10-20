//! Çalışma zamanı paketinin güvenli, kilitli ve atomik kurulumu.
//!
//! Burada üç şey aynı anda garanti edilir:
//!
//! - **Atomiklik**: kurulum önce bir evreleme (staging) dizinine açılır ve
//!   doğrulanır; hedef sürüm dizini yalnızca tek bir `rename` ile değişir,
//!   bu yüzden yarı açılmış bir çalışma zamanı asla etkin dizinde görünmez.
//! - **Kilit**: `paths.lock_file` üzerinde alınan özel (exclusive) dosya
//!   kilidi, iki pencerenin aynı anda aynı sürümü kurmaya kalkışıp
//!   birbirinin dosyalarını ezmesini engeller.
//! - **Güvenlik**: arşiv güvenilmez girdi kabul edilir. `../` içeren üye,
//!   mutlak yol ve hedef ağacın dışına çözülen sembolik bağ reddedilir
//!   (zip-slip savunması); her dosyanın SHA-256'sı manifestle karşılaştırılır.
//!
//! `install` ve etrafındaki tüm yardımcılar, `RuntimeManager::prepare`/
//! `repair` üzerinden A/7'nin `runtime_hazirla`/`runtime_onar` Tauri
//! komutlarıyla üretimde çağrılıyor; dosya kapsamlı `allow(dead_code)`
//! bu yüzden kaldırıldı.

use std::fs::OpenOptions;
use std::io::Read;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Component, Path, PathBuf};

use fs2::FileExt;
use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::runtime_manifest::{safe_relative, RuntimeError, RuntimeFileKind, RuntimeManifest};
use crate::runtime_paths::RuntimePaths;

/// Kurulacak arşiv ve manifestin diskteki konumları.
#[derive(Debug, Clone)]
pub struct RuntimeResources {
    pub manifest_path: PathBuf,
    pub archive_path: PathBuf,
}

/// Başarıyla kurulmuş bir çalışma zamanı sürümünün özeti.
#[derive(Debug, Clone)]
pub struct InstalledRuntime {
    pub version: String,
    pub executable: PathBuf,
}

/// Kurulum ilerlemesini arayüze taşıyan tel (wire) tipi.
#[derive(Debug, Clone, Serialize)]
pub struct RuntimeProgress {
    pub stage: String,
    pub completed: u64,
    pub total: u64,
    pub message: String,
}

/// Bir çalışma zamanı sürümünü güvenli, kilitli ve atomik biçimde kurar.
///
/// Sıra kesindir: kilit alınır, manifest okunup doğrulanır, arşivin
/// bütünlüğü denetlenir, içerik bir evreleme dizinine açılır, ağaç
/// manifestle birebir karşılaştırılır, `validate` ile bir sağlık denetimi
/// çalıştırılır ve ancak o geçerse sürüm dizini tek bir `rename` ile
/// değiştirilir. Herhangi bir adım başarısız olursa yalnızca bu çağrının
/// ürettiği evreleme dizini temizlenir; mevcut kurulu sürüme dokunulmaz.
pub fn install(
    resources: &RuntimeResources,
    paths: &RuntimePaths,
    expected_target: &str,
    validate: impl FnOnce(&Path) -> Result<(), RuntimeError>,
    mut progress: impl FnMut(RuntimeProgress),
) -> Result<InstalledRuntime, RuntimeError> {
    std::fs::create_dir_all(&paths.root).map_err(RuntimeError::Io)?;
    let _lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(&paths.lock_file)
        .map_err(RuntimeError::Io)?;
    _lock.lock_exclusive().map_err(RuntimeError::Io)?;

    let manifest = RuntimeManifest::read(&resources.manifest_path)?;
    manifest.validate(expected_target)?;
    verify_sha256(&resources.archive_path, &manifest.archive_sha256)?;

    let staging = paths.staging_dir(&manifest.runtime_version, std::process::id());
    remove_owned_staging(&staging, &paths.root)?;
    std::fs::create_dir_all(&staging).map_err(RuntimeError::Io)?;

    if let Err(error) = stage_runtime(
        &resources.archive_path,
        &manifest,
        &staging,
        validate,
        &mut progress,
    ) {
        remove_owned_staging(&staging, &paths.root)?;
        return Err(error);
    }

    let destination = paths.version_dir(&manifest.runtime_version);
    let executable = destination.join(&manifest.entrypoint);
    replace_version_atomically(&staging, &destination, &paths.root)?;

    Ok(InstalledRuntime {
        version: manifest.runtime_version,
        executable,
    })
}

/// Arşivi evreleme dizinine açar, ağacı manifestle doğrular ve giriş
/// noktasının sağlık denetimini çalıştırır. Herhangi bir adım
/// başarısız olursa evreleme dizini çağıran tarafından temizlenir; bu
/// yüzden burada kendi başına bir temizlik yapmaz.
fn stage_runtime(
    archive_path: &Path,
    manifest: &RuntimeManifest,
    staging: &Path,
    validate: impl FnOnce(&Path) -> Result<(), RuntimeError>,
    progress: &mut dyn FnMut(RuntimeProgress),
) -> Result<(), RuntimeError> {
    let total = manifest.files.len() as u64;
    extract_checked(archive_path, staging, total, progress)?;
    verify_tree(manifest, staging, total, progress)?;

    let executable = staging.join(safe_relative(&manifest.entrypoint)?);
    ensure_executable(&executable)?;
    validate(&executable)
}

/// Verilen dosyanın SHA-256'sının beklenenle eşleştiğini denetler.
fn verify_sha256(path: &Path, expected_hex: &str) -> Result<(), RuntimeError> {
    let mut file = std::fs::File::open(path).map_err(RuntimeError::Io)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];
    loop {
        let read = file.read(&mut buffer).map_err(RuntimeError::Io)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    let actual = hex::encode(hasher.finalize());
    if actual.eq_ignore_ascii_case(expected_hex) {
        Ok(())
    } else {
        Err(RuntimeError::HashMismatch)
    }
}

/// Arşivi `staging` altına güvenli biçimde açar.
///
/// Yalnızca dizin, düz dosya ve hedefi ağacın dışına çıkmayan göreli
/// sembolik bağ kabul edilir. Mutlak sembolik bağ, kök dışına çözülen
/// `..` bağı, aygıt dosyası, FIFO ve sabit (hard) bağ
/// `RuntimeError::UnsafePath` ile reddedilir.
fn extract_checked(
    archive_path: &Path,
    staging: &Path,
    total: u64,
    progress: &mut dyn FnMut(RuntimeProgress),
) -> Result<(), RuntimeError> {
    let file = std::fs::File::open(archive_path).map_err(RuntimeError::Archive)?;
    let decoder = flate2::read::GzDecoder::new(file);
    let mut archive = tar::Archive::new(decoder);
    let entries = archive.entries().map_err(RuntimeError::Archive)?;

    for (index, entry) in entries.enumerate() {
        let mut entry = entry.map_err(RuntimeError::Archive)?;
        let entry_type = entry.header().entry_type();
        let raw_path = entry.path().map_err(RuntimeError::Archive)?.into_owned();
        let relative = safe_relative(&raw_path)?;
        let target = staging.join(&relative);

        if entry_type.is_dir() {
            std::fs::create_dir_all(&target).map_err(RuntimeError::Io)?;
        } else if entry_type.is_file() {
            if let Some(parent) = target.parent() {
                std::fs::create_dir_all(parent).map_err(RuntimeError::Io)?;
            }
            entry.unpack(&target).map_err(RuntimeError::Archive)?;
        } else if entry_type.is_symlink() {
            let link_name = entry
                .link_name()
                .map_err(RuntimeError::Archive)?
                .ok_or_else(|| RuntimeError::UnsafePath(relative.clone()))?
                .into_owned();
            ensure_symlink_stays_inside(&relative, &link_name)?;
            if let Some(parent) = target.parent() {
                std::fs::create_dir_all(parent).map_err(RuntimeError::Io)?;
            }
            #[cfg(unix)]
            std::os::unix::fs::symlink(&link_name, &target).map_err(RuntimeError::Io)?;
            // Windows'ta sembolik bağ kurmak ayrıcalık ister ve Windows paketinde
            // sembolik bağ bulunmaz. Sessizce atlamak yerine reddedilir: beklenmedik
            // bir üye varsa kurulum yarım kalmış sayılmalı, "kuruldu" denmemeli.
            #[cfg(not(unix))]
            return Err(RuntimeError::UnsafePath(relative));
        } else {
            return Err(RuntimeError::UnsafePath(relative));
        }

        progress(RuntimeProgress {
            stage: "extract".to_string(),
            completed: index as u64 + 1,
            total,
            message: format!("{} çıkarılıyor", relative.display()),
        });
    }
    Ok(())
}

/// Bir sembolik bağın, kendi konumundan göreli çözüldüğünde evreleme
/// ağacının kökünün dışına çıkmadığını salt sözcüksel (dosya sistemine
/// dokunmadan) olarak denetler.
fn ensure_symlink_stays_inside(entry_path: &Path, link_name: &Path) -> Result<(), RuntimeError> {
    if link_name.is_absolute() {
        return Err(RuntimeError::UnsafePath(entry_path.to_path_buf()));
    }

    let mut stack: Vec<std::ffi::OsString> = entry_path
        .parent()
        .map(|parent| {
            parent
                .components()
                .map(|part| part.as_os_str().to_os_string())
                .collect()
        })
        .unwrap_or_default();

    for component in link_name.components() {
        match component {
            Component::Normal(part) => stack.push(part.to_os_string()),
            Component::CurDir => {}
            Component::ParentDir => {
                if stack.pop().is_none() {
                    return Err(RuntimeError::UnsafePath(entry_path.to_path_buf()));
                }
            }
            Component::RootDir | Component::Prefix(_) => {
                return Err(RuntimeError::UnsafePath(entry_path.to_path_buf()));
            }
        }
    }
    Ok(())
}

/// Evreleme ağacındaki her manifest üyesinin bütünlüğünü doğrular:
/// dosyaların SHA-256'sı ve izin biti, sembolik bağların hedefi manifestle
/// birebir karşılaştırılır.
fn verify_tree(
    manifest: &RuntimeManifest,
    staging: &Path,
    total: u64,
    progress: &mut dyn FnMut(RuntimeProgress),
) -> Result<(), RuntimeError> {
    for (index, file) in manifest.files.iter().enumerate() {
        let relative = safe_relative(&file.path)?;
        let target = staging.join(&relative);

        match file.kind {
            RuntimeFileKind::File => {
                let expected = file
                    .sha256
                    .as_deref()
                    .ok_or_else(|| RuntimeError::UnsafePath(relative.clone()))?;
                verify_sha256(&target, expected)?;
                set_mode(&target, file.mode)?;
            }
            RuntimeFileKind::Symlink => {
                let expected_target = file
                    .target
                    .as_ref()
                    .ok_or_else(|| RuntimeError::UnsafePath(relative.clone()))?;
                let actual_target = std::fs::read_link(&target).map_err(RuntimeError::Io)?;
                if &actual_target != expected_target {
                    return Err(RuntimeError::HashMismatch);
                }
            }
        }

        progress(RuntimeProgress {
            stage: "verify".to_string(),
            completed: index as u64 + 1,
            total,
            message: format!("{} doğrulanıyor", relative.display()),
        });
    }
    Ok(())
}

/// Bir dosyanın izin bitlerini manifestte kayıtlı moda göre ayarlar; tar
/// başlığındaki izne güvenmek yerine kaydı otoritatif kabul eder.
///
/// Windows'ta POSIX izin biti yoktur ve çalıştırılabilirlik uzantıyla belirlenir;
/// orada bu işlem anlamsızdır ve sessizce atlanır.
#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) -> Result<(), RuntimeError> {
    let permissions = std::fs::Permissions::from_mode(mode & 0o7777);
    std::fs::set_permissions(path, permissions).map_err(RuntimeError::Io)
}

#[cfg(not(unix))]
fn set_mode(_path: &Path, _mode: u32) -> Result<(), RuntimeError> {
    Ok(())
}

/// Giriş noktasının çalıştırılabilir izne sahip olduğundan emin olur; bazı
/// dosya sistemleri arşivdeki izin bitini birebir korumayabilir.
///
/// Windows'ta çalıştırılabilirlik izin biti değil `.exe` uzantısıdır; orada
/// yapılacak bir şey yoktur, ama dosyanın VARLIĞI yine doğrulanır.
#[cfg(unix)]
fn ensure_executable(path: &Path) -> Result<(), RuntimeError> {
    let metadata = std::fs::metadata(path).map_err(RuntimeError::Io)?;
    let mut permissions = metadata.permissions();
    permissions.set_mode(permissions.mode() | 0o111);
    std::fs::set_permissions(path, permissions).map_err(RuntimeError::Io)
}

#[cfg(not(unix))]
fn ensure_executable(path: &Path) -> Result<(), RuntimeError> {
    std::fs::metadata(path).map_err(RuntimeError::Io)?;
    Ok(())
}

/// Verilen yolun `root` altında kaldığını doğrular.
fn ensure_child(path: &Path, root: &Path) -> Result<(), RuntimeError> {
    if path.starts_with(root) {
        Ok(())
    } else {
        Err(RuntimeError::UnsafePath(path.to_path_buf()))
    }
}

/// Yalnızca `RuntimePaths::staging_dir` ile üretilmiş, `root` altında
/// olduğu tekrar doğrulanmış bir evreleme dizinini siler. Bu çift denetim,
/// bir hata durumunda yanlışlıkla kök dışı bir dizinin silinmesini
/// engeller.
fn remove_owned_staging(staging: &Path, root: &Path) -> Result<(), RuntimeError> {
    ensure_child(staging, root)?;
    let owned_by_installer = staging
        .file_name()
        .map(|name| name.to_string_lossy().starts_with(".install-"))
        .unwrap_or(false);
    if !owned_by_installer {
        return Err(RuntimeError::UnsafePath(staging.to_path_buf()));
    }
    if staging.exists() {
        std::fs::remove_dir_all(staging).map_err(RuntimeError::Io)?;
    }
    Ok(())
}

/// Evrelemedeki sürümü hedef sürüm dizinine tek bir `rename` ile taşır.
///
/// Mevcut aynı sürüm doğrudan silinmez: önce karantinaya (`.replaced-...`)
/// taşınır, yeni sürüm yerine geçtikten sonra silinir. `rename` başarısız
/// olursa karantinadaki eski sürüm geri getirilir; böylece hedef dizin hiç
/// boş kalmaz.
fn replace_version_atomically(
    staging: &Path,
    destination: &Path,
    root: &Path,
) -> Result<(), RuntimeError> {
    ensure_child(destination, root)?;
    let quarantine = root.join(format!(
        ".replaced-{}-{}",
        destination
            .file_name()
            .expect("sürüm dizini her zaman bir dosya adına sahiptir")
            .to_string_lossy(),
        std::process::id()
    ));

    if destination.exists() {
        std::fs::rename(destination, &quarantine).map_err(RuntimeError::Io)?;
    }
    if let Err(error) = std::fs::rename(staging, destination) {
        if quarantine.exists() {
            std::fs::rename(&quarantine, destination).map_err(RuntimeError::Io)?;
        }
        return Err(RuntimeError::Io(error));
    }
    if quarantine.exists() {
        std::fs::remove_dir_all(&quarantine).map_err(RuntimeError::Io)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const TEST_TARGET: &str = "aarch64-apple-darwin";
    const TEST_VERSION: &str = "0.9.9-test";

    /// Testler için gerçek, küçük bir gzip/tar arşivi ve eşleşen manifest
    /// üreten yardımcı. Üretim kurulum kodunu hiçbir yerde mocklamaz; her
    /// senaryo gerçek dosya sistemi işlemleriyle çalışır.
    struct RuntimeFixture {
        temp: tempfile::TempDir,
        paths: RuntimePaths,
        resources: RuntimeResources,
    }

    impl RuntimeFixture {
        fn new() -> Self {
            let temp = tempfile::tempdir().expect("geçici dizin oluşturulamadı");
            let paths = RuntimePaths::for_home(temp.path());
            let archive_path = temp.path().join("fusion-runtime.tar.gz");
            let manifest_path = temp.path().join("runtime-manifest.json");
            let fixture = Self {
                temp,
                paths,
                resources: RuntimeResources {
                    manifest_path,
                    archive_path,
                },
            };
            fixture.write_valid_archive_and_manifest();
            fixture
        }

        fn valid() -> Self {
            Self::new()
        }

        fn write_valid_archive_and_manifest(&self) {
            let content = b"#!/bin/sh\necho fusion\n";
            let archive_bytes = build_tar_gz(&[("fusion", content, 0o755)]);
            std::fs::write(&self.resources.archive_path, &archive_bytes).unwrap();
            let archive_hash = sha256_hex(&archive_bytes);
            let file_hash = sha256_hex(content);
            write_manifest(
                &self.resources.manifest_path,
                &archive_hash,
                &[ManifestFile {
                    path: "fusion",
                    kind: "file",
                    mode: 0o755,
                    sha256: Some(file_hash),
                    target: None,
                }],
            );
        }

        fn with_archive_bytes(self, bytes: &[u8]) -> Self {
            std::fs::write(&self.resources.archive_path, bytes).unwrap();
            self
        }

        fn with_manifest_hash(self, hash: &str) -> Self {
            rewrite_manifest_archive_hash(&self.resources.manifest_path, hash);
            self
        }

        fn with_tar_file(self, name: &str, content: &[u8]) -> Self {
            let archive_bytes = build_tar_gz(&[(name, content, 0o644)]);
            std::fs::write(&self.resources.archive_path, &archive_bytes).unwrap();
            let archive_hash = sha256_hex(&archive_bytes);
            rewrite_manifest_archive_hash(&self.resources.manifest_path, &archive_hash);
            self
        }
    }

    struct ManifestFile {
        path: &'static str,
        kind: &'static str,
        mode: u32,
        sha256: Option<String>,
        target: Option<&'static str>,
    }

    fn build_tar_gz(entries: &[(&str, &[u8], u32)]) -> Vec<u8> {
        let buffer = Vec::new();
        let encoder = flate2::write::GzEncoder::new(buffer, flate2::Compression::default());
        let mut builder = tar::Builder::new(encoder);
        for (name, content, mode) in entries {
            let mut header = tar::Header::new_gnu();
            // `Header::set_path` bilerek bozuk (ör. `..` içeren) isimleri
            // reddeder; buradaki testler tam da kendi `extract_checked`
            // güvenliğimizi bir arşivdeki kötü yol girdisiyle sınadığından,
            // ham ad alanına doğrudan yazarak tar crate'inin bu korumasını
            // bilerek atlıyoruz.
            set_raw_name(&mut header, name);
            header.set_size(content.len() as u64);
            header.set_mode(*mode);
            header.set_cksum();
            builder
                .append(&header, *content)
                .expect("tar üyesi eklenemedi");
        }
        let encoder = builder.into_inner().expect("tar arşivi kapatılamadı");
        encoder.finish().expect("gzip akışı kapatılamadı")
    }

    fn set_raw_name(header: &mut tar::Header, name: &str) {
        let bytes = name.as_bytes();
        let old = header.as_old_mut();
        old.name.fill(0);
        let len = bytes.len().min(old.name.len());
        old.name[..len].copy_from_slice(&bytes[..len]);
    }

    fn sha256_hex(bytes: &[u8]) -> String {
        let mut hasher = Sha256::new();
        hasher.update(bytes);
        hex::encode(hasher.finalize())
    }

    fn write_manifest(path: &Path, archive_sha256: &str, files: &[ManifestFile]) {
        let files_json: Vec<serde_json::Value> = files
            .iter()
            .map(|file| {
                serde_json::json!({
                    "path": file.path,
                    "kind": file.kind,
                    "mode": file.mode,
                    "sha256": file.sha256,
                    "target": file.target,
                })
            })
            .collect();
        let manifest = serde_json::json!({
            "schema": 1,
            "runtime_version": TEST_VERSION,
            "target": TEST_TARGET,
            "archive": "fusion-runtime.tar.gz",
            "archive_sha256": archive_sha256,
            "entrypoint": "fusion",
            "files": files_json,
        });
        std::fs::write(path, serde_json::to_vec_pretty(&manifest).unwrap()).unwrap();
    }

    fn rewrite_manifest_archive_hash(path: &Path, hash: &str) {
        let content = std::fs::read_to_string(path).unwrap();
        let mut value: serde_json::Value = serde_json::from_str(&content).unwrap();
        value["archive_sha256"] = serde_json::Value::String(hash.to_string());
        std::fs::write(path, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
    }

    #[test]
    fn archive_hash_uyusmazsa_hedef_dizin_olusmaz() {
        let fixture = RuntimeFixture::new()
            .with_archive_bytes(b"bozuk")
            .with_manifest_hash("00");
        let result = install(
            &fixture.resources,
            &fixture.paths,
            TEST_TARGET,
            |_| Ok(()),
            |_| {},
        );
        assert!(matches!(result, Err(RuntimeError::HashMismatch)));
        assert!(!fixture.paths.version_dir(TEST_VERSION).exists());
    }

    #[test]
    fn path_traversal_girdisi_runtime_kokunun_disina_cikamaz() {
        let fixture = RuntimeFixture::new().with_tar_file("../../escaped", b"no");
        assert!(matches!(
            install(
                &fixture.resources,
                &fixture.paths,
                TEST_TARGET,
                |_| Ok(()),
                |_| {}
            ),
            Err(RuntimeError::UnsafePath(_))
        ));
        assert!(!fixture.temp.path().join("escaped").exists());
    }

    #[test]
    fn basarili_kurulum_once_staginge_yazip_surume_tasir() {
        let fixture = RuntimeFixture::valid();
        let installed = install(
            &fixture.resources,
            &fixture.paths,
            TEST_TARGET,
            |_| Ok(()),
            |_| {},
        )
        .unwrap();
        assert_eq!(
            installed.executable,
            fixture.paths.version_dir(TEST_VERSION).join("fusion")
        );
        assert!(installed.executable.exists());
        assert!(std::fs::read_dir(&fixture.paths.root)
            .unwrap()
            .all(|item| !item
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with(".install-")));
    }

    #[test]
    fn saglik_denetimi_basarisiz_olursa_mevcut_surum_degismez_ve_staging_temizlenir() {
        let fixture = RuntimeFixture::valid();
        install(
            &fixture.resources,
            &fixture.paths,
            TEST_TARGET,
            |_| Ok(()),
            |_| {},
        )
        .unwrap();
        let destination = fixture.paths.version_dir(TEST_VERSION);
        let onceki_icerik = std::fs::read(destination.join("fusion")).unwrap();

        let result = install(
            &fixture.resources,
            &fixture.paths,
            TEST_TARGET,
            |_| Err(RuntimeError::Health("smoke başarısız".into())),
            |_| {},
        );

        assert!(matches!(result, Err(RuntimeError::Health(_))));
        assert_eq!(
            std::fs::read(destination.join("fusion")).unwrap(),
            onceki_icerik
        );
        assert!(std::fs::read_dir(&fixture.paths.root)
            .unwrap()
            .all(|item| !item
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with(".install-")));
    }
}
