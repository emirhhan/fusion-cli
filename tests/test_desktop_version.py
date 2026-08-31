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


def test_macos_paketi_apple_hesabi_olmadan_ad_hoc_imzalanir():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "app/src-tauri/tauri.bundle.conf.json").read_text(encoding="utf-8"))

    assert config["bundle"]["macOS"]["signingIdentity"] == "-"


def test_masaustu_ci_ses_motorunu_paketleme_ortamina_kurar():
    """PyInstaller, spec'te Piper'ı topluyorsa CI da `voice` extrasını kurmalı."""
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/desktop.yml").read_text(encoding="utf-8")

    install_lines = [line for line in workflow.splitlines() if "pip install -e" in line]
    assert len(install_lines) == 2
    assert all("voice" in line for line in install_lines)


def test_windows_paket_ayari_normal_cargo_kapisinda_otomatik_yuklenmez():
    """Runtime yalnız paketlemede gerekir; düz `cargo clippy` onu aramamalı."""
    root = Path(__file__).resolve().parents[1]
    app = json.loads((root / "app/package.json").read_text(encoding="utf-8"))

    assert not (root / "app/src-tauri/tauri.windows.conf.json").exists()
    assert "--config src-tauri/tauri.windows.bundle.conf.json" in app["scripts"]["bundle:win"]


def test_macos_paket_komutu_dinleme_yardimcisini_kaynaktan_uretir():
    """Temiz CI, geliştirici makinesinde kalmış `fusion-listen` ikilisine güvenemez."""
    root = Path(__file__).resolve().parents[1]
    app = json.loads((root / "app/package.json").read_text(encoding="utf-8"))

    assert (root / "desktop_build/listen/main.swift").is_file()
    assert "build_adapter.py --platform macos" in app["scripts"]["listen:build:mac"]
    assert "npm run listen:build:mac" in app["scripts"]["bundle:mac"]


def test_tauri_paketleme_uygulama_binarysini_acikca_secer():
    """Test helper binary'si eklenince Tauri ana binary'yi tahmin edemez."""
    import tomllib

    root = Path(__file__).resolve().parents[1]
    with (root / "app/src-tauri/Cargo.toml").open("rb") as stream:
        cargo = tomllib.load(stream)

    assert cargo["package"]["default-run"] == "fusion-desktop"


def test_terminal_test_yardimcisi_release_binarysi_degil():
    """PTY test yardımcısı son kullanıcı `.app` paketine girmemeli."""
    import tomllib

    root = Path(__file__).resolve().parents[1]
    with (root / "app/src-tauri/Cargo.toml").open("rb") as stream:
        cargo = tomllib.load(stream)

    assert all(item.get("name") != "terminal_test_helper" for item in cargo.get("bin", []))
    assert not (root / "app/src-tauri/src/bin/terminal_test_helper.rs").exists()
