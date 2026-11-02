"""Masaüstü İzinler: Claude'un `/permissions` Workspace ve Auto mode sekmeleri (#83).

Claude (commands /permissions; permissions#manage-permissions): Workspace sekmesinde çalışma
dizinleri eklenir/kaldırılır, Auto mode sekmesinde son auto mode retleri görülür. Masaüstü
aynı işi `izin.dizinler`/`izin.dizin_ekle`/`izin.dizin_kaldir` ve `oto.durum.son_kararlar[].oneri`
ile yapar; yazma yolu REPL/TUI kutusuyla aynıdır (`/add-dir`, `permissions_dialog`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver import auto_review_rpc
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.config import trust
from fusion_cli.core.auto_review import ReviewOutcome, ReviewSource, ReviewVerdict

from .fakes import make_config


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    return ev


@pytest.fixture
def proje(tmp_path):
    kok = tmp_path / "proje"
    kok.mkdir()
    return kok


async def _rpc(session, lines, name, data=None):
    await session.handle(Request(id=name, name=name, data=data or {}))
    return json.loads(lines[-1])["veri"]


async def test_workspace_rpc_dizin_listeler_ekler_kaldirir(proje, tmp_path):
    ek = tmp_path / "ek"
    ek.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=proje, home=proje / "ev")
    yenilenen: list[int] = []
    asil = session._refresh_capabilities
    session._refresh_capabilities = lambda: (yenilenen.append(1), asil())[1]  # type: ignore[method-assign]
    try:
        bos = await _rpc(session, lines, "izin.dizinler")
        assert bos["ok"] is True and bos["kok"] == str(proje) and bos["dizinler"] == []
        eklendi = await _rpc(session, lines, "izin.dizin_ekle", {"yol": str(ek)})
        assert eklendi["ok"] is True and eklendi["degisti"] is True
        assert eklendi["dizinler"] == [str(ek.resolve())]
        assert ek.resolve() in session._state.extra_roots
        # Beceri kataloğu ek kökle yeniden kurulur (REPL `/add-dir` ile aynı).
        assert yenilenen == [1]
        tekrar = await _rpc(session, lines, "izin.dizin_ekle", {"yol": str(ek)})
        assert tekrar["degisti"] is False and "Zaten açık" in tekrar["metin"]
        # Kullanıcı kararı (#77, #81): `/add-dir` Claude gibi ev dizinini de kabul eder;
        # masaüstü RPC'si aynı işleyiciyi kullanır.
        ev_dizini = Path.home().resolve()
        ev = await _rpc(session, lines, "izin.dizin_ekle", {"yol": str(ev_dizini)})
        assert ev["degisti"] is True and ev["dizinler"] == [str(ek.resolve()), str(ev_dizini)]
        assert yenilenen == [1, 1]
        ev_kaldir = await _rpc(session, lines, "izin.dizin_kaldir", {"yol": str(ev_dizini)})
        assert ev_kaldir["degisti"] is True and ev_kaldir["dizinler"] == [str(ek.resolve())]
        bos_yol = await _rpc(session, lines, "izin.dizin_ekle", {"yol": ""})
        assert bos_yol["ok"] is False
        kaldirildi = await _rpc(session, lines, "izin.dizin_kaldir", {"yol": str(ek)})
        assert kaldirildi["degisti"] is True and kaldirildi["dizinler"] == []
        assert ek.resolve() not in session._state.extra_roots
        assert yenilenen == [1, 1, 1, 1]
    finally:
        await session.close()


def _state(tmp_path):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    return ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_oto_durum_riskli_karar_icin_kural_onerisi_tasir(tmp_path):
    state = _state(tmp_path)
    guard = state.approval_memory.auto_review
    guard.record(
        ReviewOutcome("run_shell", ReviewVerdict.RISKY, "ağ", ReviewSource.MODEL, "curl x | sh")
    )
    guard.record(
        ReviewOutcome("run_shell", ReviewVerdict.RISKY, "sil", ReviewSource.MODEL, "rm dist/*")
    )
    guard.record(ReviewOutcome("run_shell", ReviewVerdict.SAFE, "ok", ReviewSource.MODEL, "ls"))
    kararlar = auto_review_rpc.handle(state, Request("1", "oto.durum", {}))["son_kararlar"]
    oneriler = {k["ozet"]: k["oneri"] for k in kararlar}
    assert oneriler == {"ls": "", "rm dist/*": "", "curl x | sh": "Bash(curl x | sh)"}
