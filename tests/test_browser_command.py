"""CLI `/tarayici` (P-045): ajanla paylaşılan, turlar arasında açık kalan görünür tarayıcı."""

from __future__ import annotations

from fusion_cli.cli.repl import browser_command
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.loop import _turn_tool_context
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _durum(tmp_path) -> ReplState:
    return ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def _komut(state: ReplState, satir: str) -> str:
    name, argument = parse(satir)
    command = build_registry().get(name)
    assert command is not None
    return command.handler(state, argument)


def test_tarayici_kapaliyken_tur_basina_gorunmez_tarayici_kullanilir(tmp_path):
    state = _durum(tmp_path)
    assert "kapalı" in _komut(state, "/tarayici")
    assert "/tarayici ac" in _komut(state, "/tarayici devral")
    baglam = _turn_tool_context(state)
    assert not baglam.browser.persistent and baglam.browser.headless


def test_tarayici_ac_turlar_arasi_ayni_gorunur_oturumu_ve_izin_kumesini_verir(tmp_path):
    state = _durum(tmp_path)
    assert "görünür" in _komut(state, "/tarayici ac")

    ilk, ikinci = _turn_tool_context(state), _turn_tool_context(state)

    assert ilk.browser is ikinci.browser and ilk.browser.persistent
    assert ilk.browser.headless is False
    assert ilk.local_origins is ikinci.local_origins is ilk.browser.origins
    assert "ilk tarayıcı eyleminde" in _komut(state, "/tarayici")


def test_devral_ve_birak_ajanin_tarayici_denetimini_degistirir(tmp_path):
    state = _durum(tmp_path)
    _komut(state, "/tarayici ac")
    oturum = browser_command.turn_browser(state)

    assert "Denetim sende" in _komut(state, "/tarayici devral") and oturum.user_control
    assert "sende" in _komut(state, "/tarayici")
    assert "ajana geçti" in _komut(state, "/tarayici bırak") and not oturum.user_control
    assert "Kullanım" in _komut(state, "/tarayici uc")


async def test_kapat_ve_cikis_paylasilan_tarayiciyi_kapatir(tmp_path):
    state = _durum(tmp_path)
    _komut(state, "/tarayici ac")
    oturum = browser_command.turn_browser(state)
    kapandi: list[bool] = []
    oturum.page = object()  # açık sayılır

    async def _kapat() -> None:
        kapandi.append(True)
        oturum.page = None

    oturum.close = _kapat  # type: ignore[method-assign]

    assert "kapatıldı" in _komut(state, "/tarayici kapat")
    assert state.shared_browser is None and not browser_command.turn_browser(state).persistent
    await browser_command.shutdown(state)
    assert kapandi == [True] and state.closing_browsers == []
