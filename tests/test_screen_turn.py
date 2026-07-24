"""Tur koşucusu — olayları konuşmaya pompalar, onayları etkileşimsiz karşılar."""

from __future__ import annotations

import pytest

from fusion_cli.cli.repl.state import Engine, ReplState
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _repl_state(engine: Engine, tmp_path) -> ReplState:
    """Gerçek ReplState — motor seçimini test etmek için asgari kurulum."""
    return ReplState(config=make_config(), memory=null_memory(), root=tmp_path, engine=engine)


@pytest.mark.asyncio
async def test_etkilesimsiz_prompter_reddeder():
    from fusion_cli.cli.repl.screen_turn import NonInteractivePrompter

    prompter = NonInteractivePrompter()
    assert await prompter.confirm(object()) is False
    cevap = await prompter.ask("emin misin?")
    assert isinstance(cevap, str)


def test_pump_her_olayda_geri_cagirir():
    from fusion_cli.cli.repl.screen_turn import PumpSink

    sayac = {"n": 0}
    pump = PumpSink(lambda: sayac.__setitem__("n", sayac["n"] + 1))
    pump.handle(object())
    pump.handle(object())
    assert sayac["n"] == 2


class _SahteBridge:
    """Konuşma köprüsü yerine geçen asgari sahte."""

    def __init__(self) -> None:
        self.console = object()


class _SahteScreen:
    """FusionScreen yerine geçen asgari sahte — yalnızca kullanılan alanlar."""

    def __init__(self) -> None:
        self.bridge = _SahteBridge()

    def set_work(self, text: str) -> None:  # pragma: no cover - çağrılmaz
        pass

    def clear_work(self) -> None:  # pragma: no cover - çağrılmaz
        pass

    def after_event(self) -> None:  # pragma: no cover - çağrılmaz
        pass


def _sinks_tiplerini_topla(sinks):
    from fusion_cli.cli.repl.screen_turn import PumpSink
    from fusion_cli.cli.repl.work_line import WorkLineSink
    from fusion_cli.ui.renderer import ConsoleRenderer

    return {
        "renderer": any(isinstance(s, ConsoleRenderer) for s in sinks),
        "work": any(isinstance(s, WorkLineSink) for s in sinks),
        "pump": any(isinstance(s, PumpSink) for s in sinks),
    }


@pytest.mark.asyncio
async def test_fusion_motoru_secilir_ve_sinks_dogru(monkeypatch, tmp_path):
    from fusion_cli.cli.repl import screen_turn

    yakalanan: dict = {}

    async def sahte_run_task(line, config, **kwargs):
        yakalanan["engine"] = "fusion"
        yakalanan["sinks"] = kwargs["sinks"]
        return object()

    async def sahte_run_agent_task(*args, **kwargs):  # pragma: no cover
        yakalanan["engine"] = "agent"

    monkeypatch.setattr(screen_turn, "run_task", sahte_run_task)
    monkeypatch.setattr(screen_turn, "run_agent_task", sahte_run_agent_task)

    state = _repl_state(Engine.FUSION, tmp_path)
    await screen_turn.run_turn("merhaba", state, _SahteScreen())

    assert yakalanan["engine"] == "fusion"
    tipler = _sinks_tiplerini_topla(yakalanan["sinks"])
    assert tipler == {"renderer": True, "work": True, "pump": True}


@pytest.mark.asyncio
async def test_agent_motoru_secilir_ve_sinks_dogru(monkeypatch, tmp_path):
    from fusion_cli.cli.repl import screen_turn

    yakalanan: dict = {}

    async def sahte_run_task(*args, **kwargs):  # pragma: no cover
        yakalanan["engine"] = "fusion"

    async def sahte_run_agent_task(line, config, **kwargs):
        yakalanan["engine"] = "agent"
        yakalanan["sinks"] = kwargs["sinks"]
        return object()

    monkeypatch.setattr(screen_turn, "run_task", sahte_run_task)
    monkeypatch.setattr(screen_turn, "run_agent_task", sahte_run_agent_task)

    state = _repl_state(Engine.AGENT, tmp_path)
    await screen_turn.run_turn("merhaba", state, _SahteScreen())

    assert yakalanan["engine"] == "agent"
    tipler = _sinks_tiplerini_topla(yakalanan["sinks"])
    assert tipler == {"renderer": True, "work": True, "pump": True}
