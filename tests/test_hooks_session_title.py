"""Kanca `sessionTitle` (#123): `/rename` ile aynı etki; SessionStart'ta yalnız
startup/resume/fork; `--name`/`/rename` başlığı `session_title` girdisinde."""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture(autouse=True)
def _kancalar_acik(monkeypatch):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)


def _hook(tmp_path: Path, event: HookEvent, output: dict[str, object]) -> HookCommand:
    log = tmp_path / f"{event.value}.jsonl"
    script = tmp_path / f"{event.value}.py"
    script.write_text(
        "import sys\n"
        f"open({str(log)!r}, 'a').write(sys.stdin.read().strip() + '\\n')\n"
        f"print({json.dumps(output)!r})\n",
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    return HookCommand(event, "", command, 20.0)


def _title(name: str) -> dict[str, object]:
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "sessionTitle": name}}


def test_sessionstart_basligi_sinke_gider_clear_kaynaginda_gitmez(tmp_path):
    hooks = HookSet((_hook(tmp_path, HookEvent.SESSION_START, _title("auth-refactor")),))
    titles: list[str] = []
    session = HookSession(root=tmp_path, loader=lambda: hooks)
    session.title_sink = titles.append

    asyncio.run(session.start("startup"))
    session.restart("clear", reason="clear")
    asyncio.run(session.start())

    assert titles == ["auth-refactor"]


def test_repl_durumu_basligi_rename_gibi_kaydeder_ve_girdiye_verir(tmp_path):
    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    session = state.hooks()
    assert session.title_sink is not None
    session.title_sink("kanca-adi")
    assert state.conversation_name == "kanca-adi"
    assert state.hooks().session_title == "kanca-adi"
