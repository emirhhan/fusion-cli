"""`PreModelSwitch` / `PostModelSwitch` kancaları (#90): `/model agent <id>`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fusion_cli.cli.repl.commands import _model
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookSet
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.hook_model_switch import canonical
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path: Path, hooks: dict[str, tuple[str, str]]) -> tuple[ReplState, Path]:
    block: dict[str, list[dict[str, object]]] = {}
    for event, (matcher, body) in hooks.items():
        script = tmp_path / f"{event}.py"
        script.write_text(
            f"import sys\nopen(r'{tmp_path / event}.json', 'w').write(sys.stdin.read())\n{body}",
            encoding="utf-8",
        )
        block[event] = [
            {
                "matcher": matcher,
                "hooks": [{"type": "command", "command": f"{sys.executable} {script}"}],
            }
        ]
    commands, skipped = parse_hooks_block(block, source="kullanici", path=Path("settings.json"))
    assert not skipped
    config = make_config(agent=ModelSpec(name="agent", model="anthropic/claude-sonnet-5"))
    state = ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path / "ev")
    state.hook_session = HookSession(root=tmp_path, loader=lambda: HookSet(commands))
    return state, tmp_path


def test_olaylar_artik_tetikleniyor():
    assert "PreModelSwitch" not in CLAUDE_ONLY_EVENTS
    assert "PostModelSwitch" not in CLAUDE_ONLY_EVENTS
    assert canonical("anthropic/claude-opus-5[1m]") == "claude-opus-5"


def test_pre_deny_modeli_degistirmez(tmp_path):
    body = (
        'print(\'{"hookSpecificOutput": {"hookEventName": "PreModelSwitch", '
        '"permissionDecision": "deny", "permissionDecisionReason": "pahalı"}}\')\n'
    )
    state, d = _state(tmp_path, {"PreModelSwitch": ("claude-opus-5", body)})
    text = _model(state, "agent anthropic/claude-opus-5")
    assert state.config.agent.model == "anthropic/claude-sonnet-5"
    assert "pahalı" in text
    payload = json.loads((d / "PreModelSwitch.json").read_text())
    assert payload["hook_event_name"] == "PreModelSwitch"
    assert payload["from_model"] == "anthropic/claude-sonnet-5"
    assert payload["to_model"] == "anthropic/claude-opus-5"
    assert payload["requested_model"] == "anthropic/claude-opus-5"
    assert payload["source"] == "command"
    assert payload["pricing"] == "default"


def test_cikis_2_ve_ask_reddeder(tmp_path):
    state, _ = _state(tmp_path, {"PreModelSwitch": ("", "sys.stderr.write('yok')\nsys.exit(2)\n")})
    _model(state, "agent anthropic/claude-opus-5")
    assert state.config.agent.model == "anthropic/claude-sonnet-5"
    body = (
        'print(\'{"hookSpecificOutput": {"hookEventName": "PreModelSwitch", '
        '"permissionDecision": "ask", "permissionDecisionReason": "emin misin"}}\')\n'
    )
    state, _ = _state(tmp_path, {"PreModelSwitch": ("", body)})
    assert "emin misin" in _model(state, "agent anthropic/claude-opus-5")
    assert state.config.agent.model == "anthropic/claude-sonnet-5"


def test_izin_ve_post_baglami_sonraki_tura(tmp_path):
    state, d = _state(
        tmp_path,
        {
            "PreModelSwitch": ("", 'print(\'{"systemMessage": "maliyet: düşük"}\')\n'),
            "PostModelSwitch": (".*opus.*", "print('Opus: işi alt ajanlara böl')\n"),
        },
    )
    text = _model(state, "agent anthropic/claude-opus-5")
    assert state.config.agent.model == "anthropic/claude-opus-5"
    assert "maliyet: düşük" in text
    assert json.loads((d / "PostModelSwitch.json").read_text())["to_model"] == (
        "anthropic/claude-opus-5"
    )
    notes = state.hook_session.take_rewake_notes()
    assert notes == ("PostModelSwitch hook additional context: Opus: işi alt ajanlara böl",)


def test_ayni_model_kanca_calistirmaz(tmp_path):
    state, d = _state(tmp_path, {"PreModelSwitch": ("", "sys.exit(2)\n")})
    _model(state, "agent anthropic/claude-sonnet-5")
    assert not (d / "PreModelSwitch.json").exists()
