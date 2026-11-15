"""Masaüstü paketi Kits'i HER ZAMAN içerir; Kits'siz paket üretmenin yolu yoktur.

Ölçüldü (31 Ekim): `bundle:mac` Kits'siz, `bundle:mac:kits` Kits'li paket üretiyordu.
Kits'siz paket kurulunca uygulama "Bu Fusion paketinde Kits bileşeni bulunamadı"
hatası veriyordu. Kullanıcı kararı: indiren herkes Kits'i kurulu alsın.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TAURI = APP / "src-tauri"

#: Paket yapılandırması → Kits kaynak eşlemesi (Node ikilisinin adı platforma göre).
KITS_RESOURCES = {
    "tauri.bundle.conf.json": {
        "resources/kits/kits-manifest.json": "kits/kits-manifest.json",
        "resources/kits/node": "kits/node",
        "resources/kits/app/": "kits/app/",
    },
    "tauri.windows.bundle.conf.json": {
        "resources/kits/kits-manifest.json": "kits/kits-manifest.json",
        "resources/kits/node.exe": "kits/node.exe",
        "resources/kits/app/": "kits/app/",
    },
}


def _scripts() -> dict[str, str]:
    package = json.loads((APP / "package.json").read_text(encoding="utf-8"))
    return package["scripts"]


def _resources(config: str) -> dict[str, str]:
    return json.loads((TAURI / config).read_text(encoding="utf-8"))["bundle"]["resources"]


def test_paket_yapilandirmalari_kits_kaynagini_kendisi_esler() -> None:
    """Eşleme paket yapılandırmasının KENDİSİNDE: Kits yoksa her `tauri build` düşer."""
    for config, expected in KITS_RESOURCES.items():
        resources = _resources(config)
        for source, target in expected.items():
            assert resources.get(source) == target, f"{config}: {source} eşlenmemiş"


def test_ayri_kits_yapilandirmasi_kalmadi() -> None:
    assert not (TAURI / "tauri.kits.conf.json").exists()
    assert all("tauri.kits.conf.json" not in command for command in _scripts().values())


def test_paket_komutlari_kits_hazirligiyla_baslar() -> None:
    scripts = _scripts()
    assert scripts["kits:prepare"] == "node scripts/prepare-kits.mjs"
    assert scripts["bundle:mac"].startswith("npm run kits:prepare && ")
    assert scripts["bundle:win"].startswith("npm run kits:prepare && ")
    assert "--config src-tauri/tauri.bundle.conf.json" in scripts["bundle:mac"]
    assert "--config src-tauri/tauri.windows.bundle.conf.json" in scripts["bundle:win"]


def test_eski_kits_komutu_yalniz_takma_addir() -> None:
    assert _scripts()["bundle:mac:kits"] == "npm run bundle:mac"


def test_kitssiz_paket_ureten_komut_yok() -> None:
    """`tauri build` çağıran her komut Kits'i eşleyen bir paket yapılandırması kullanır."""
    for name, command in _scripts().items():
        if "tauri build" not in command:
            continue
        assert "npm run kits:prepare" in command, f"{name} Kits hazırlamadan paketliyor"
        assert any(f"--config src-tauri/{config}" in command for config in KITS_RESOURCES), name


# --- prepare-kits.mjs: Kits son commit'ten, temiz ağaçta derlenip paketlenir -------------

_FAKE_BUILD = """
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
const marker = readFileSync('src/marker.txt', 'utf8').trim();
if (marker === 'DERLEME-HATASI') process.exit(3);
mkdirSync('dist/client', { recursive: true });
writeFileSync('dist/client/index.html', marker);
"""

_FAKE_BUNDLE = """
import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
const output = resolve(process.argv[2]);
mkdirSync(resolve(output, 'dist/server/server'), { recursive: true });
const marker = readFileSync('src/marker.txt', 'utf8').trim();
writeFileSync(resolve(output, 'dist/server/server/index.js'), `// ${marker}\\n`);
cpSync('dist/client', resolve(output, 'dist/client'), { recursive: true });
writeFileSync(resolve(output, 'dep.txt'), readFileSync('node_modules/dep/value.txt'));
"""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _fake_kits(root: Path, marker: str = "HEAD-ICERIK") -> Path:
    kits = root / "kits"
    (kits / "scripts").mkdir(parents=True)
    (kits / "src").mkdir()
    (kits / "package.json").write_text(
        json.dumps({"name": "fake-kits", "type": "module", "scripts": {"build": "node build.mjs"}}),
        encoding="utf-8",
    )
    (kits / "build.mjs").write_text(_FAKE_BUILD, encoding="utf-8")
    (kits / "scripts/kits-bundle.mjs").write_text(_FAKE_BUNDLE, encoding="utf-8")
    (kits / "src/marker.txt").write_text(marker, encoding="utf-8")
    (kits / ".gitignore").write_text("node_modules/\ndist/\n", encoding="utf-8")
    _git(kits, "init", "-q")
    _git(kits, "add", ".")
    _git(kits, "commit", "-q", "-m", "ilk")
    (kits / "node_modules/dep").mkdir(parents=True)
    (kits / "node_modules/dep/value.txt").write_text("bagimlilik", encoding="utf-8")
    return kits


