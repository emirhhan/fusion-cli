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
