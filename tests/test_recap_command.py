"""`/recap` (#230): oturumun tek satırlık özeti, isteğe bağlı; en çok 400 karakter."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from fusion_cli.cli.repl import btw_command, help_view, recap_command
from fusion_cli.cli.repl.commands import build_registry, renders_itself
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.types import Message, ModelResult
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages

from .fakes import make_config


class _Sahte:
    def __init__(self, text: str) -> None:
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


def _console() -> Console:
    return Console(record=True, width=500, force_terminal=False, no_color=True)


async def test_recap_tek_satir_400_karakter_gecmise_girmez(state, monkeypatch) -> None:
    sahte = _Sahte("Godot ile\noyun motoru kuruldu. " + "x" * 600)
    monkeypatch.setattr(btw_command, "_provider", lambda state: sahte)
    once = list(state.history)
    console = _console()
    assert renders_itself("recap", "")

    await help_view.render("recap", state, build_registry(), console, "")

    text = console.export_text().strip()
    assert text.startswith("※ Godot ile oyun motoru kuruldu.")
    assert "\n" not in text and len(text) <= recap_command.RECAP_MAX_CHARS + 2
    assert state.history == once
    request = sahte.requests[0]
    assert request.tools == () and request.messages[0].content == messages.RECAP_SYSTEM
    assert "Godot ile başladım" in [m.content for m in request.messages]


async def test_bos_oturumda_model_cagrilmaz(state, monkeypatch) -> None:
    state.history = []
    monkeypatch.setattr(btw_command, "_provider", lambda state: pytest.fail("çağrılmamalı"))
    console = _console()
    await help_view.render("recap", state, build_registry(), console, "")
    assert messages.RECAP_EMPTY in console.export_text()
