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


async def test_tui_yan_soru_kapatilabilir_katmanda_gezinir(state, sahte) -> None:
    """Claude Code: cevap kapatılabilir katmanda; konuşma alanına basılmaz (#221)."""
    import asyncio

    from fusion_cli.cli.repl.tui_loop import _TuiSession

    state.side_questions = [("ilk soru", "ilk cevap")]
    session = _TuiSession(state)
    gorev = asyncio.ensure_future(session._command("/btw hangi motor?"))
    for _ in range(20):
        await asyncio.sleep(0.01)
        if session.tui._mode == "choice":
            break
    assert "2/2: hangi motor?" in session.tui._choice_title
    assert [c.label for c in session.tui._choices] == ["Yan cevap"]
    session.tui._pick_alt("left")
    await asyncio.sleep(0.01)
    assert "1/2: ilk soru" in session.tui._choice_title
    session.tui._resolve(None)
    await gorev
    assert "Yan cevap" not in session.tui.transcript
    assert state.history[-1].content == "Godot ile başladım"


def test_katman_satirlari_uzun_cevabi_sarar() -> None:
    rows = btw_command.overlay_rows("a" * 200 + "\n\nb")
    assert len(rows) == 5 and rows[3].label == " " and rows[4].label == "b"


async def test_satir_ici_yan_soru_katmani_secicide(state, sahte, monkeypatch) -> None:
    from fusion_cli.ui import picker

    titles: list[str] = []

    def fake_pick(rows, *, title, alt_keys=()):
        titles.append(title)
        return None

    monkeypatch.setattr(picker, "pick", fake_pick)
    console = _console()
    await btw_command.inline_overlay(state, "neden Godot?", console)
    assert titles and "neden Godot?" in titles[0]
    assert "Yan cevap" not in console.export_text()
