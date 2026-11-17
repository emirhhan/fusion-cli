"""#439: yerleşik tarayıcının yönetici ayarları (disableBrowserExternalNavigation,
browserExternalPageTools) yalnız managed-settings.json'dan okunur ve dış sitelere uygulanır."""

from __future__ import annotations

import json

import pytest

from fusion_cli.config.browser_admin import BrowserAdmin, load_browser_admin
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import browser
from fusion_cli.tools.browser_policy import external_host, navigation_blocked, page_tools_blocked

pytestmark = pytest.mark.asyncio


def _managed(tmp_path, monkeypatch, data: dict) -> None:
    (tmp_path / "managed-settings.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("FUSION_CLAUDE_MANAGED_DIR", str(tmp_path))


async def test_dis_site_tanimi_localhost_ve_dosyayi_disarida_tutar() -> None:
    assert external_host("https://www.example.com/a") == "www.example.com"
    for local in (
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://[::1]:3000",
        "http://app.localhost",
        "file:///tmp/a.html",
        "about:blank",
        None,
    ):
        assert external_host(local) is None, local


async def test_yonetilen_dosya_yoksa_kisit_yok(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FUSION_CLAUDE_MANAGED_DIR", str(tmp_path))
    assert load_browser_admin() == BrowserAdmin()
    assert navigation_blocked("https://example.com") is None


async def test_dis_gezinme_kapali_localhost_acik(tmp_path, monkeypatch, public_example_dns) -> None:
    _managed(tmp_path, monkeypatch, {"disableBrowserExternalNavigation": True})
    assert "disableBrowserExternalNavigation" in str(navigation_blocked("https://example.com"))
    assert navigation_blocked("http://localhost:5173") is None
    result = await browser.browser_open({"url": "https://example.com"}, ToolContext(root=tmp_path))
    assert not result.ok and "disableBrowserExternalNavigation" in result.output


async def test_dis_sayfa_araclari_kapali_gezinme_acik(tmp_path, monkeypatch) -> None:
    _managed(tmp_path, monkeypatch, {"browserExternalPageTools": False})
    assert navigation_blocked("https://example.com") is None
    assert "browserExternalPageTools" in str(page_tools_blocked("https://example.com/x"))
    assert page_tools_blocked("http://127.0.0.1:3000") is None

    class _Page:
        url = "https://example.com/gizli"

        async def title(self):  # pragma: no cover - çağrılmamalı
            raise AssertionError("dış sayfa okunmamalı")

    summary = await browser._sayfa_ozeti(_Page(), "açıldı")
    assert summary.ok and "browserExternalPageTools" in summary.output
    assert "gizli" in summary.output  # adres söylenir, içerik okunmaz


async def test_kullanici_ya_da_proje_ayari_kisit_koyamaz(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FUSION_CLAUDE_MANAGED_DIR", str(tmp_path / "yok"))
    project = tmp_path / ".claude"
    project.mkdir()
    (project / "settings.json").write_text(json.dumps({"disableBrowserExternalNavigation": True}))
    assert load_browser_admin().external_navigation is True


async def test_browser_tools_kapaliyken_ajan_browser_araclarini_gormez(tmp_path) -> None:
    """Ayarlar › Browser tools (#439): `browser.tools: false` browser_* ailesini gizler."""
    from types import SimpleNamespace

    from fusion_cli.appserver.browser_profiles import set_setting
    from fusion_cli.engines.agent.engine_tools import _disabled_browser_tools
    from fusion_cli.tools.builtin import build_registry

    registry = build_registry()
    off = SimpleNamespace(config=SimpleNamespace(browser=SimpleNamespace(tools=False)))
    on = SimpleNamespace(config=SimpleNamespace(browser=SimpleNamespace(tools=True)))
    hidden = _disabled_browser_tools(off, registry)  # type: ignore[arg-type]
    assert "browser_open" in hidden and "browser_click" in hidden
    assert not any(name.startswith(("chrome_", "claude-in-chrome")) for name in hidden)
    assert _disabled_browser_tools(on, registry) == frozenset()  # type: ignore[arg-type]
    bad = set_setting(SimpleNamespace(), {"anahtar": "tools", "deger": "evet"})  # type: ignore[arg-type]
    assert not bad["ok"]


async def test_dis_sayfa_araclari_kapaliyken_sekme_listesi_basligi_gizler(tmp_path, monkeypatch):
    """Sekme başlığı sayfa içeriğidir: browserExternalPageTools:false iken dış sekmede gizli."""
    from types import SimpleNamespace

    _managed(tmp_path, monkeypatch, {"browserExternalPageTools": False})

    class _Page:
        def __init__(self, url: str, title: str) -> None:
            self.url, self._title = url, title

        async def title(self) -> str:
            return self._title

    yerel = _Page("http://localhost:5173/", "Geliştirme")
    dis = _Page("https://example.com/hesap", "Gizli Bakiye 1.234 TL")

    async def pages():
        return (yerel, dis)

    async def wait_for_control(_timeout):
        return True

    session = SimpleNamespace(is_open=True, page=yerel, pages=pages)
    session.wait_for_control = wait_for_control
    context = ToolContext(root=tmp_path)
    object.__setattr__(context, "browser", session)
    result = await browser.browser_tabs_list({}, context)
    assert result.ok
    assert "Geliştirme" in result.output  # yerel sekme olduğu gibi
    assert "Bakiye" not in result.output
    assert "https://example.com/hesap" in result.output  # adres söylenir (sayfa özeti gibi)
