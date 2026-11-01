"""`PermissionDenied` kancası (#90) — Claude Code hooks başvurusu.

Claude: otomatik kip sınıflandırıcısı bir çağrıyı reddedince çalışır (elle ret, deny kuralı
ve PreToolUse engeli tetiklemez); `retry: true` modele yeniden deneyebileceğini söyler,
çıkış kodu/stderr yok sayılır. Ölçüldü (1 Kasım): olay "Fusion bu olayı tetiklemiyor" diye
atlanıyordu.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.auto_review import AutoClassifierMode
from fusion_cli.core.events import ToolExecuted
from fusion_cli.core.hooks.decision import verdict_from_run
from fusion_cli.core.hooks.events import HookEvent, HookRun, HookSet
from fusion_cli.core.tools import Tool, ToolContext, ToolEffect, ToolResult
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent import risk_classifier
from fusion_cli.engines.agent.approval import ApprovalMemory, ApprovalMode, build_policy
from fusion_cli.engines.agent.hook_permission_denied import RETRY_NOTE
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.hooks.session import HookSession

from .fakes import RecordingSink, ScriptedProvider, make_config, model_result, tool_call


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self._sink = sink

    def publish(self, event: object) -> None:
        self._sink.handle(event)


class _Reject:
    """Soru sorulamayan taraf: her soruyu reddeder (başsız koşu)."""

    async def confirm(self, request: object) -> bool:
        return False


def _hooks(tmp_path: Path, output: object, *, exit_code: int = 0, matcher: str = "*"):
    script = tmp_path / "kanca.py"
    body = json.dumps(output) if output is not None else ""
    script.write_text(
        "import sys, pathlib\n"
        f"pathlib.Path(r'{tmp_path / 'girdi.json'}').write_text(sys.stdin.read())\n"
        f"print({body!r})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    commands, skipped = parse_hooks_block(
        {
            "PermissionDenied": [
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
    return HookSession(root=tmp_path, loader=lambda: HookSet(commands))


def _price_tool(calls: list) -> Tool:
    return Tool(
        "store_update_price",
        "Mağazada fiyat güncelle",
        {"type": "object", "properties": {"sku": {}, "price": {}}},
        lambda args, context: calls.append(args) or ToolResult("tamam"),
        mutating=True,
        effect=ToolEffect.REMOTE_WRITE,
    )


async def _run(monkeypatch, tmp_path: Path, hooks: HookSession, *, verdict: str, interactive=False):
    agent = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("store_update_price", sku="A1", price=10)]),
            model_result("Fiyatı güncelleyemedim; izin verilmedi."),
        ]
    )
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: agent)
    judge = ScriptedProvider(
        [model_result(json.dumps({"karar": verdict, "gerekce": "kullanıcı bunu istemedi"}))]
    )
    monkeypatch.setattr(risk_classifier, "build_provider", lambda spec, **_: judge)
    memory = ApprovalMemory()
    calls: list = []
    sink = RecordingSink()
    deps = AgentDeps(
        config=make_config(runtime={"auto_classifier": AutoClassifierMode.ASK_ONLY}),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, _Reject(), memory),
        tool_context=ToolContext(root=tmp_path),
        approval_mode=lambda: ApprovalMode.AUTO,
        auto_review=memory.auto_review,
        hooks=hooks,
        interactive=interactive,
    )
    deps.base_registry.register(_price_tool(calls))
    await run_agent("A1 ürününün fiyatını 10 yap", deps, verify=False, self_review=False)
    return sink, calls


def _tool_results(sink: RecordingSink) -> str:
    return "\n".join(e.output for e in sink.events if isinstance(e, ToolExecuted))


def _retry(value: bool) -> dict[str, object]:
    return {"hookSpecificOutput": {"hookEventName": "PermissionDenied", "retry": value}}


async def test_denetci_reddi_kancayi_calistirir_girdi_claude_seklinde(monkeypatch, tmp_path):
    hooks = _hooks(tmp_path, _retry(True), matcher="mcp__.*|store_update_price")
    sink, calls = await _run(monkeypatch, tmp_path, hooks, verdict="riskli")
    assert not calls
    girdi = json.loads((tmp_path / "girdi.json").read_text())
    assert girdi["hook_event_name"] == "PermissionDenied"
    assert girdi["tool_name"] == "store_update_price"
    assert girdi["tool_input"] == {"sku": "A1", "price": 10}
    assert girdi["tool_use_id"]
    assert girdi["reason"] == "kullanıcı bunu istemedi"
    assert RETRY_NOTE in _tool_results(sink)


async def test_retry_yoksa_ret_aynen_kalir(monkeypatch, tmp_path):
    hooks = _hooks(tmp_path, _retry(False))
    sink, _ = await _run(monkeypatch, tmp_path, hooks, verdict="riskli")
    assert (tmp_path / "girdi.json").exists()
    assert RETRY_NOTE not in _tool_results(sink)


async def test_etkilesimli_oturumda_soru_elle_karardir_kanca_calismaz(monkeypatch, tmp_path):
    hooks = _hooks(tmp_path, _retry(True))
    await _run(monkeypatch, tmp_path, hooks, verdict="riskli", interactive=True)
    assert not (tmp_path / "girdi.json").exists()


async def test_denetci_riskli_demediyse_kanca_calismaz(monkeypatch, tmp_path):
    hooks = _hooks(tmp_path, _retry(True))
    _, calls = await _run(monkeypatch, tmp_path, hooks, verdict="guvenli")
    assert calls
    assert not (tmp_path / "girdi.json").exists()


@pytest.mark.parametrize("exit_code", [1, 2])
def test_cikis_kodu_ve_stderr_yok_sayilir_retry_okunur(exit_code):
    command = HookSet(
        parse_hooks_block(
            {"PermissionDenied": [{"hooks": [{"type": "command", "command": "x"}]}]},
            source="kullanici",
            path=Path("settings.json"),
        )[0]
    ).commands[0]
    run = HookRun(command, exit_code, stdout=json.dumps(_retry(True)), stderr="kötü bir şey oldu")
    verdict = verdict_from_run(HookEvent.PERMISSION_DENIED, run, "Bash")
    assert verdict.retry and not verdict.blocked and not verdict.errors
