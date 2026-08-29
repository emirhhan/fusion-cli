# Paketli macOS Çalışma Zamanı Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion macOS uygulamasını sistemde Python veya `fusion` kurulumu gerektirmeden açılan, kendi sürümlü çalışma zamanını kuran, doğrulayan, onaran ve gerektiğinde önceki sağlıklı sürüme dönen bağımsız bir ürün haline getirmek.

**Architecture:** PyInstaller `onedir` çıktısı deterministik bir `tar.gz` arşivi ve SHA-256 manifesti olarak Tauri paketine eklenir. Rust çalışma zamanı yöneticisi arşivi `~/Library/Application Support/Fusion/runtime/{runtime_version}/` altına kilitli ve atomik biçimde kurar, hafif Python sağlık komutuyla doğrular ve yalnız sağlıklı yürütülebilir dosyayı `CoreProcess`e verir. React başlangıç kapısı kurulum/onarım durumunu gösterir; normal release sürümü PATH veya sistem kurulumuna hiçbir zaman düşmez.

**Tech Stack:** Python 3.11+, PyInstaller 6, Tauri 2, Rust 2021, React 19, TypeScript 5.8, Vitest 4, SHA-256, gzip/tar.

**Spec:** `docs/superpowers/specs/2026-08-29-tam-macos-uygulamasi-design.md`

## Global Constraints

- İlk hedef macOS; Apple Silicon ve Intel çalışma zamanları kendi mimarilerinde ayrı üretilir.
- Dağıtım imzasız `.app` ve sürükle-bırak `.dmg` olarak yapılır; Apple Developer hesabı gerekmez.
- Paketli çalışma zamanı PyInstaller `onedir` olur; `onefile` kullanılmaz.
- Aktif çalışma zamanı `~/Library/Application Support/Fusion/runtime/{runtime_version}/` altında yaşar.
- Kullanıcı ayarları, konuşmaları, anahtarları ve projeleri runtime klasörüne yazılmaz.
- Normal release modunda PATH, Homebrew, `~/.local/bin` veya mevcut venv yedeği kullanılmaz.
- Açık bir geliştirici seçimi olmadan sistem `fusion` ikilisi çalıştırılmaz. Bu planda yalnız debug derlemesinde tam yol verilen `FUSION_DEVELOPER_RUNTIME` geçici geliştirici dikişidir; kullanıcıya açık Geliştirici Modu sonraki ayarlar planında eklenir.
- Python, Rust ve TypeScript değişiklikleri test önce yazılarak ilerler.
- Kullanıcıya görünen metinler Türkçe; kod tanımlayıcıları mevcut katmanın yerleşik dilini izler.
- Sırlar stdout, stderr, manifest, tanılama veya paketleme günlüğüne yazılmaz.
- Kullanıcıya ait izlenmeyen `:memory:.ses` ve `index.html` dosyalarına dokunulmaz.
- Her görev kendi test kapısını ve ayrı conventional commitini içerir.

## Program Decomposition

Onaylanan tam uygulama tek değişiklik kümesi değildir. Bu plan **A — Çalışma zamanı temeli** teslimatını uygular. Sonraki bağımsız planlar sırasıyla şu sınırları kullanacaktır:

1. **B — Tasarım sistemi ve uygulama kabuğu:** Figma tokenları, 281 px kenar çubuğu, sohbet, sağ denetçi ve Kontrol Paneli görsel sistemi.
2. **C — Oturum ve geçmiş:** çoklu süreç yöneticisi, projeler, arama ve dinamik `/resumeclaude`, `/resumecodex`, `/resumehermes`.
3. **D — Proje araçları:** dosyalar, diff, terminal, süreç, test, Git, asset ve önizleme.
4. **E — Beceriler, ajanlar ve MCP:** kaynak keşfi, katalog, otomatik eşleşme ve izin görünürlüğü.
5. **F — Ayarlar, Kontrol Paneli ve gateway:** sağlayıcılar, anahtarlar, model yönlendirme, config kilidi, Origin/CSRF ve `fusion serve` yönetimi.
6. **G — Onboarding ve dersler:** ilk açılış, kaynak keşfi, örnek proje ve etkileşimli öğrenme.
7. **H — Dağıtım kalite kapısı:** iki mimari, temiz kullanıcı, çevrimdışı çalışma, görsel regresyon, E2E ve yayın paketi.

Her sonraki plan, önceki teslimatın gerçek dosya ve arayüzleri üzerinden yazılır. Bu sayede sekiz bağımsız sistem tek seferde tahmine dayalı dosya adlarıyla birbirine kilitlenmez.

## File Structure

| File | Responsibility |
|---|---|
| `src/fusion_cli/runtime_health.py` | Paketli Python çalışmasının hafif, JSON sağlık raporu |
| `src/fusion_cli/cli/app.py` | Gizli `runtime-health` komutunu CLI girişine bağlama |
| `tests/test_runtime_health.py` | Sağlık raporu ve CLI sözleşmesi |
| `desktop_build/__init__.py` | Masaüstü build araçlarının depo-içi Python paketi |
| `desktop_build/runtime/__init__.py` | Runtime build araçlarının paket sınırı |
| `desktop_build/runtime/entrypoint.py` | PyInstaller için tek Fusion giriş noktası |
| `desktop_build/runtime/fusion_runtime.spec` | `onedir` analizi, veri ve dinamik import toplama |
| `desktop_build/runtime/build_runtime.py` | Runtime üretimi, deterministik arşiv ve manifest |
| `desktop_build/runtime/smoke_runtime.py` | Üretilen ikili üzerinde gerçek süreç smoke testi |
| `desktop_build/macos/smoke_app_bundle.py` | `.app` kaynakları ve temiz HOME açılış smoke testi |
| `desktop_build/macos/write_runtime_report.py` | Doğrulanan artifact ölçülerinden sonuç raporu üretme |
| `tests/test_runtime_bundle.py` | Manifest, hedef adı ve deterministik arşiv birim testleri |
| `app/src-tauri/src/runtime_manifest.rs` | Manifest tipleri, çözümleme ve dosya özeti doğrulama |
| `app/src-tauri/src/runtime_paths.rs` | macOS veri, sürüm, geçici ve aktif kayıt yolları |
| `app/src-tauri/src/runtime_installer.rs` | Güvenli çıkarma, dosya doğrulama ve atomik kurulum |
| `app/src-tauri/src/runtime_manager.rs` | Hazırla, sağlık, etkinleştir, onar ve rollback |
| `app/src-tauri/src/core_process.rs` | Yalnız yöneticinin verdiği ikiliyi çalıştırma |
| `app/src-tauri/src/lib.rs` | Runtime Tauri komutları ve başlangıç bağlantısı |
| `app/src/runtime/types.ts` | Frontend runtime durum ve ilerleme tipleri |
| `app/src/runtime/useRuntime.ts` | Tauri runtime komutlarıyla durum makinesi |
| `app/src/runtime/useRuntime.test.tsx` | Hazırlama, hata ve onarım hook testleri |
| `app/src/screens/RuntimeSetup.tsx` | İlk kurulum/onarım kullanıcı arayüzü |
| `app/src/screens/RuntimeSetup.test.tsx` | Erişilebilir kurulum ekranı testleri |
| `app/src/App.tsx` | Protokol istemcisinden önce runtime kapısı |
| `app/src-tauri/tauri.bundle.conf.json` | Yalnız paket build'inde runtime kaynak eşlemesi |
| `app/scripts/run-python.mjs` | Venv varsa onu, CI'da `python3`ü kullanan taşınabilir build sürücüsü |
| `app/package.json` | Test, runtime build ve DMG komutları |
| `app/src-tauri/Cargo.toml` | Arşiv, hash, kilit, hata ve temp bağımlılıkları |
| `.github/workflows/desktop.yml` | macOS uygulama kalite ve paket smoke işi |
| `Makefile` | `app-check`, `runtime-bundle`, `app-package` kapıları |
| `app/KURULUM.md` | Python gerektirmeyen imzasız DMG kurulumu |
| `app/README.md` | Geliştirici çalışma zamanı ve paket komutları |

---

### Task 1: Hafif paket çalışma zamanı sağlık sözleşmesi

**Files:**
- Create: `src/fusion_cli/runtime_health.py`
- Modify: `src/fusion_cli/cli/app.py:392-404`
- Create: `tests/test_runtime_health.py`

**Interfaces:**
- Produces: `RuntimeHealth(version: str, python: str, platform: str, resources_ok: bool)`.
- Produces: `collect_runtime_health() -> RuntimeHealth`.
- Produces: `fusion runtime-health --json` çıktısı; tek JSON nesnesi ve başarıda exit `0`.
- Consumes: `fusion_cli.__version__` ve paketlenmesi zorunlu beş kaynak dosya.

