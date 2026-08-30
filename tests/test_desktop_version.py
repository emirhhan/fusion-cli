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


def test_masaustu_ci_ses_motorunu_paketleme_ortamina_kurar():
    """PyInstaller, spec'te Piper'ı topluyorsa CI da `voice` extrasını kurmalı."""
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/desktop.yml").read_text(encoding="utf-8")

    install_lines = [line for line in workflow.splitlines() if "pip install -e" in line]
    assert len(install_lines) == 2
    assert all("voice" in line for line in install_lines)
