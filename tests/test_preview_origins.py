"""Projenin çalışan önizleme sunucusunun yerel kökeni onaysız açılır (#438)."""

from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import chrome, preview_launch, preview_origins, preview_server


class _Kopru:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def invoke(self, name, data):
        self.calls.append(name)
        return {"ok": True, "veri": {}}


def _onizleme(monkeypatch, url: str | None, static: str | None = None) -> None:
    named = (("web", SimpleNamespace(url=url)),) if url else ()
    monkeypatch.setattr(preview_launch, "running_launches", lambda root=None: named)
    monkeypatch.setattr(
        preview_server, "running", lambda root: SimpleNamespace(url=static) if static else None
    )


async def test_calisan_onizleme_kokeni_acilir_baskasi_kapali(tmp_path, monkeypatch):
    _onizleme(monkeypatch, "http://localhost:5173/", static="http://127.0.0.1:8770/index.html")
    kopru = _Kopru()
    context = ToolContext(root=tmp_path, chrome=kopru)
    ok = await chrome.chrome_action(
        {"action": "open", "value": "http://localhost:5173/app"}, context
    )
    assert ok.ok and kopru.calls == ["tab_open"]
    assert preview_origins.project_preview_origins(context) == {"localhost:5173", "127.0.0.1:8770"}
    blocked = await chrome.chrome_action(
        {"action": "open", "value": "http://localhost:6000/"}, context
    )
    assert not blocked.ok and kopru.calls == ["tab_open"]


async def test_onizleme_yoksa_yerel_adres_kapali(tmp_path, monkeypatch):
    _onizleme(monkeypatch, None)
    context = ToolContext(root=tmp_path, chrome=_Kopru())
    result = await chrome.chrome_action(
        {"action": "open", "value": "http://localhost:5173/"}, context
    )
    assert not result.ok