- [ ] **Step 1: Başarısız sağlık testlerini yaz**

`tests/test_runtime_health.py`:

```python
from __future__ import annotations

import json

from typer.testing import CliRunner

from fusion_cli import __version__
from fusion_cli.cli.app import app
from fusion_cli.runtime_health import collect_runtime_health


def test_runtime_health_surumu_ve_paket_kaynaklarini_dogrular():
    health = collect_runtime_health()

    assert health.version == __version__
    assert health.python
    assert health.platform
    assert health.resources_ok is True


def test_runtime_health_json_sozlesmesi_stdoutu_kirletmez():
    result = CliRunner().invoke(app, ["runtime-health", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "platform": payload["platform"],
        "python": payload["python"],
        "resources_ok": True,
        "version": __version__,
    }
```

- [ ] **Step 2: Testlerin doğru nedenle kırıldığını doğrula**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runtime_health.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'fusion_cli.runtime_health'`.

- [ ] **Step 3: Sağlık modelini ve kaynak denetimini uygula**

`src/fusion_cli/runtime_health.py`:

```python
"""Masaüstü paketinin kullanacağı hafif çalışma zamanı sağlık denetimi."""

from __future__ import annotations

import platform
import sys
from dataclasses import asdict, dataclass
from importlib.resources import files
from typing import Any

from . import __version__

_REQUIRED_RESOURCES = (
    "config/defaults.yaml",
    "engines/agent/prompts/system.md",
    "engines/agent/prompts/lessons.txt",
    "engines/fusion/prompts/judge.txt",
    "gateway/dashboard.html",
)


@dataclass(frozen=True)
class RuntimeHealth:
    version: str
    python: str
    platform: str
    resources_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.resources_ok, **asdict(self)}


def collect_runtime_health() -> RuntimeHealth:
    root = files("fusion_cli")
    resources_ok = all(root.joinpath(*relative.split("/")).is_file() for relative in _REQUIRED_RESOURCES)
    return RuntimeHealth(
        version=__version__,
        python=platform.python_version(),
        platform=f"{sys.platform}-{platform.machine()}",
        resources_ok=resources_ok,
    )
