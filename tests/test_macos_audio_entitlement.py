"""Dağıtım izinleri: Hardened Runtime mikrofon erişimi açıkça bildirilir."""

import json
import plistlib
from pathlib import Path


def test_macos_bundle_has_audio_input_entitlement():
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "app/src-tauri/tauri.conf.json").read_text())
    relative = config["bundle"]["macOS"].get("entitlements")
    assert relative, "macOS audio-input entitlement pakete bağlanmalı"
    entitlements = plistlib.loads((root / "app/src-tauri" / relative).read_bytes())
    assert entitlements.get("com.apple.security.device.audio-input") is True
    assert "com.apple.security.device.camera" not in entitlements
