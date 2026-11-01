"""Masaüstü yüzeyinde `disableAutoMode` (#85): çekirdek auto'yu reddeder ve arayüze bildirir.

Claude (permissions#permission-modes, settings-reference disableAutoMode): `"disable"` auto
kipini engeller ve kip seçicisinden çıkarır; her ayar dosyasında geçerlidir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.engines.agent.approval import ApprovalMode


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "kullanici-evi"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))


def _sonuc(satirlar: list[str], kimlik: str) -> dict:
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(kimlik)


def _kapat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"disableAutoMode": "disable"}}), encoding="utf-8")


async def test_durum_auto_kapali_alanini_tasir(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=proje, home=tmp_path / "ev")
    await oturum.handle(Request(id="1", name="oturum.durum", data={}))
    assert _sonuc(satirlar, "1")["auto_kapali"] is False

    _kapat(Path.home() / ".claude" / "settings.json")
    await oturum.handle(Request(id="2", name="oturum.durum", data={}))
    assert _sonuc(satirlar, "2")["auto_kapali"] is True


async def test_kapali_auto_masaustunden_secilemez(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    _kapat(proje / ".claude" / "settings.json")
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=proje, home=tmp_path / "ev")
    await oturum.handle(Request(id="1", name="oturum.baslat", data={"mod": "auto"}))
    sonuc = _sonuc(satirlar, "1")
    assert sonuc["ok"] is False
    assert "disableAutoMode" in sonuc["metin"]
    assert oturum._state.approval is not ApprovalMode.AUTO
    # Öteki kipler etkilenmez.
    await oturum.handle(Request(id="2", name="oturum.baslat", data={"mod": "plan"}))
    assert _sonuc(satirlar, "2")["ok"] is True
