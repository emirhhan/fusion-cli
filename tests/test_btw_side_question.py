"""`/btw` yan soru (#221): konuşmadan yanıtlar, geçmişe girmez, araçsız, son 20 tutulur."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from fusion_cli.cli.repl import btw_command, help_view
from fusion_cli.cli.repl.commands import build_registry, renders_itself
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.types import Message, ModelResult
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages

from .fakes import make_config


class _Sahte:
    def __init__(self, text: str = "Yan cevap") -> None:
        self.requests: list = []
        self.text = text

    async def complete(self, request):
        self.requests.append(request)
        return ModelResult(name="a", model="m/x", text=self.text, latency_ms=1, ok=True)


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    value = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    value.history = [Message("user", "Oyun motoru yaz"), Message("assistant", "Godot ile başladım")]
    return value


@pytest.fixture
def sahte(monkeypatch) -> _Sahte:
    provider = _Sahte()
    monkeypatch.setattr(btw_command, "_provider", lambda state: provider)
    return provider


def _console() -> Console:
    return Console(record=True, width=100, force_terminal=False, no_color=True)


async def test_yan_soru_konusmayi_gorur_gecmise_girmez_aracsiz(state, sahte) -> None:
    once = list(state.history)
    console = _console()

    await help_view.render("btw", state, build_registry(), console, "hangi motor?")

    text = console.export_text()
    assert "hangi motor?" in text and "Yan cevap" in text
    assert state.history == once
    request = sahte.requests[0]
    assert request.tools == ()
    contents = [m.content for m in request.messages]
    assert "Godot ile başladım" in contents and contents[-1] == "hangi motor?"


async def test_argumansiz_en_son_yan_soruyu_gosterir(state, sahte) -> None:
    await help_view.render("btw", state, build_registry(), _console(), "ilk")
    await help_view.render("btw", state, build_registry(), _console(), "ikinci")
    console = _console()

    await help_view.render("btw", state, build_registry(), console, "")

    assert "ikinci" in console.export_text() and len(sahte.requests) == 2


async def test_hic_yan_soru_yoksa_kullanim_satiri(state, sahte) -> None:
    console = _console()
    await help_view.render("btw", state, build_registry(), console, "")
    assert messages.BTW_USAGE in console.export_text()
    assert sahte.requests == []


async def test_son_yirmi_tutulur(state, sahte) -> None:
    for index in range(btw_command.SIDE_QUESTION_LIMIT + 3):
        await btw_command.ask(state, f"soru {index}")
    assert len(state.side_questions) == btw_command.SIDE_QUESTION_LIMIT
    assert state.side_questions[0][0] == "soru 3"


def test_btw_kendi_basan_komut_makro_degil() -> None:
    command = build_registry().get("btw")
    assert command is not None and command.group != "Makro"
    assert renders_itself("btw", "soru")
