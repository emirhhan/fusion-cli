"""`StopFailure` kancası (#90): tur API hatasıyla bitince `Stop` yerine çalışır."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.engines.agent.hook_stop import continue_until_stop_allowed
from fusion_cli.engines.agent.hook_stop_failure import error_type
from fusion_cli.engines.hooks.session import HookSession


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        ("Error code: 429 - Too Many Requests", "rate_limit"),
        ("AuthenticationError: invalid x-api-key", "authentication_failed"),
        ("Your credit balance is too low", "billing_error"),
        ("529 Overloaded", "overloaded"),
        ("InternalServerError 500", "server_error"),
        ("tuhaf", "unknown"),
    ],
)
def test_ham_hata_claude_turune_cevrilir(raw, kind):
    assert error_type(raw) == kind


def _deps(tmp_path: Path, event: str, matcher: str = ""):
    script = tmp_path / "kanca.py"
    script.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path(r'{tmp_path / 'girdi.json'}').write_text(sys.stdin.read())\n"
        'print(\'{"decision": "block", "reason": "yok sayılmalı"}\')\n'
        "sys.exit(2)\n",
        encoding="utf-8",
    )
    commands, skipped = parse_hooks_block(
        {
            event: [
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
    return SimpleNamespace(hooks=session, budget=None)


def _outcome(**fields: object):
    base = {
        "final_text": "API Error: Rate limit reached",
        "messages": [],
        "ok": False,
        "budget_stopped": False,
        "model_error": None,
    }
    return SimpleNamespace(**{**base, **fields})


async def _rerun(prompt, past):  # pragma: no cover - çağrılmamalı
    raise AssertionError("StopFailure turu sürdürmemeli")


def test_api_hatasinda_stopfailure_calisir_karar_yok_sayilir(tmp_path):
    deps = _deps(tmp_path, "StopFailure", matcher="rate_limit")
    outcome = _outcome(model_error="429 Too Many Requests")
    result = asyncio.run(continue_until_stop_allowed(deps, outcome, _rerun, subagent=False))
    assert result is outcome
    girdi = json.loads((tmp_path / "girdi.json").read_text())
    assert girdi["hook_event_name"] == "StopFailure"
    assert girdi["error"] == "rate_limit"
    assert girdi["error_details"] == "429 Too Many Requests"
    assert girdi["last_assistant_message"] == "API Error: Rate limit reached"


def test_hatasiz_turda_ve_alt_ajanda_stopfailure_calismaz(tmp_path):
    deps = _deps(tmp_path, "StopFailure")
    asyncio.run(continue_until_stop_allowed(deps, _outcome(), _rerun, subagent=False))
    error = _outcome(model_error="500")
    asyncio.run(continue_until_stop_allowed(deps, error, _rerun, subagent=True))
    assert not (tmp_path / "girdi.json").exists()


def test_stopfailure_ciktisi_hata_ya_da_engel_uretmez(tmp_path):
    deps = _deps(tmp_path, "StopFailure")
    verdict = asyncio.run(
        deps.hooks.emit(HookEvent.STOP_FAILURE, subjects=("unknown",), fields={"error": "unknown"})
    )
    assert not verdict.blocked and not verdict.errors and not verdict.system_messages
