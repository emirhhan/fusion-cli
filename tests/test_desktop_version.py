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
