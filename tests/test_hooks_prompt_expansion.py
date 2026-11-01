"""`UserPromptExpansion` kancası (#90): `/komut` açılırken, UserPromptSubmit'ten önce."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookSet
from fusion_cli.engines.agent.hook_bridge import user_prompt_submit
from fusion_cli.engines.agent.hook_expansion import (
    MCP_PROMPT,
    command_source,
    queue_expansion,
    state_hooks,
)
from fusion_cli.engines.hooks.session import HookSession


class _Sink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


def _session(tmp_path: Path, body: str, matcher: str = "") -> tuple[HookSession, Path]:
    log = tmp_path / "girdi.jsonl"
    script = tmp_path / "kanca.py"
    script.write_text(
        f"import sys\nopen(r'{log}', 'a').write(sys.stdin.read().strip() + '\\n')\n{body}",
        encoding="utf-8",
    )
    commands, skipped = parse_hooks_block(
        {
            "UserPromptExpansion": [
                {
                    "matcher": matcher,
                    "hooks": [{"type": "command", "command": f"{sys.executable} {script}"}],
                }
            ]
        },
        source="kullanici",
        path=Path("settings.json"),
    )
    assert not skipped
    return HookSession(root=tmp_path, loader=lambda: HookSet(commands)), log


def _deps(session: HookSession):
    return SimpleNamespace(hooks=session, publisher=_Sink())


def _lines(log: Path) -> list[dict]:
    return [json.loads(x) for x in log.read_text().splitlines() if x] if log.exists() else []


def test_olay_tetiklenir_ve_claude_alanlarini_alir(tmp_path):
    assert "UserPromptExpansion" not in CLAUDE_ONLY_EVENTS
    session, log = _session(tmp_path, "print('ekip kontrol listesi')\n")
    queue_expansion(session, name="review", args="12 acil", source="userSettings")
    gate = asyncio.run(user_prompt_submit(_deps(session), "gövde"))
    assert gate.blocked is None
    assert "UserPromptExpansion hook additional context: ekip kontrol listesi" in gate.after
    (record,) = _lines(log)
    assert record["hook_event_name"] == "UserPromptExpansion"
    assert record["expansion_type"] == "slash_command"
    assert record["command_name"] == "review"
    assert record["command_args"] == "12 acil"
    assert record["command_source"] == "userSettings"
    assert record["prompt"] == "/review 12 acil"
    # Bir kez: sonraki düz istemde yeniden çalışmaz.
    asyncio.run(user_prompt_submit(_deps(session), "düz istem"))
    assert len(_lines(log)) == 1


def test_block_komutu_acmaz(tmp_path):
    body = 'print(\'{"decision": "block", "reason": "onay dosyası yok"}\')\n'
    session, _ = _session(tmp_path, body, matcher="deploy")
    queue_expansion(session, name="deploy", args="", source="projectSettings")
    gate = asyncio.run(user_prompt_submit(_deps(session), "dağıt"))
    assert gate.blocked is not None
    assert "UserPromptExpansion operation blocked by hook" in gate.blocked
    assert "onay dosyası yok" in gate.blocked


def test_cikis_2_stderr_ile_engeller(tmp_path):
    session, _ = _session(tmp_path, "sys.stderr.write('yasak komut')\nsys.exit(2)\n")
    queue_expansion(session, name="x", args="", source="userSettings", expansion_type=MCP_PROMPT)
    gate = asyncio.run(user_prompt_submit(_deps(session), "x"))
    assert gate.blocked is not None and "yasak komut" in gate.blocked


def test_eslesmeyen_komut_calismaz(tmp_path):
    session, log = _session(tmp_path, "", matcher="deploy")
    queue_expansion(session, name="review", args="", source="userSettings")
    gate = asyncio.run(user_prompt_submit(_deps(session), "x"))
    assert gate.blocked is None and not _lines(log)


def test_command_source_eslemesi():
    assert command_source("claude-plugin") == "plugin"
    assert command_source("proje") == "projectSettings"
    assert command_source("claude+codex") == "userSettings"


def test_state_hooks_kanca_yoksa_none():
    assert state_hooks(SimpleNamespace()) is None


def test_beceri_komutu_acilimi_kuyruga_yazar(tmp_path):
    from fusion_cli.cli.repl.skill_commands import skill_handler
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    folder = tmp_path / "ev" / ".claude" / "skills" / "gozden"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("---\nname: gozden\ndescription: d\n---\nGövde", "utf-8")
    state = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    assert state.capabilities is not None
    skill = state.capabilities.get_skill("gozden")
    assert skill is not None
    skill_handler(skill.qualified_name)(state, "PR 7")
    pending = state.hooks().pending_expansion
    assert pending is not None
    assert pending["command_name"] == "gozden"
    assert pending["command_args"] == "PR 7"
    assert pending["prompt"] == "/gozden PR 7"