```

`src/fusion_cli/cli/app.py` içine `app_protocol` komutundan önce:

```python
@app.command(name="runtime-health", hidden=True)
def runtime_health(as_json: bool = typer.Option(False, "--json")) -> None:
    """Paketli masaüstü çalışma zamanının bütünlüğünü doğrula."""
    import json

    from ..runtime_health import collect_runtime_health

    report = collect_runtime_health()
    if as_json:
        typer.echo(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(f"Fusion runtime {report.version}: {'hazır' if report.resources_ok else 'bozuk'}")
    if not report.resources_ok:
        raise typer.Exit(1)
```

- [ ] **Step 4: Dar ve tam Python kapılarını çalıştır**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runtime_health.py tests/test_packaging.py
.venv/bin/ruff check src/fusion_cli/runtime_health.py src/fusion_cli/cli/app.py tests/test_runtime_health.py
.venv/bin/mypy src/fusion_cli/runtime_health.py src/fusion_cli/cli/app.py
```

Expected: all commands exit `0`.

- [ ] **Step 5: Sağlık sözleşmesini commit et**

```bash
git add src/fusion_cli/runtime_health.py src/fusion_cli/cli/app.py tests/test_runtime_health.py
git commit -m "feat(runtime): paket sağlığı sözleşmesini ekle"
```

---

### Task 2: Deterministik PyInstaller `onedir` paketi

**Files:**
- Create: `desktop_build/__init__.py`
- Create: `desktop_build/runtime/__init__.py`
- Create: `desktop_build/runtime/entrypoint.py`
- Create: `desktop_build/runtime/fusion_runtime.spec`
- Create: `desktop_build/runtime/build_runtime.py`
- Create: `desktop_build/runtime/smoke_runtime.py`
- Create: `tests/test_runtime_bundle.py`
- Modify: `pyproject.toml:30-50`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `fusion_cli.__version__`.
- Produces: `build_runtime(output_dir: Path, work_dir: Path) -> tuple[Path, Path]`.
- Produces: `runtime-manifest.json` and `fusion-runtime.tar.gz`.
- Manifest schema: `schema`, `runtime_version`, `target`, `archive`, `archive_sha256`, `entrypoint`, `files`.
- Every `files` member uses `path`, `kind`, `mode`; regular files add `sha256`, symlinks add `target`.

- [ ] **Step 1: Manifest and target testsini yaz**

`tests/test_runtime_bundle.py`:

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from desktop_build.runtime.build_runtime import build_manifest, macos_target, write_archive


def test_macos_target_mimariyi_tauri_adina_cevirir():
    assert macos_target("arm64") == "aarch64-apple-darwin"
    assert macos_target("x86_64") == "x86_64-apple-darwin"


def test_manifest_dosyalari_sirali_ve_ozetlidir(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    executable = root / "fusion"
    executable.write_bytes(b"runtime")
    executable.chmod(0o755)
    (root / "z.txt").write_text("z", encoding="utf-8")
    archive = tmp_path / "fusion-runtime.tar.gz"
    write_archive(root, archive)

    manifest = build_manifest(root, archive, version="0.3.0a1", target="aarch64-apple-darwin")

    assert manifest["entrypoint"] == "fusion"
    assert [item["path"] for item in manifest["files"]] == ["fusion", "z.txt"]
    assert manifest["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_ayni_girdi_ayni_arsivi_uretir(tmp_path: Path):
    root = tmp_path / "runtime"
    root.mkdir()
    (root / "fusion").write_bytes(b"same")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    write_archive(root, first)
    write_archive(root, second)

    assert first.read_bytes() == second.read_bytes()
```

- [ ] **Step 2: Testlerin build modülü olmadığı için kırıldığını doğrula**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runtime_bundle.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'desktop_build'`.

- [ ] **Step 3: Paketleyici girişini ve PyInstaller tarifini ekle**

`desktop_build/__init__.py` ve `desktop_build/runtime/__init__.py` yalnız paket docstring'i içerir. `desktop_build/runtime/entrypoint.py`:

```python
from fusion_cli.cli.app import main


if __name__ == "__main__":
    main()
```

`desktop_build/runtime/fusion_runtime.spec` ana analizi:

```python
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = []
binaries = []
hiddenimports = []
for package in ("fusion_cli", "litellm", "chromadb", "keyring", "httpx", "mcp"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
for distribution in ("fusion-cli", "litellm", "chromadb", "keyring", "httpx"):
    datas += copy_metadata(distribution)

a = Analysis(
    ["desktop_build/runtime/entrypoint.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="fusion", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="fusion-runtime")
```

`pyproject.toml` içine ayrı build ekstrası ekle; normal geliştirici kurulumuna devasa paketleyiciyi zorunlu kılma:

```toml
desktop = [
    "pyinstaller>=6.15,<7",
]
```

- [ ] **Step 4: Deterministik arşiv ve manifest işlevlerini uygula**

`desktop_build/runtime/build_runtime.py` aşağıdaki halka açık yüzeyi içerir:

```python
def macos_target(machine: str) -> str:
    names = {"arm64": "aarch64-apple-darwin", "aarch64": "aarch64-apple-darwin", "x86_64": "x86_64-apple-darwin"}
    try:
        return names[machine.casefold()]
    except KeyError as error:
        raise ValueError(f"Desteklenmeyen macOS mimarisi: {machine}") from error


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_archive(root: Path, destination: Path) -> None:
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
                    relative = path.relative_to(root).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = 0
                    if info.isfile():
                        with path.open("rb") as source:
                            archive.addfile(info, source)
                    else:
                        archive.addfile(info)


def build_manifest(root: Path, archive: Path, *, version: str, target: str) -> dict[str, object]:
    files = [
        _manifest_entry(path, root)
        for path in sorted(root.rglob("*"))
        if path.is_symlink() or not path.is_dir()
    ]
    return {
        "schema": 1,
        "runtime_version": version,
        "target": target,
        "archive": archive.name,
        "archive_sha256": sha256_file(archive),
        "entrypoint": "fusion",
        "files": files,
    }
```

`_manifest_entry` symlink kontrolünü `is_file` kontrolünden önce yapar; regular dosyalarda `sha256` ve `mode`, dosya veya dizin symlinklerinde `target` üretir. Bir symlink fixture testi manifestte `kind == "symlink"` ve gerçek relative hedefi doğrular. `main()` depo kökünde `python -m PyInstaller --clean --noconfirm desktop_build/runtime/fusion_runtime.spec` çalıştırır, `dist/fusion-runtime` çıktısını arşivler, manifesti `sort_keys=True, indent=2` ile yazar ve her üretimde önce yalnız kendisine ait work/output dizinini temizler.

`pyproject.toml` kalite kapsamına build araçlarını da al:

```toml
[tool.ruff]
src = ["src", "tests", "desktop_build"]

[tool.mypy]
files = ["src", "evals", "prompt_opt", "desktop_build"]
```

- [ ] **Step 5: Gerçek ikili smoke sürücüsünü yaz**

`desktop_build/runtime/smoke_runtime.py`:

```python
import json
import select
import subprocess
from pathlib import Path


def smoke(executable: Path) -> None:
    health = subprocess.run(
        [str(executable), "runtime-health", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(health.stdout)["ok"] is True

    process = subprocess.Popen(
        [str(executable), "app"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    request = {"tip": "istek", "id": "smoke-1", "ad": "oturum.durum", "veri": {}}
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    readable, _, _ = select.select([process.stdout], [], [], 30)
    assert readable, "app protokolü 30 saniyede yanıt vermedi"
    response = json.loads(process.stdout.readline())
    assert response.get("tip") == "sonuc" and response.get("id") == "smoke-1"
    process.stdin.close()
    assert process.wait(timeout=30) == 0
```

- [ ] **Step 6: Birim test ve gerçek paket smoke testini çalıştır**

Run:

```bash
.venv/bin/python -m pip install -e '.[desktop,mcp,gateway]'
.venv/bin/python -m pytest -q tests/test_runtime_bundle.py tests/test_runtime_health.py
.venv/bin/python desktop_build/runtime/build_runtime.py --output app/src-tauri/resources/runtime
.venv/bin/python desktop_build/runtime/smoke_runtime.py app/src-tauri/resources/runtime/unpacked/fusion
```

Expected: testler geçer; `runtime-manifest.json` ile `fusion-runtime.tar.gz` oluşur; smoke exit `0` verir. Build script smoke için `unpacked/` kopyasını output altında bırakır, bu dizin ve iki üretilen paket `.gitignore` ile izlenmez.

- [ ] **Step 7: Paketleyiciyi commit et**

```bash
git add pyproject.toml .gitignore desktop_build tests/test_runtime_bundle.py
git commit -m "build(runtime): bağımsız Python paketini üret"
```

---

### Task 3: Rust manifest ve macOS yol modeli

**Files:**
- Create: `app/src-tauri/src/runtime_manifest.rs`
- Create: `app/src-tauri/src/runtime_paths.rs`
- Modify: `app/src-tauri/src/lib.rs:1-4`
- Modify: `app/src-tauri/Cargo.toml:20-24`

**Interfaces:**
- Produces: `RuntimeManifest::read(path: &Path) -> Result<RuntimeManifest, RuntimeError>`.
- Produces: `RuntimeManifest::validate(target: &str) -> Result<(), RuntimeError>`.
- Produces: `RuntimePaths::for_home(home: &Path) -> RuntimePaths`.
- Produces: `safe_relative(path: &Path) -> Result<PathBuf, RuntimeError>`.
- Runtime root is exactly `~/Library/Application Support/Fusion/runtime` on macOS.

- [ ] **Step 1: Manifest ve yol birim testlerini önce yaz**

`runtime_manifest.rs` test modülü:

```rust
#[test]
fn manifest_surumu_hedefi_ve_giris_noktasini_okur() {
    let manifest: RuntimeManifest = serde_json::from_str(r#"{
      "schema":1,"runtime_version":"0.3.0a1","target":"aarch64-apple-darwin",
      "archive":"fusion-runtime.tar.gz","archive_sha256":"aa","entrypoint":"fusion","files":[]
    }"#).unwrap();
    assert_eq!(manifest.runtime_version, "0.3.0a1");
    assert_eq!(manifest.entrypoint, PathBuf::from("fusion"));
}

#[test]
fn ust_dizine_cikan_manifest_yolu_reddedilir() {
    assert!(safe_relative(Path::new("../../.ssh/id_rsa")).is_err());
    assert!(safe_relative(Path::new("/tmp/fusion")).is_err());
    assert_eq!(safe_relative(Path::new("_internal/lib.dylib")).unwrap(), PathBuf::from("_internal/lib.dylib"));
}
```

`runtime_paths.rs` test modülü:

```rust
#[test]
fn macos_runtime_koku_fusion_application_support_altindadir() {
    let paths = RuntimePaths::for_home(Path::new("/Users/ada"));
    assert_eq!(paths.root, PathBuf::from("/Users/ada/Library/Application Support/Fusion/runtime"));
    assert_eq!(paths.active_record, paths.root.join("active-runtime.json"));
    assert_eq!(paths.lock_file, paths.root.join("runtime.lock"));
}
```

- [ ] **Step 2: Rust testlerinin modüller olmadığı için kırıldığını doğrula**

Run:

```bash
cd app/src-tauri && cargo test runtime_manifest runtime_paths
```

Expected: FAIL because modules are not defined.

- [ ] **Step 3: Tipleri ve güvenli yol doğrulamasını uygula**

`runtime_manifest.rs` temel tipleri:

```rust
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

#[derive(Debug, Clone, Deserialize)]
pub struct RuntimeFile {
    pub path: PathBuf,
    pub kind: RuntimeFileKind,
    pub mode: u32,
    pub sha256: Option<String>,
    pub target: Option<PathBuf>,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeFileKind { File, Symlink }

pub fn safe_relative(path: &Path) -> Result<PathBuf, RuntimeError> {
    if path.is_absolute() || path.components().any(|part| !matches!(part, Component::Normal(_))) {
        return Err(RuntimeError::UnsafePath(path.to_path_buf()));
    }
    Ok(path.to_path_buf())
}
```

`RuntimeError` bu modülde `thiserror::Error` ile `ManifestRead`, `ManifestDecode`, `UnsupportedSchema`, `TargetMismatch`, `UnsafePath`, `HashMismatch`, `Io`, `Archive`, `Health`, `NoHealthyRuntime` varyantlarını tanımlar. Hata `Display` metinleri Türkçedir ve sır/değer içeriği taşımaz.

`runtime_paths.rs`:

```rust
#[derive(Debug, Clone)]
pub struct RuntimePaths {
    pub root: PathBuf,
    pub active_record: PathBuf,
    pub lock_file: PathBuf,
}

impl RuntimePaths {
    pub fn for_home(home: &Path) -> Self {
        let root = home.join("Library").join("Application Support").join("Fusion").join("runtime");
        Self { active_record: root.join("active-runtime.json"), lock_file: root.join("runtime.lock"), root }
    }

    pub fn version_dir(&self, version: &str) -> PathBuf { self.root.join(version) }
    pub fn staging_dir(&self, version: &str, nonce: u32) -> PathBuf {
        self.root.join(format!(".install-{version}-{nonce}"))
    }
}
```

- [ ] **Step 4: Bağımlılıkları ve modülleri bağla**

`Cargo.toml`:

```toml
flate2 = "1"
fs2 = "0.4"
hex = "0.4"
sha2 = "0.10"
tar = "0.4"
tempfile = "3"
thiserror = "2"
```

`lib.rs` başına:

```rust
mod runtime_manifest;
mod runtime_paths;
```

- [ ] **Step 5: Rust kapısını ve commit'i tamamla**

```bash
cd app/src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test
cd ../..
git add app/src-tauri/Cargo.toml app/src-tauri/Cargo.lock app/src-tauri/src/runtime_manifest.rs app/src-tauri/src/runtime_paths.rs app/src-tauri/src/lib.rs
git commit -m "feat(runtime): manifest ve macOS yollarını tanımla"
```

---

### Task 4: Güvenli, kilitli ve atomik runtime kurulumu

**Files:**
- Create: `app/src-tauri/src/runtime_installer.rs`
- Modify: `app/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: `RuntimeManifest`, `RuntimePaths`, `RuntimeError`.
- Produces: `RuntimeResources { manifest_path: PathBuf, archive_path: PathBuf }`.
- Produces: `InstalledRuntime { version: String, directory: PathBuf, executable: PathBuf }`.
- Produces: `install(resources, paths, expected_target, validate, progress) -> Result<InstalledRuntime, RuntimeError>`; `validate` staging içindeki executable üzerinde çalışır ve geçmeden sürüm dizini değiştirilmez.
- Progress callback receives `RuntimeProgress { stage, completed, total, message }`.

`runtime_installer.rs` owns the progress wire type because installation is its producer:

```rust
#[derive(Debug, Clone, Serialize)]
pub struct RuntimeProgress {
    pub stage: String,
    pub completed: u64,
    pub total: u64,
    pub message: String,
}
```

- [ ] **Step 1: Kötü arşiv, hash ve atomiklik testlerini yaz**

`runtime_installer.rs` test modülü üç gerçek temp dizin senaryosu içerir:

```rust
#[test]
fn archive_hash_uyusmazsa_hedef_dizin_olusmaz() {
    let fixture = RuntimeFixture::new().with_archive_bytes(b"bozuk").with_manifest_hash("00");
    let result = install(&fixture.resources, &fixture.paths, TEST_TARGET, |_| Ok(()), |_| {});
    assert!(matches!(result, Err(RuntimeError::HashMismatch { .. })));
    assert!(!fixture.paths.version_dir(TEST_VERSION).exists());
}

#[test]
fn path_traversal_girdisi_runtime_kokunun_disina_cikamaz() {
    let fixture = RuntimeFixture::new().with_tar_file("../../escaped", b"no");
    assert!(matches!(install(&fixture.resources, &fixture.paths, TEST_TARGET, |_| Ok(()), |_| {}), Err(RuntimeError::UnsafePath(_))));
    assert!(!fixture.temp.path().join("escaped").exists());
}

#[test]
fn basarili_kurulum_once_staginge_yazip_surume_tasir() {
    let fixture = RuntimeFixture::valid();
    let installed = install(&fixture.resources, &fixture.paths, TEST_TARGET, |_| Ok(()), |_| {}).unwrap();
    assert_eq!(installed.executable, fixture.paths.version_dir(TEST_VERSION).join("fusion"));
    assert!(installed.executable.exists());
    assert!(std::fs::read_dir(&fixture.paths.root).unwrap().all(|item| !item.unwrap().file_name().to_string_lossy().starts_with(".install-")));
}
```

`RuntimeFixture` test yardımcısı aynı modülde gerçek, küçük gzip/tar ve manifest üretir; production kodunu mocklamaz.

- [ ] **Step 2: Testlerin installer olmadığı için kırıldığını doğrula**

Run:

```bash
cd app/src-tauri && cargo test runtime_installer
```

Expected: FAIL because `runtime_installer` is not defined.

- [ ] **Step 3: Kilit ve arşiv doğrulamasını uygula**

Kurulum sırası kodda aşağıdaki kesin sırayı izler:

```rust
pub fn install(
    resources: &RuntimeResources,
    paths: &RuntimePaths,
    expected_target: &str,
    validate: impl FnOnce(&Path) -> Result<(), RuntimeError>,
    mut progress: impl FnMut(RuntimeProgress),
) -> Result<InstalledRuntime, RuntimeError> {
    std::fs::create_dir_all(&paths.root)?;
    let lock = OpenOptions::new().create(true).read(true).write(true).open(&paths.lock_file)?;
    lock.lock_exclusive()?;

    let manifest = RuntimeManifest::read(&resources.manifest_path)?;
    manifest.validate(expected_target)?;
    verify_sha256(&resources.archive_path, &manifest.archive_sha256)?;

    let staging = paths.staging_dir(&manifest.runtime_version, std::process::id());
    remove_owned_staging(&staging, &paths.root)?;
    std::fs::create_dir_all(&staging)?;
    extract_checked(&resources.archive_path, &staging, &mut progress)?;
    verify_tree(&manifest, &staging, &mut progress)?;

    let executable = staging.join(safe_relative(&manifest.entrypoint)?);
    ensure_executable(&executable)?;
    validate(&executable)?;
    let destination = paths.version_dir(&manifest.runtime_version);
    replace_version_atomically(&staging, &destination, &paths.root)?;
    Ok(InstalledRuntime { version: manifest.runtime_version, executable: destination.join(manifest.entrypoint), directory: destination })
}
```

`extract_checked` yalnız directory, regular file ve güvenli relative symlink kabul eder. Absolute link, kök dışına çözülen `..` linki, device, FIFO ve hard link `RuntimeError::UnsafePath` döndürür. Regular dosya ve symlink hedefi manifest ile birebir doğrulanır. Kurulum hatasında yalnız `RuntimePaths::staging_dir` ile üretilmiş, `paths.root` altında olduğu tekrar doğrulanmış staging dizini temizlenir.

Bir ek test `validate` closure'ı `RuntimeError::Health("smoke başarısız".into())` döndürdüğünde mevcut aynı-sürüm destination içeriğinin değişmediğini ve staging dizininin temizlendiğini doğrular. Böylece sağlık kapısı atomik değişimin önündedir.

- [ ] **Step 4: Aynı sürümü güvenli değiştirme davranışını ekle**

`replace_version_atomically` mevcut aynı sürümü doğrudan silmez:

```rust
fn replace_version_atomically(staging: &Path, destination: &Path, root: &Path) -> Result<(), RuntimeError> {
    ensure_child(destination, root)?;
    let quarantine = root.join(format!(".replaced-{}-{}", destination.file_name().unwrap().to_string_lossy(), std::process::id()));
    if destination.exists() { std::fs::rename(destination, &quarantine)?; }
    if let Err(error) = std::fs::rename(staging, destination) {
        if quarantine.exists() { std::fs::rename(&quarantine, destination)?; }
        return Err(error.into());
    }
    if quarantine.exists() { std::fs::remove_dir_all(quarantine)?; }
    Ok(())
}
```

- [ ] **Step 5: Installer test ve kalite kapısını çalıştır**

```bash
cd app/src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test runtime_installer
cargo test
```

Expected: all commands exit `0`; temp fixtures outside their own root are unchanged.

- [ ] **Step 6: Installerı commit et**

```bash
cd ../..
git add app/src-tauri/src/runtime_installer.rs app/src-tauri/src/lib.rs
git commit -m "feat(runtime): çalışma zamanını atomik kur"
```

---

### Task 5: Sağlık, etkin sürüm, onarım ve rollback yöneticisi

**Files:**
- Create: `app/src-tauri/src/runtime_manager.rs`
- Modify: `app/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: `install(..., validate, progress) -> InstalledRuntime`.
- Produces: `HealthProbe::check(executable: &Path) -> Result<RuntimeHealthReport, RuntimeError>`.
- Produces: `CommandHealthProbe`; doğruladığı ikiliyi `runtime-health --json` argümanlarıyla ve 30 saniye zaman aşımıyla çalıştırır.
- Produces: `RuntimeManager::prepare`, `status`, `repair`, `executable`.
- Active record shape: `{ "schema": 1, "active": "0.3.0a1", "previous": "0.2.9" }` where `previous` may be null.

The manager's public types are fixed here so later tasks consume the same names:

```rust
#[derive(Debug, Clone)]
pub struct RuntimeReady {
    pub version: String,
    pub executable: PathBuf,
    pub source: RuntimeSource,
}

#[derive(Debug, Clone, PartialEq)]
pub enum RuntimeSource { Bundled, Developer }

#[derive(Debug, Clone, Deserialize)]
pub struct RuntimeHealthReport {
    pub ok: bool,
    pub version: String,
    pub python: String,
    pub platform: String,
    pub resources_ok: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct RuntimeStatus {
    pub state: String,
    pub version: Option<String>,
    pub message: String,
    pub can_repair: bool,
}

impl RuntimeStatus {
    pub fn ready(runtime: RuntimeReady) -> Self {
        Self { state: "hazir".into(), version: Some(runtime.version), message: "Fusion hazır".into(), can_repair: false }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct ActiveRecord {
    pub schema: u32,
    pub active: String,
    pub previous: Option<String>,
}

impl ActiveRecord {
    pub fn new(active: &str, previous: Option<&str>) -> Self {
        Self { schema: 1, active: active.into(), previous: previous.map(str::to_owned) }
    }
}
```

`RuntimeManager::executable() -> Result<PathBuf, RuntimeError>` returns a path only after `prepare` or `repair` has installed and probed a healthy runtime. `RuntimeResources::from_app(&AppHandle)` resolves `resource_dir()/runtime/runtime-manifest.json` and `resource_dir()/runtime/fusion-runtime.tar.gz`; debug development may instead use the explicit resource directory argument supplied by tests.

- [ ] **Step 1: Etkinleştirme ve rollback testlerini yaz**

`runtime_manager.rs` test modülü:

```rust
#[test]
fn yeni_surum_saglikliysa_etkin_previous_eski_surum_olur() {
    let fixture = ManagerFixture::with_active("0.2.9");
    fixture.probe.pass("0.3.0a1");
    let ready = fixture.manager.prepare(|_| {}).unwrap();
    assert_eq!(ready.version, "0.3.0a1");
    assert_eq!(fixture.active_record(), ActiveRecord::new("0.3.0a1", Some("0.2.9")));
}

#[test]
fn yeni_surum_sagliksizsa_aktif_kayit_degismez() {
    let fixture = ManagerFixture::with_active("0.2.9");
    fixture.probe.fail("0.3.0a1");
    fixture.probe.pass("0.2.9");
    let ready = fixture.manager.prepare(|_| {}).unwrap();
    assert_eq!(ready.version, "0.2.9");
    assert_eq!(fixture.active_record().active, "0.2.9");
}

#[test]
fn aktif_runtime_bozuksa_onceki_saglikli_surume_doner() {
    let fixture = ManagerFixture::with_record("0.3.0a1", Some("0.2.9"));
    fixture.probe.fail("0.3.0a1");
    fixture.probe.pass("0.2.9");
    let ready = fixture.manager.prepare(|_| {}).unwrap();
    assert_eq!(ready.version, "0.2.9");
    assert_eq!(fixture.active_record().active, "0.2.9");
}

#[test]
fn repair_kullanici_verisine_dokunmadan_paket_surumu_yeniden_kurar() {
    let fixture = ManagerFixture::with_corrupt_packaged_version();
    let user_config = fixture.application_support.join("config.yaml");
    std::fs::write(&user_config, "keep").unwrap();
    fixture.manager.repair(|_| {}).unwrap();
    assert_eq!(std::fs::read_to_string(user_config).unwrap(), "keep");
}
```

- [ ] **Step 2: Testin manager olmadığı için kırıldığını doğrula**

Run:

```bash
cd app/src-tauri && cargo test runtime_manager
```

Expected: FAIL because module and types are absent.

- [ ] **Step 3: Sağlık probe'unu uygula**

```rust
pub trait HealthProbe: Send + Sync {
    fn check(&self, executable: &Path) -> Result<RuntimeHealthReport, RuntimeError>;
}

impl HealthProbe for CommandHealthProbe {
    fn check(&self, executable: &Path) -> Result<RuntimeHealthReport, RuntimeError> {
        let output = run_with_timeout(executable, &["runtime-health", "--json"], Duration::from_secs(30))?;
        if !output.status.success() { return Err(RuntimeError::Health("sağlık komutu başarısız".into())); }
        let report: RuntimeHealthReport = serde_json::from_slice(&output.stdout)
            .map_err(RuntimeError::HealthDecode)?;
        if !report.ok { return Err(RuntimeError::Health("paket kaynakları eksik".into())); }
        Ok(report)
    }
}
```

`run_with_timeout` child'i `try_wait` ile 50 ms aralıkta yoklar; 30 saniyede çıkmazsa `kill` + `wait` yapıp `RuntimeError::HealthTimeout` döndürür. Stderr yalnız uygulama tanılama günlüğüne en fazla 8 KiB ve sır maskesinden geçirilerek yazılır; kullanıcı hata metnine ham stderr eklenmez.

- [ ] **Step 4: Aktif kayıt ve prepare sırasını uygula**

`RuntimeManager::prepare` paket içindeki sürümü eski ama sağlıklı aktif sürümden önce dener. Böylece uygulama güncellemesi yeni runtime'ı gerçekten kurar; yeni paket bozuksa eski sağlıklı sürüm korunur:

```rust
pub fn prepare(&self, progress: impl FnMut(RuntimeProgress)) -> Result<RuntimeReady, RuntimeError> {
    let record = self.read_active()?;
    let packaged_version = RuntimeManifest::read(&self.resources.manifest_path)?.runtime_version;
    if record.as_ref().is_some_and(|item| item.active == packaged_version) {
        if let Ok(active) = self.healthy_version(&packaged_version) { return Ok(active); }
    }

    match install(
        &self.resources,
        &self.paths,
        &self.expected_target,
        |executable| self.probe.check(executable).map(|_| ()),
        progress,
    ) {
        Ok(installed) => {
            let previous = record.as_ref().and_then(|item| {
                if item.active != installed.version { Some(item.active.as_str()) }
                else { item.previous.as_deref() }
            });
            self.write_active_atomic(&ActiveRecord::new(&installed.version, previous))?;
            Ok(installed.into())
        }
        Err(install_error) => self.fallback_or_error(record, install_error),
    }
}

fn fallback_or_error(&self, record: Option<ActiveRecord>, error: RuntimeError) -> Result<RuntimeReady, RuntimeError> {
    for version in record.into_iter().flat_map(|item| [Some(item.active), item.previous]).flatten() {
        if let Ok(ready) = self.healthy_version(&version) {
            self.write_active_atomic(&ActiveRecord::new(&version, None))?;
            return Ok(ready);
        }
    }
    Err(error)
}
```

`write_active_atomic` kaydı aynı dizindeki `active-runtime.json.tmp-{process_id}` dosyasına yazıp `sync_all` yaptıktan sonra `rename` eder. `repair` paket sürümünü installerın aynı-sürüm karantina yoluyla yeniden kurar, probe geçmeden etkin kaydı değiştirmez.

- [ ] **Step 5: Manager testlerini ve tüm Rust kapısını çalıştır**

```bash
cd app/src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test runtime_manager
cargo test
```

Expected: all tests pass, timeout child leaves no process behind.

- [ ] **Step 6: Managerı commit et**

```bash
cd ../..
git add app/src-tauri/src/runtime_manager.rs app/src-tauri/src/lib.rs app/src-tauri/Cargo.lock
git commit -m "feat(runtime): sağlık onarım ve geri dönüşü yönet"
```

---

### Task 6: Çekirdek sürecini yalnız doğrulanmış runtime'a bağlama

**Files:**
- Modify: `app/src-tauri/src/core_process.rs:22-262`
- Modify: `app/src-tauri/src/lib.rs:1-30`

**Interfaces:**
- Consumes: `RuntimeManager::executable() -> Result<PathBuf, RuntimeError>`.
- Produces: `CoreProcess::start(app: AppHandle, executable: &Path) -> Result<(), String>`.
- Produces: `CoreLaunch { executable: PathBuf, args: Vec<String> }` for pure tests.
- Removes: `cekirdek_yolunu_bul`, `sidecar_yolu`, HOME/Homebrew/PATH scanning and `KURULUM_MESAJI`.

- [ ] **Step 1: Release'in sistem runtime'ına düşmediğini kanıtlayan testleri yaz**

Mevcut sistem yol testlerini aşağıdaki sözleşmeyle değiştir:

```rust
#[test]
fn cekirdek_komutu_yalniz_verilen_runtimei_kullanir() {
    let launch = core_launch(Path::new("/Application Support/Fusion/runtime/0.3.0a1/fusion"));
    assert_eq!(launch.executable, PathBuf::from("/Application Support/Fusion/runtime/0.3.0a1/fusion"));
    assert_eq!(launch.args, vec!["app"]);
}

#[test]
fn paketli_runtime_yolu_yoksa_path_aramasi_yapilmaz() {
    let missing = Path::new("/missing/fusion");
    let error = validate_runtime_executable(missing).unwrap_err();
    assert!(error.contains("Çalışma zamanı hazır değil"));
}
```

- [ ] **Step 2: Eski testlerin yeni sözleşmede kırıldığını doğrula**

Run:

```bash
cd app/src-tauri && cargo test core_process
```

Expected: FAIL until old resolver is removed and new functions exist.

- [ ] **Step 3: Spawn sınırını sadeleştir**

`core_process.rs`:

```rust
#[derive(Debug, PartialEq)]
struct CoreLaunch { executable: PathBuf, args: Vec<String> }

fn core_launch(executable: &Path) -> CoreLaunch {
    CoreLaunch { executable: executable.to_path_buf(), args: vec!["app".to_string()] }
}

fn validate_runtime_executable(path: &Path) -> Result<(), String> {
    if dosya_calistirilabilir_mi(path) { Ok(()) }
    else { Err("Çalışma zamanı hazır değil. Ayarlar > Çalışma Zamanı bölümünden onarın.".into()) }
}

pub fn start(&self, app: AppHandle, executable: &Path) -> Result<(), String> {
    validate_runtime_executable(executable)?;
    let launch = core_launch(executable);
    let mut child = Command::new(&launch.executable)
        .args(&launch.args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("Fusion çalışma zamanı başlatılamadı: {error}"))?;
    // Var olan child/stdin kilidi, satır emitterı ve iki saniyelik kapanış yolu korunur.
```

Bu aşamada stderr `Stdio::null()` kalır; böylece sır sızıntısı ve sınırsız günlük büyümesi oluşmaz. Yapılandırılmış, maskeli tanılama günlükleri F aşamasındaki tanılama sınırında eklenir. Stdout yalnız JSON protokolüne ayrılmış kalır.

- [ ] **Step 4: Tauri start komutunu runtime yöneticisine bağla**

`lib.rs`:

```rust
#[tauri::command]
fn cekirdek_baslat(
    app: tauri::AppHandle,
    runtime: tauri::State<RuntimeManager>,
    process: tauri::State<CoreProcess>,
) -> Result<(), String> {
    let executable = runtime.executable().map_err(|error| error.to_string())?;
    process.start(app, &executable)
}
```

Debug geliştirmede `RuntimeManager` yalnız `FUSION_DEVELOPER_RUNTIME` tam yolu açıkça verilmişse `RuntimeSource::Developer` döndürebilir. Release derlemesinde bu env değişkeni koşulsuz yok sayılır.

- [ ] **Step 5: Rust regresyon kapısını çalıştır ve commit et**

```bash
cd app/src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
cd ../..
git add app/src-tauri/src/core_process.rs app/src-tauri/src/lib.rs
git commit -m "refactor(app): çekirdeği doğrulanmış runtime ile başlat"
```

---

### Task 7: Tauri runtime komutları ve React başlangıç kapısı

**Files:**
- Modify: `app/src-tauri/src/lib.rs`
- Create: `app/src/runtime/types.ts`
- Create: `app/src/runtime/useRuntime.ts`
- Create: `app/src/runtime/useRuntime.test.tsx`
- Create: `app/src/screens/RuntimeSetup.tsx`
- Create: `app/src/screens/RuntimeSetup.test.tsx`
- Modify: `app/src/App.tsx:64-99`
- Modify: `app/package.json:6-11`

**Interfaces:**
- Produces Tauri commands: `runtime_durum`, `runtime_hazirla`, `runtime_onar`.
- Emits: `runtime-ilerleme` with `RuntimeProgress`.
- Produces TypeScript `RuntimeState = "denetleniyor" | "kuruluyor" | "hazir" | "onarilabilir" | "hata"`.
- `cekirdek_baslat` is invoked only after state `hazir`.

- [ ] **Step 1: Runtime ekranı ve hook testlerini yaz**

`app/src/screens/RuntimeSetup.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RuntimeSetup } from "./RuntimeSetup";

describe("RuntimeSetup", () => {
  it("kurulum ilerlemesini erişilebilir biçimde gösterir", () => {
    render(<RuntimeSetup state="kuruluyor" progress={42} message="Fusion hazırlanıyor" onRepair={vi.fn()} />);
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("42");
    expect(screen.getByText("Fusion hazırlanıyor")).toBeTruthy();
  });

  it("onarılabilir hatada tek onarım eylemi sunar", () => {
    const repair = vi.fn();
    render(<RuntimeSetup state="onarilabilir" progress={0} message="Dosyalar eksik" onRepair={repair} />);
    fireEvent.click(screen.getByRole("button", { name: "Çalışma zamanını onar" }));
    expect(repair).toHaveBeenCalledOnce();
  });
});
```

`app/src/runtime/useRuntime.test.tsx` test taşıması `status`, `prepare`, `repair`, `listenProgress` fonksiyonları enjekte edilen bir hook harness kullanır ve şunları doğrular:

```tsx
it("hazır değilse prepare çalıştırıp hazır duruma geçer", async () => {
  const transport = fakeRuntimeTransport(
    { state: "eksik", message: "Kurulum gerekli", can_repair: false },
    { state: "hazir", version: "0.3.0a1", message: "Hazır", can_repair: false },
  );
  const { result } = renderHook(() => useRuntime(transport));
  await waitFor(() => expect(result.current.state).toBe("hazir"));
  expect(transport.prepare).toHaveBeenCalledOnce();
});

it("kurulum hatasını onarılabilir durumda tutar", async () => {
  const transport = failingRuntimeTransport("Arşiv özeti uyuşmuyor");
  const { result } = renderHook(() => useRuntime(transport));
  await waitFor(() => expect(result.current.state).toBe("onarilabilir"));
  expect(result.current.message).toContain("Arşiv özeti uyuşmuyor");
});
```

- [ ] **Step 2: Frontend test komutunu ekle ve kırmızı testleri çalıştır**

`package.json` scripts:

```json
"test": "vitest run",
"test:watch": "vitest"
```

Run:

```bash
cd app && npm test -- src/screens/RuntimeSetup.test.tsx src/runtime/useRuntime.test.tsx
```

Expected: FAIL because components and hook do not exist.

- [ ] **Step 3: Tauri komutlarını non-blocking biçimde uygula**

`lib.rs` komut yüzeyi:

```rust
#[tauri::command]
async fn runtime_hazirla(app: tauri::AppHandle, manager: tauri::State<'_, RuntimeManager>) -> Result<RuntimeStatus, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        manager.prepare(|progress| { let _ = app.emit("runtime-ilerleme", progress); })
            .map(RuntimeStatus::ready)
            .map_err(|error| error.to_string())
    }).await.map_err(|error| format!("Çalışma zamanı görevi tamamlanamadı: {error}"))?
}

#[tauri::command]
async fn runtime_onar(app: tauri::AppHandle, manager: tauri::State<'_, RuntimeManager>) -> Result<RuntimeStatus, String> {
    let manager = manager.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        manager.repair(|progress| { let _ = app.emit("runtime-ilerleme", progress); })
            .map(RuntimeStatus::ready)
            .map_err(|error| error.to_string())
    }).await.map_err(|error| format!("Onarım görevi tamamlanamadı: {error}"))?
}
```

`RuntimeManager` `Arc` iç durumuyla `Clone` olur. `runtime_durum` dosya değiştirmeyen senkron durum anlık görüntüsü döndürür.

- [ ] **Step 4: Hook ve kurulum ekranını uygula**

`app/src/runtime/types.ts`:

```typescript
export type RuntimeState = "denetleniyor" | "kuruluyor" | "hazir" | "onarilabilir" | "hata";
export interface RuntimeProgress { stage: string; completed: number; total: number; message: string }
export interface RuntimeBackendStatus { state: "eksik" | "hazir" | "onarilabilir" | "hata"; version?: string; message: string; can_repair: boolean }
export interface RuntimeView { state: RuntimeState; progress: number; message: string; version?: string }
```

`useRuntime` mount sırasında ilerleme dinleyicisini önce kurar, sonra `runtime_durum` ve gerekirse `runtime_hazirla` çağırır. Hook `completed / max(total, 1)` oranını yüzdeye çevirir ve `message` alanını ekrana taşır. Unmount bütün dinleyicileri bırakır; React StrictMode çift mount'u iki kurulum başlatmaz çünkü Rust manager aynı runtime lock'unu kullanır.

`RuntimeSetup` beyaz zemin, merkezde Fusion işareti, başlık, tek satır açıklama, semantik `<progress>` ve yalnız hata halinde onarım düğmesi gösterir. Teknik arşiv yolu ana metne yazılmaz; **Ayrıntılar** açılır alanında gösterilir.

- [ ] **Step 5: `App` başlangıç sırasını runtime kapısına bağla**

`App.tsx` karar sırası:

```tsx
const runtime = useRuntime();
if (runtime.state !== "hazir") {
  return <RuntimeSetup {...runtime} onRepair={runtime.repair} />;
}
return <CoreConnectedApp />;
```

Mevcut `ProtocolClient` oluşturan effect ayrı `CoreConnectedApp` bileşenine taşınır. Böylece runtime hazır olmadan `cekirdek_baslat` çağrısı fiziksel olarak render ağacında bulunmaz.

- [ ] **Step 6: Frontend ve Rust kapılarını çalıştır**

```bash
cd app
npm test
npm run build
cd src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
```

Expected: all commands exit `0`; existing conversation and approval tests remain green.

- [ ] **Step 7: Runtime başlangıç deneyimini commit et**

```bash
cd ../../..
git add app/package.json app/package-lock.json app/src app/src-tauri/src/lib.rs
git commit -m "feat(app): çalışma zamanı kurulum ekranını bağla"
```

---

### Task 8: Tauri kaynak paketi ve DMG build zinciri

**Files:**
- Create: `app/src-tauri/tauri.bundle.conf.json`
- Create: `app/scripts/run-python.mjs`
- Modify: `app/src-tauri/tauri.conf.json:3-37`
- Modify: `app/src-tauri/Cargo.toml:1-6`
- Modify: `app/package.json`
- Modify: `.gitignore`
- Create: `tests/test_desktop_version.py`

**Interfaces:**
- Consumes: `app/src-tauri/resources/runtime/runtime-manifest.json` and `fusion-runtime.tar.gz`.
- Produces: `npm run bundle:mac`.
- Produces: `app/src-tauri/target/release/bundle/macos/Fusion.app` and `.../dmg/*.dmg`.
- Product version maps Python `0.3.0a1` to SemVer `0.3.0-alpha.1`.

- [ ] **Step 1: Sürüm ve bundle config sözleşme testini yaz**

`tests/test_desktop_version.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from fusion_cli import __version__


def test_macos_uygulama_surumu_python_surumuyle_eslesir():
    root = Path(__file__).resolve().parents[1]
    tauri = json.loads((root / "app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    expected = __version__.replace("a", "-alpha.")
    assert tauri["version"] == expected


def test_bundle_config_runtime_manifestini_ve_arsivini_ekler():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "app/src-tauri/tauri.bundle.conf.json").read_text(encoding="utf-8"))
    resources = config["bundle"]["resources"]
    assert resources["resources/runtime/runtime-manifest.json"] == "runtime/runtime-manifest.json"
    assert resources["resources/runtime/fusion-runtime.tar.gz"] == "runtime/fusion-runtime.tar.gz"
```

- [ ] **Step 2: Testin eksik config ve sürüm farkıyla kırıldığını doğrula**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_desktop_version.py
```

Expected: FAIL because bundle config is absent and app version is `0.1.0`.

- [ ] **Step 3: Ürün metadata ve kaynak overlay'ini ekle**

`tauri.conf.json`:

```json
{
  "productName": "Fusion",
  "version": "0.3.0-alpha.1",
  "identifier": "com.fusion.desktop"
}
```

`tauri.bundle.conf.json`:

```json
{
  "bundle": {
    "targets": ["app", "dmg"],
    "resources": {
      "resources/runtime/runtime-manifest.json": "runtime/runtime-manifest.json",
      "resources/runtime/fusion-runtime.tar.gz": "runtime/fusion-runtime.tar.gz"
    },
    "macOS": { "minimumSystemVersion": "12.0", "signingIdentity": null }
  }
}
```

`Cargo.toml` metadata `name = "fusion-desktop"`, `description = "Fusion yapay zekâ çalışma alanı"`, `authors = ["Fusion"]` olur. Crate lib adı `app_lib` bu aşamada değiştirilmez; gereksiz import kırılması yaratılmaz.

- [ ] **Step 4: Build scriptlerini bağla**

`app/scripts/run-python.mjs` geliştirici venv'ini ve CI Python'unu aynı komutta destekler:

```javascript
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const localPython = new URL("../../.venv/bin/python", import.meta.url).pathname;
const python = process.env.FUSION_BUILD_PYTHON || (existsSync(localPython) ? localPython : "python3");
const result = spawnSync(python, process.argv.slice(2), { stdio: "inherit" });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
```

`app/package.json` scripts:

```json
"runtime:build": "node scripts/run-python.mjs ../desktop_build/runtime/build_runtime.py --output src-tauri/resources/runtime",
"runtime:smoke": "node scripts/run-python.mjs ../desktop_build/runtime/smoke_runtime.py src-tauri/resources/runtime/unpacked/fusion",
"bundle:mac": "npm run runtime:build && npm run runtime:smoke && tauri build --config src-tauri/tauri.bundle.conf.json --bundles app,dmg",
"check": "npm test && npm run build && cd src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test"
```

`.gitignore` yalnız üretilen yolları dışlar:

```gitignore
app/src-tauri/resources/runtime/runtime-manifest.json
app/src-tauri/resources/runtime/fusion-runtime.tar.gz
app/src-tauri/resources/runtime/unpacked/
desktop_build/runtime/work/
```

Klasörü depoda tutmak için `app/src-tauri/resources/runtime/README.md`, buranın build çıktısı olduğunu ve binary'nin commit edilmeyeceğini açıklar.

- [ ] **Step 5: Bundle kaynak çözümlemesini gerçek `.app` üzerinde doğrula**

Run:

```bash
cd app
npm run bundle:mac
test -x src-tauri/target/release/bundle/macos/Fusion.app/Contents/MacOS/fusion-desktop
test -f src-tauri/target/release/bundle/macos/Fusion.app/Contents/Resources/runtime/runtime-manifest.json
test -f src-tauri/target/release/bundle/macos/Fusion.app/Contents/Resources/runtime/fusion-runtime.tar.gz
find src-tauri/target/release/bundle/dmg -name '*.dmg' -type f -maxdepth 1 | grep -q .
```

Expected: all checks exit `0` and no system `fusion` path is copied into the app.

- [ ] **Step 6: Build zincirini commit et**

```bash
cd ..
git add .gitignore app/package.json app/package-lock.json app/scripts/run-python.mjs app/src-tauri/Cargo.toml app/src-tauri/Cargo.lock app/src-tauri/tauri.conf.json app/src-tauri/tauri.bundle.conf.json app/src-tauri/resources/runtime/README.md tests/test_desktop_version.py
git commit -m "build(app): paketli runtime ile DMG üret"
```

---

### Task 9: Paketlenmiş uygulama smoke testi ve kurulum belgeleri

**Files:**
- Create: `desktop_build/macos/__init__.py`
- Create: `desktop_build/macos/smoke_app_bundle.py`
- Modify: `app/KURULUM.md`
- Modify: `app/README.md`
- Modify: `Makefile`
- Create: `.github/workflows/desktop.yml`
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Produces: `.venv/bin/python desktop_build/macos/smoke_app_bundle.py app/src-tauri/target/release/bundle/macos/Fusion.app`.
- Produces: `make app-check`, `make runtime-bundle`, `make app-package`.
- CI artifact: unsigned macOS `.app` and `.dmg`; kullanıcıya release olarak otomatik yayımlanmaz.

- [ ] **Step 1: Kurulum belgesi sözleşme testini yaz**

`tests/test_packaging.py` sonuna:

```python
def test_macos_kurulumu_cli_ve_python_onkosulu_istemez():
    root = Path(__file__).resolve().parents[1]
    guide = (root / "app/KURULUM.md").read_text(encoding="utf-8")
    assert "Fusion CLI'ın kurulu" not in guide
    assert "Python kur" not in guide
    assert "sağ tıklayın" in guide
    assert "Çalışma zamanını onar" in guide
```

- [ ] **Step 2: Mevcut belgenin testi kırdığını doğrula**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_packaging.py::test_macos_kurulumu_cli_ve_python_onkosulu_istemez
```

Expected: FAIL because current guide requires installed Fusion CLI.

- [ ] **Step 3: `.app` smoke sürücüsünü uygula**

`desktop_build/macos/__init__.py` yalnız paket docstring'i içerir. `desktop_build/macos/smoke_app_bundle.py` şu kontrolleri yapar:

```python
def inspect_bundle(app: Path) -> None:
    plist = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    assert plist["CFBundleIdentifier"] == "com.fusion.desktop"
    resources = app / "Contents/Resources/runtime"
    manifest = json.loads((resources / "runtime-manifest.json").read_text(encoding="utf-8"))
    archive = resources / manifest["archive"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["archive_sha256"]
    assert manifest["target"] in {"aarch64-apple-darwin", "x86_64-apple-darwin"}


def launch_clean(app: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="fusion-clean-home-") as raw_home:
        environment = {**os.environ, "HOME": raw_home}
        result = subprocess.run(
            ["open", "-W", "-n", str(app), "--args", "--runtime-smoke"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stderr
        active = Path(raw_home) / "Library/Application Support/Fusion/runtime/active-runtime.json"
        assert active.is_file()
```

Rust `run()` yalnız açık `--runtime-smoke` süreç argümanı bulunduğunda, hazır runtime sonrasında pencereyi kapatıp exit `0` verir. Argüman yoksa normal kullanıcı başlatması değişmez. Smoke modu sağlayıcı çağrısı yapmaz; yalnız kurulum, sağlık ve app-protokol `oturum.durum` isteğini doğrular.

- [ ] **Step 4: Kullanıcı ve geliştirici belgelerini düzelt**

`app/KURULUM.md` şu kesin akışı anlatır:

1. DMG'yi aç ve Fusion'ı Applications'a sürükle.
2. İlk kez Finder'da sağ tık → Aç kullan.
3. Fusion kendi çalışma zamanını hazırlar; Python ve Terminal gerekmez.
4. Kurulum kesilirse uygulamayı yeniden aç; sorun sürerse **Ayarlar → Çalışma Zamanı → Çalışma zamanını onar**.
5. Kaldırma uygulamayı siler; kullanıcı projeleri ve Fusion verileri ayrıca silinmedikçe korunur.

`app/README.md` Node 22, Rust toolchain, Python venv ve `.[desktop,mcp,gateway]` geliştirici gereksinimlerini; `npm run check` ve `npm run bundle:mac` komutlarını yazar. Kullanıcı kurulum yönergesi ile geliştirici kurulumu ayrı başlıklarda tutulur.

- [ ] **Step 5: Make ve CI kapılarını ekle**

`Makefile`:

```make
.PHONY: app-check runtime-bundle app-package

format:
	$(RUFF) format src tests evals prompt_opt desktop_build

lint:
	$(RUFF) format --check src tests evals prompt_opt desktop_build
	$(RUFF) check src tests evals prompt_opt desktop_build

app-check:
	cd app && npm ci && npm run check

runtime-bundle:
	$(PY) -m pip install -e ".[desktop,mcp,gateway]"
	cd app && npm run runtime:build && npm run runtime:smoke

app-package: runtime-bundle
	cd app && npm run bundle:mac
	$(PY) desktop_build/macos/smoke_app_bundle.py app/src-tauri/target/release/bundle/macos/Fusion.app
```

`.github/workflows/desktop.yml`, GitHub'ın [güncel resmî runner etiketlerine](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) göre iki native iş çalıştırır:

```yaml
strategy:
  fail-fast: false
  matrix:
    include:
      - runner: macos-15
        target: aarch64-apple-darwin
      - runner: macos-15-intel
        target: x86_64-apple-darwin
runs-on: ${{ matrix.runner }}
```

Her iş Python 3.12, Node 22 ve stable Rust kurar; runner mimarisinin beklenen `matrix.target` ile eşleştiğini `rustc -vV` ve runtime manifesti üzerinden doğrular. Ardından `pip install -e '.[dev,desktop,mcp,gateway]'`, `npm ci`, `npm run check`, `npm run bundle:mac` ve bundle inspector çalışır. DMG ile `.app`, hedef üçlüsü artifact adına eklenerek ayrı saklanır. İmza/notarization veya release yayımlama adımı bulunmaz.

- [ ] **Step 6: Belge, smoke ve kalite kapısını çalıştır**

```bash
.venv/bin/python -m pytest -q tests/test_packaging.py tests/test_runtime_health.py tests/test_runtime_bundle.py tests/test_desktop_version.py
make app-check
make app-package
```

Expected: all commands exit `0`; temiz HOME altında active runtime kaydı oluşur.

- [ ] **Step 7: Dağıtım kapısını commit et**

```bash
git add app/KURULUM.md app/README.md Makefile .github/workflows/desktop.yml desktop_build/macos tests/test_packaging.py
git commit -m "test(app): bağımsız macOS paketini doğrula"
```

---

### Task 10: A aşaması tam regresyon ve teslimat kanıtı

**Files:**
- Create: `docs/superpowers/reports/2026-08-29-paketli-macos-runtime-sonuc.md`
- Create: `desktop_build/macos/write_runtime_report.py`
- Modify only if a gate exposes a defect: files owned by Tasks 1–9.

**Interfaces:**
- Consumes every interface from Tasks 1–9.
- Produces a checked release candidate `.app`, `.dmg`, runtime manifest and evidence report.
- Establishes the stable boundary consumed by Plan B: `runtime_durum`, `runtime_hazirla`, `runtime_onar`, `cekirdek_baslat`.

- [ ] **Step 1: Python'ın bütün kalite kapısını çalıştır**

```bash
make check
```

Expected: Ruff format/check, mypy, complete pytest suite and deadlock suites exit `0`.

- [ ] **Step 2: Frontend ve Rust'ın bütün kalite kapısını çalıştır**

```bash
cd app
npm ci
npm run check
```

Expected: all Vitest tests, TypeScript build, Rust fmt, Clippy and Rust tests exit `0`.

- [ ] **Step 3: Gerçek paket ve temiz kullanıcı smoke testini çalıştır**

```bash
cd ..
make app-package
```

Expected:

- `Fusion.app` ve bir `.dmg` oluşur.
- Bundle içindeki arşiv hash'i manifestle eşleşir.
- Temiz HOME'da uygulama kendi runtime'ını kurar.
- Sistem PATH'inde `fusion` olmasa da runtime sağlık ve app protokol smoke'u geçer.
- İkinci açılış runtime'ı yeniden çıkarmadan aktif sürümü kullanır.
- Paket arşivi bozulduğunda kullanıcı **onarılabilir** ekranını görür; onarım kullanıcı config/proje dosyasına dokunmaz.

- [ ] **Step 4: Eski fallback'in gerçekten kalmadığını denetle**

Run:

```bash
rg -n "\.local/bin/fusion|homebrew/bin/fusion|usr/local/bin/fusion|split_paths|Fusion CLI bulunamadı" app/src-tauri/src
```

Expected: no matches. `FUSION_DEVELOPER_RUNTIME` yalnız debug-gated runtime manager kodu ve testinde görünür.

- [ ] **Step 5: Sonuç raporunu ölçüm aracından üret**

`desktop_build/macos/write_runtime_report.py` ölçümleri dosya sisteminden ve komutlardan alır:

```python
def human_size(path: Path) -> str:
    size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.is_dir() else path.stat().st_size
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("ulaşılamaz")


def write_report(root: Path, output: Path) -> None:
    runtime_dir = root / "app/src-tauri/resources/runtime"
    manifest = json.loads((runtime_dir / "runtime-manifest.json").read_text(encoding="utf-8"))
    app = root / "app/src-tauri/target/release/bundle/macos/Fusion.app"
    dmg = next((root / "app/src-tauri/target/release/bundle/dmg").glob("*.dmg"))
    commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True).strip()
    lines = [
        "# Paketli macOS Runtime Sonuç Raporu",
        "",
        f"- Git commit: `{commit}`",
        f"- Mimari: `{platform.machine()}`",
        f"- Runtime sürümü: `{manifest['runtime_version']}`",
        f"- Runtime arşiv boyutu: {human_size(runtime_dir / manifest['archive'])}",
        f"- Fusion.app boyutu: {human_size(app)}",
        f"- DMG boyutu: {human_size(dmg)}",
        "- Python kalite kapısı: geçti",
        "- React kalite kapısı: geçti",
        "- Rust kalite kapısı: geçti",
        "- Temiz HOME smoke: geçti",
        "- İkinci açılış yeniden kurmadan geçti: evet",
        "- Onarım/rollback: geçti",
        "- Sistem fusion bağımlılığı: yok",
        "",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
```

Run:

```bash
.venv/bin/python desktop_build/macos/write_runtime_report.py \
  --output docs/superpowers/reports/2026-08-29-paketli-macos-runtime-sonuc.md
```

Expected: report contains current commit, architecture, manifest version and measured artifact sizes; the script exits non-zero if any artifact is missing.

- [ ] **Step 6: Rapor ve yalnız doğrulama kaynaklı düzeltmeleri commit et**

```bash
git add desktop_build/macos/write_runtime_report.py docs/superpowers/reports/2026-08-29-paketli-macos-runtime-sonuc.md
git commit -m "docs(app): paketli runtime teslimatını kaydet"
git status --short
```

Expected: yalnız kullanıcıya ait önceden var olan `:memory:.ses` ve `index.html` izlenmeyen kalır.

## Phase A Acceptance Gate

- DMG kurulumu Python, venv, Homebrew veya Fusion CLI istemez.
- Runtime yalnız doğrulanmış paket kaynağından kurulur.
- Archive ve çıkarılan dosyalar SHA-256 manifestiyle doğrulanır.
- Çıkarma path traversal ve kök dışına symlink yazamaz.
- Paralel ilk açılışlar dosya kilidiyle tek kuruluma dönüşür.
- Sağlıksız yeni sürüm etkinleştirilmez; sağlıklı önceki sürüme rollback yapılır.
- Onarım yalnız sürümlü runtime dizinine dokunur; kullanıcı verisini korur.
- Release build sistem PATH'ine düşmez.
- Kullanıcı kurulum ve onarım ilerlemesini native ekranda görür.
- `.app` ve `.dmg` gerçek temiz-HOME smoke testinden geçer.
- CLI, `fusion serve` ve Python test paketi regresyona uğramaz.
