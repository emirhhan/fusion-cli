"""`PermissionRequest` kancası (#90) — Claude Code hooks başvurusu.

Ölçüldü (1 Kasım): olay "Fusion bu olayı tetiklemiyor" diye atlanıyordu; izin sorusunu
kancayla otomatik onaylayan/reddeden Claude ayarı Fusion'da hiç çalışmıyordu.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import HookSet
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalReply, ApprovalRequest
from fusion_cli.engines.hooks.notify import NotifyingPrompter
from fusion_cli.engines.hooks.session import HookSession


class _Tool:
    name = "run_shell"


class _Soran:
    def __init__(self) -> None:
        self.soruldu = 0

    async def confirm(self, request: ApprovalRequest) -> ApprovalAnswer:
        self.soruldu += 1
        return ApprovalAnswer.UNAVAILABLE


def _prompter(tmp_path: Path, output: dict[str, object] | None, matcher: str = "Bash"):
    script = tmp_path / "kanca.py"
    body = json.dumps(output) if output is not None else ""
    script.write_text(
        "import json, sys, pathlib\n"
        f"pathlib.Path(r'{tmp_path / 'girdi.json'}').write_text(sys.stdin.read())\n"
        f"print({body!r})\n",
        encoding="utf-8",
    )
    commands, skipped = parse_hooks_block(
        {
            "PermissionRequest": [
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
    session = HookSession(root=tmp_path, loader=lambda: HookSet(commands))
    inner = _Soran()
    return NotifyingPrompter(inner, session, delay_s=60), inner


def _sor(prompter: NotifyingPrompter):
    request = ApprovalRequest(tool=_Tool(), args={"command": "npm test"}, danger=None)
    return asyncio.run(prompter.confirm(request))


def _karar(behavior: str, **extra: object) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": behavior, **extra},
        }
    }


def test_allow_soruyu_sormadan_izin_verir_girdi_claude_seklinde(tmp_path):
    prompter, inner = _prompter(tmp_path, _karar("allow"))
    assert _sor(prompter) is ApprovalAnswer.ONCE
    assert inner.soruldu == 0
    girdi = json.loads((tmp_path / "girdi.json").read_text())
    assert girdi["hook_event_name"] == "PermissionRequest"
    assert girdi["tool_name"] == "Bash"
    assert girdi["tool_input"]["command"] == "npm test"
    assert "tool_use_id" not in girdi


def test_deny_mesaji_modele_gerekce_olur_interrupt_turu_durdurur(tmp_path):
    prompter, _ = _prompter(tmp_path, _karar("deny", message="testler CI'da koşar"))
    answer = _sor(prompter)
    assert isinstance(answer, ApprovalReply)
    assert answer.answer is ApprovalAnswer.DENY and answer.note == "testler CI'da koşar"
    prompter, _ = _prompter(tmp_path, _karar("deny", interrupt=True))
    assert _sor(prompter) is ApprovalAnswer.DENY


@pytest.mark.parametrize("output", [None, {"systemMessage": "bakıldı"}])
def test_kararsiz_kanca_akisi_degistirmez(tmp_path, output):
    prompter, inner = _prompter(tmp_path, output)
    assert _sor(prompter) is ApprovalAnswer.UNAVAILABLE
    assert inner.soruldu == 1


def test_eslesmeyen_arac_kancayi_calistirmaz(tmp_path):
    prompter, _ = _prompter(tmp_path, _karar("allow"), matcher="Write")
    assert _sor(prompter) is ApprovalAnswer.UNAVAILABLE
    assert not (tmp_path / "girdi.json").exists()


def test_agent_turu_izin_isteginde_desteklenmez():
    commands, skipped = parse_hooks_block(
        {"PermissionRequest": [{"hooks": [{"type": "agent", "prompt": "x"}]}]},
        source="kullanici",
        path=Path("settings.json"),
    )
    assert not commands and "desteklemez" in skipped[0].reason