def _fake_app(root: Path) -> Path:
    scripts = root / "app/scripts"
    scripts.mkdir(parents=True)
    for name in ("prepare-kits.mjs", "check-runtime.mjs"):
        shutil.copy(APP / "scripts" / name, scripts / name)
    target = root / "app/src-tauri/resources/kits"
    target.mkdir(parents=True)
    (target / "sentinel").write_text("koru", encoding="utf-8")
    return target


def _node24(root: Path) -> Path:
    """Sürümü 24 bildiren, işi gerçek Node'a devreden `node` sarmalayıcısı."""
    real = shutil.which("node")
    assert real, "Testler için PATH'te Node gerekir"
    bin_dir = root / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "node"
    wrapper.write_text(
        '#!/bin/sh\nif [ "$1" = "--version" ]; then echo v24.0.0; exit 0; fi\n'
        f'exec "{real}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def _prepare(root: Path, kits: Path, node: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "FUSION_KITS_DIR": str(kits), "FUSION_KITS_NODE": str(node)}
    return subprocess.run(
        [str(node), str(root / "app/scripts/prepare-kits.mjs")],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


_POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32", reason="sahte Node sarmalayıcısı POSIX kabuk betiği"
)


@_POSIX_ONLY
def test_prepare_kits_kirli_agactan_degil_head_den_paketler(tmp_path: Path) -> None:
    kits = _fake_kits(tmp_path)
    head = _git(kits, "rev-parse", "HEAD")
    # Ana kopya kirli ve içinde bayat derlenmiş istemci var: ikisi de pakete girmemeli.
    (kits / "src/marker.txt").write_text("KIRLI", encoding="utf-8")
    (kits / "dist/client").mkdir(parents=True)
    (kits / "dist/client/index.html").write_text("BAYAT", encoding="utf-8")
    target = _fake_app(tmp_path)
    node = _node24(tmp_path)

    result = _prepare(tmp_path, kits, node)

    assert result.returncode == 0, result.stderr
    app = target / "app"
    assert (app / "dist/client/index.html").read_text(encoding="utf-8") == "HEAD-ICERIK"
    assert "HEAD-ICERIK" in (app / "dist/server/server/index.js").read_text(encoding="utf-8")
    assert (app / "dep.txt").read_text(encoding="utf-8") == "bagimlilik"
    assert (target / "node").is_file()
    assert not (target / "sentinel").exists()
    manifest = json.loads((target / "kits-manifest.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == head
    assert manifest["nodeVersion"] == "v24.0.0"
    assert manifest["commitDate"] and manifest["packagedAt"]
    assert manifest["sourceDirty"] is True
    # Ana kopya olduğu gibi kalır; geçici ağaç kaldırılır.
    assert (kits / "src/marker.txt").read_text(encoding="utf-8") == "KIRLI"
    assert (kits / "dist/client/index.html").read_text(encoding="utf-8") == "BAYAT"
    assert (kits / "node_modules/dep/value.txt").is_file()
    assert len(_git(kits, "worktree", "list").splitlines()) == 1


@_POSIX_ONLY
def test_prepare_kits_depo_yoksa_acik_hatayla_durur(tmp_path: Path) -> None:
    target = _fake_app(tmp_path)
    result = _prepare(tmp_path, tmp_path / "yok", _node24(tmp_path))

    assert result.returncode != 0
    assert "Fusion Kits deposu bulunamadı" in result.stderr
    assert (target / "sentinel").is_file()


@_POSIX_ONLY
def test_prepare_kits_git_deposu_degilse_durur(tmp_path: Path) -> None:
    kits = tmp_path / "kits"
    (kits / "scripts").mkdir(parents=True)
    (kits / "scripts/kits-bundle.mjs").write_text(_FAKE_BUNDLE, encoding="utf-8")
    target = _fake_app(tmp_path)
    result = _prepare(tmp_path, kits, _node24(tmp_path))

    assert result.returncode != 0
    assert "git deposu değil" in result.stderr
    assert (target / "sentinel").is_file()


@_POSIX_ONLY
def test_prepare_kits_derleme_duserse_kitssiz_devam_etmez(tmp_path: Path) -> None:
    kits = _fake_kits(tmp_path, marker="DERLEME-HATASI")
    target = _fake_app(tmp_path)
    result = _prepare(tmp_path, kits, _node24(tmp_path))

    assert result.returncode != 0
    assert "Kits istemcisi derlenemedi" in result.stderr
    assert (target / "sentinel").is_file()
    assert not (target / "app").exists()
    assert len(_git(kits, "worktree", "list").splitlines()) == 1


# --- Doğrulama kapıları: Kits'siz paket smoke'tan ve yayından geçemez -----------------------

_HEAD = "79a6007a89fb599961a6917b1a565986eb5087ec"
_SYSTEM_OTOOL = "node:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n"
_BREW_OTOOL = _SYSTEM_OTOOL + "\t/opt/homebrew/opt/libuv/lib/libuv.1.dylib (compat 1.0.0)\n"


def _system_otool(_: Path) -> str:
    return _SYSTEM_OTOOL


def _write_kits(kits: Path, node_name: str = "node") -> Path:
    (kits / "app/dist/server/server").mkdir(parents=True)
    (kits / "app/dist/server/server/index.js").write_text("// sunucu\n", encoding="utf-8")
    (kits / "app/dist/client").mkdir(parents=True)
    (kits / "app/dist/client/index.html").write_text("<!doctype html>", encoding="utf-8")
    node = kits / node_name
    node.write_bytes(bytes.fromhex("cffaedfe") + b"\0" * 64)
    node.chmod(0o755)
    manifest = {"schema": 1, "commit": _HEAD, "commitDate": "2026-10-31T21:34:00+03:00"}
    manifest |= {"nodeVersion": "v24.21.0", "packagedAt": "2026-10-31T19:39:00Z"}
    (kits / "kits-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return kits


def test_kits_denetimi_tam_paketi_kabul_eder(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import inspect_kits

    kits = _write_kits(tmp_path / "kits")
    manifest = inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)

    assert manifest["commit"] == _HEAD


@pytest.mark.parametrize(
    ("bozma", "beklenen"),
    [
        ("app/dist/server/server/index.js", "Kits sunucusu"),
        ("app/dist/client", "Kits istemcisi"),
        ("node", "Kits Node"),
        ("kits-manifest.json", "kits-manifest.json"),
    ],
)
def test_kits_denetimi_eksik_parcada_duser(tmp_path: Path, bozma: str, beklenen: str) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    shutil.rmtree(kits / bozma) if (kits / bozma).is_dir() else (kits / bozma).unlink()

    with pytest.raises(KitsBundleError, match=beklenen):
        inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)


def test_kits_denetimi_kits_dizini_yoksa_duser(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    with pytest.raises(KitsBundleError, match="Kits bileşeni yok"):
        inspect_kits(tmp_path / "yok", node_name="node", macos=False)


def test_kits_denetimi_gecersiz_manifesti_reddeder(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    (kits / "kits-manifest.json").write_text(json.dumps({"commit": "kirli"}), encoding="utf-8")

    with pytest.raises(KitsBundleError, match="commit"):
        inspect_kits(kits, node_name="node", macos=False)


def test_kits_denetimi_eski_node_surumunu_reddeder(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    manifest = json.loads((kits / "kits-manifest.json").read_text(encoding="utf-8"))
    (kits / "kits-manifest.json").write_text(
        json.dumps({**manifest, "nodeVersion": "v22.23.3"}), encoding="utf-8"
    )

    with pytest.raises(KitsBundleError, match="Node 24"):
        inspect_kits(kits, node_name="node", macos=False)


def test_kits_denetimi_homebrew_node_unu_reddeder(tmp_path: Path) -> None:
    """Homebrew Node'u /opt/homebrew kitaplıklarına bağlı; kullanıcının Mac'inde açılmaz."""
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")

    with pytest.raises(KitsBundleError, match="taşınabilir değil"):
        inspect_kits(kits, node_name="node", macos=True, otool=lambda _: _BREW_OTOOL)


def test_kits_denetimi_mach_o_olmayan_node_u_reddeder(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits")
    (kits / "node").write_text("#!/bin/sh\n", encoding="utf-8")

    with pytest.raises(KitsBundleError, match="Mach-O"):
        inspect_kits(kits, node_name="node", macos=True, otool=_system_otool)


def _fake_app_bundle(root: Path, *, with_kits: bool) -> Path:
    import hashlib
    import plistlib

    app = root / "Fusion.app"
    (app / "Contents").mkdir(parents=True)
    (app / "Contents/Info.plist").write_bytes(
        plistlib.dumps(
            {"CFBundleIdentifier": "com.fusion.desktop", "CFBundleShortVersionString": "0.7.19"}
        )
    )
    runtime = app / "Contents/Resources/runtime"
    runtime.mkdir(parents=True)
    (runtime / "fusion-runtime.tar.gz").write_bytes(b"arsiv")
    (runtime / "runtime-manifest.json").write_text(
        json.dumps(
            {
                "archive": "fusion-runtime.tar.gz",
                "archive_sha256": hashlib.sha256(b"arsiv").hexdigest(),
                "target": "aarch64-apple-darwin",
                "runtime_version": "0.7.19",
            }
        ),
        encoding="utf-8",
    )
    if with_kits:
        _write_kits(app / "Contents/Resources/kits")
    return app


def test_macos_smoke_kitssiz_paketi_reddeder(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError
    from desktop_build.macos.smoke_app_bundle import inspect_bundle

    app = _fake_app_bundle(tmp_path, with_kits=False)

    with pytest.raises(KitsBundleError, match="Kits bileşeni yok"):
        inspect_bundle(app, otool=_system_otool)


def test_macos_smoke_kitsli_paketi_kits_commitiyle_raporlar(tmp_path: Path) -> None:
    from desktop_build.macos.smoke_app_bundle import inspect_bundle

    app = _fake_app_bundle(tmp_path, with_kits=True)
    manifest = inspect_bundle(app, otool=_system_otool)

    assert manifest["runtime_version"] == "0.7.19"
    assert manifest["kits"]["commit"] == _HEAD


def test_macos_guncelleme_paketi_kitssiz_uygulamayi_reddeder(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError
    from desktop_build.macos.build_update import build_update

    app = _fake_app_bundle(tmp_path, with_kits=False)
    out = tmp_path / "out"

    with pytest.raises(KitsBundleError):
        build_update(app, out, key=None, repository="x/y")
    assert not list(out.glob("*.tar.gz")) if out.exists() else True


def test_windows_guncelleme_paketi_kitssiz_kaynagi_reddeder(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError
    from desktop_build.windows.build_update import build_update

    installer = tmp_path / "Fusion-setup.exe"
    installer.write_bytes(b"MZ")

    with pytest.raises(KitsBundleError, match="Kits bileşeni yok"):
        build_update(installer, tmp_path / "out", "0.7.19", "x/y", kits_dir=tmp_path / "yok")


def test_windows_kits_denetimi_node_exe_ister(tmp_path: Path) -> None:
    from desktop_build.kits_bundle import KitsBundleError, inspect_kits

    kits = _write_kits(tmp_path / "kits", node_name="node")
    with pytest.raises(KitsBundleError, match=r"node\.exe"):
        inspect_kits(kits, node_name="node.exe", macos=False)


def _release_manifest():  # type: ignore[no-untyped-def]
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "release_manifest_kits", ROOT / "scripts/release_manifest.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_yayin_manifesti_kits_commiti_olmadan_reddedilir(tmp_path: Path) -> None:
    module = _release_manifest()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "a.dmg").write_bytes(b"alpha")
    base = ["--version", "1.2.3", "--commit", "abc", "--artifacts", str(dist)]

    with pytest.raises(SystemExit, match="Kits"):
        module.main([*base, "--out", str(tmp_path / "out")])
    with pytest.raises(SystemExit, match="Kits"):
        module.main([*base, "--kits-commit", "", "--out", str(tmp_path / "out")])


def test_yayin_manifesti_kits_manifestinden_commit_okur(tmp_path: Path) -> None:
    module = _release_manifest()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "a.dmg").write_bytes(b"alpha")
    kits = _write_kits(tmp_path / "kits")
    out = tmp_path / "out"

    code = module.main(
        [
            *("--version", "1.2.3", "--commit", "abc", "--artifacts", str(dist)),
            *("--kits-manifest", str(kits / "kits-manifest.json"), "--out", str(out)),
        ]
    )

    assert code == 0
    manifest = json.loads((out / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["bundled"]["kitsCommit"] == _HEAD
