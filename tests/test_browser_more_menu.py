"""#439: Browser ⋮ menüsü — Auto-verify changes (launch.json autoVerify) ve Clear browsing data."""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.browser_panel import PANEL_PROFILE, BrowserPanel
from fusion_cli.appserver.preview_rpc import handle_preview_rpc
from fusion_cli.config import trust
from fusion_cli.config.browser_profiles import BrowserProfileStore
from fusion_cli.tools.preview_launch import auto_verify_enabled

from .fakes import make_config

pytestmark = pytest.mark.asyncio


def _launch(root, body: str):
    path = root / ".claude" / "launch.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


async def test_auto_verify_kapatilir_acilir_yapilandirma_korunur(tmp_path) -> None:
    config = {
        "name": "web",
        "runtimeExecutable": "npm",
        "runtimeArgs": ["run", "dev"],
        "port": 5173,
    }
    path = _launch(tmp_path, json.dumps({"version": "0.0.1", "configurations": [config]}))
    trust.approve_file(tmp_path, path)
    off = await handle_preview_rpc(tmp_path, "onizleme.otomatik_dogrulama", {"deger": False})
    assert off["ok"] and auto_verify_enabled(tmp_path) is False
    data = json.loads(path.read_text())
    assert data["configurations"] == [config] and data["autoVerify"] is False
    assert trust.is_file_trusted(tmp_path, path)  # Fusion'ın tek alanlık yazımı güveni bozmaz
    listing = await handle_preview_rpc(tmp_path, "onizleme.yapilandirmalar", {})
    assert listing["otomatik_dogrulama"] is False
    await handle_preview_rpc(tmp_path, "onizleme.otomatik_dogrulama", {"deger": True})
    assert auto_verify_enabled(tmp_path) is True


async def test_dosya_yoksa_olusturulur_yorumlu_dosyaya_yazilmaz(tmp_path) -> None:
    created = await handle_preview_rpc(tmp_path, "onizleme.otomatik_dogrulama", {"deger": False})
    assert created["ok"] and auto_verify_enabled(tmp_path) is False
    _launch(tmp_path, '// yorum\n{"version": "0.0.1", "configurations": []}')
    refused = await handle_preview_rpc(tmp_path, "onizleme.otomatik_dogrulama", {"deger": False})
    assert not refused["ok"] and "yorum" in refused["metin"]
    bad = await handle_preview_rpc(tmp_path, "onizleme.otomatik_dogrulama", {"deger": "hayir"})
    assert not bad["ok"]


async def test_clear_browsing_data_panel_oturumunu_siler(tmp_path) -> None:
    store = BrowserProfileStore(tmp_path / "profiller", secret_key="test-anahtari")
    store.save(PANEL_PROFILE, (), source="panel")
    assert store.exists(PANEL_PROFILE)
    panel = BrowserPanel(
        config=lambda: make_config(),
        root=lambda: tmp_path,
        turn_running=lambda: False,
        store=lambda: store,
    )
    result = await panel.handle("tarayici_panel.veri_temizle", {})
    assert result["ok"] and "temizlendi" in result["metin"]
    assert not store.exists(PANEL_PROFILE)
    await panel.close()
