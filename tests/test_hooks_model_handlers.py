"""`mcp_tool`, `prompt` ve `agent` kanca türleri (#93) — Claude Code hooks başvurusu.

Ölçüldü (1 Kasım): üç tür "tür henüz desteklenmiyor" diye atlanıyordu; `Stop` üstündeki
`prompt` kancası hiç çalışmadan ajan durabiliyordu.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.core.tools import ToolResult
from fusion_cli.engines.agent.hook_services import bind_hook_services, hook_model_spec
from fusion_cli.engines.hooks.handlers import HookServices, render_prompt, substitute_paths
from fusion_cli.engines.hooks.session import HookSession


def _parse(event: str, *handlers: dict[str, object]):
    return parse_hooks_block(
        {event: [{"matcher": "", "hooks": list(handlers)}]},
        source="kullanici",
        path=Path("settings.json"),
    )


def _session(tmp_path: Path, event: str, handler: dict[str, object], services: HookServices):
    commands, skipped = _parse(event, handler)
    assert not skipped
    session = HookSession(root=tmp_path, loader=lambda: HookSet(commands))
    session.services = services
    return session


def _model(answer: str, seen: list[str] | None = None) -> HookServices:
    async def call(prompt: str, model: str, timeout_s: float) -> str:
        if seen is not None:
            seen.append(prompt)
        return answer

    return HookServices(model_call=call, agent_call=call)


def test_uc_tur_alanlariyla_okunur_varsayilan_sureler_claude_ile_ayni():
    commands, skipped = _parse(
        "PreToolUse",
        {"type": "prompt", "prompt": "uygun mu? $ARGUMENTS", "continueOnBlock": True},
        {"type": "agent", "prompt": "testler geçiyor mu?", "model": "haiku"},
        {"type": "mcp_tool", "server": "tara", "tool": "scan", "input": {"p": "${cwd}"}},
        {"type": "mcp_tool", "tool": "scan"},
    )
    assert [(c.handler, c.timeout_s) for c in commands] == [
        ("prompt", 30.0),
        ("agent", 60.0),
        ("mcp_tool", 600.0),
    ]
    assert commands[0].continue_on_block is True
    assert commands[1].model == "haiku" and commands[1].continue_on_block is False
    assert (commands[2].server, commands[2].tool) == ("tara", "scan")
    assert json.loads(commands[2].tool_input_json) == {"p": "${cwd}"}
    assert len(skipped) == 1 and "server" in skipped[0].reason


def test_oturum_baslangicinda_prompt_desteklenmez():
    commands, skipped = _parse("SessionStart", {"type": "prompt", "prompt": "x"})
    assert not commands and "desteklemez" in skipped[0].reason


def test_arguments_yer_tutucusu_ve_kacis():
    payload = {"a": 1}
    assert render_prompt("bak: $ARGUMENTS", payload) == 'bak: {"a": 1}'
    assert render_prompt("fiyat \\$1.00", payload) == 'fiyat $1.00\n\n{"a": 1}'


def test_input_yollari_kanca_girdisinden_dolar():
    payload = {"tool_input": {"file_path": "/a.py", "n": 3}}
    value = {
        "f": "${tool_input.file_path}",
        "s": "dosya ${tool_input.file_path}",
        "n": "${tool_input.n}",
    }
    assert substitute_paths(value, payload) == {"f": "/a.py", "s": "dosya /a.py", "n": 3}


def test_pretooluse_ok_false_reddeder_ve_turu_bitirir(tmp_path):
    seen: list[str] = []
    session = _session(
        tmp_path,
        "PreToolUse",
        {"type": "prompt", "prompt": "Bash .env okumasın: $ARGUMENTS"},
        _model('{"ok": false, "reason": ".env okunuyor"}', seen),
    )
    verdict = asyncio.run(session.emit(HookEvent.PRE_TOOL_USE, subjects=("Bash",)))
    assert verdict.blocked and verdict.halt
    assert ".env okunuyor" in verdict.reason
    assert '"hook_event_name": "PreToolUse"' in seen[0]


def test_continue_on_block_ve_agent_turu_surdurur(tmp_path):
    for handler in (
        {"type": "prompt", "prompt": "x", "continueOnBlock": True},
        {"type": "agent", "prompt": "x"},
    ):
        session = _session(
            tmp_path, "PreToolUse", handler, _model('{"ok": false, "reason": "hayır"}')
        )
        verdict = asyncio.run(session.emit(HookEvent.PRE_TOOL_USE, subjects=("Bash",)))
        assert verdict.blocked and not verdict.halt and "hayır" in verdict.reason


def test_stop_ok_false_devam_ettirir_impossible_durdurur(tmp_path):
    handler = {"type": "prompt", "prompt": "bitti mi?"}
    session = _session(tmp_path, "Stop", handler, _model('{"ok": false, "reason": "test yaz"}'))
    verdict = asyncio.run(session.emit(HookEvent.STOP))
    assert verdict.blocked and verdict.reason == "test yaz"
    impossible = '{"ok": false, "reason": "olmaz", "impossible": true}'
    session = _session(tmp_path, "Stop", handler, _model(impossible))
    assert not asyncio.run(session.emit(HookEvent.STOP)).blocked


def test_ok_true_ve_bozuk_yanit(tmp_path):
    handler = {"type": "prompt", "prompt": "x"}
    session = _session(tmp_path, "Stop", handler, _model('{"ok": true}'))
    assert not asyncio.run(session.emit(HookEvent.STOP)).blocked
    session = _session(tmp_path, "Stop", handler, _model("bilmiyorum"))
    verdict = asyncio.run(session.emit(HookEvent.STOP))
    assert not verdict.blocked and verdict.errors


def test_model_erisimi_yoksa_engellemeyen_hata(tmp_path):
    session = _session(tmp_path, "Stop", {"type": "prompt", "prompt": "x"}, HookServices())
    verdict = asyncio.run(session.emit(HookEvent.STOP))
    assert not verdict.blocked and verdict.errors


def test_mcp_tool_metin_icerigi_stdout_gibi_okunur(tmp_path):
    calls: list[tuple[str, str, dict[str, object]]] = []

    async def mcp(server: str, tool: str, args):
        calls.append((server, tool, dict(args)))
        return json.dumps({"decision": "block", "reason": "açık var"}), False

    handler = {
        "type": "mcp_tool",
        "server": "tara",
        "tool": "scan",
        "input": {"file_path": "${tool_input.file_path}"},
    }
    session = _session(tmp_path, "PostToolUse", handler, HookServices(mcp_call=mcp))
    verdict = asyncio.run(
        session.emit(
            HookEvent.POST_TOOL_USE,
            subjects=("Write",),
            fields={"tool_name": "Write", "tool_input": {"file_path": "/x.py"}},
        )
    )
    assert calls == [("tara", "scan", {"file_path": "/x.py"})]
    assert verdict.blocked and verdict.reason == "açık var"


def test_mcp_tool_hata_ve_bagli_olmayan_sunucu_engellemez(tmp_path):
    async def failing(server: str, tool: str, args):
        return "patladı", True

    async def missing(server: str, tool: str, args):
        raise LookupError(server)

    handler = {"type": "mcp_tool", "server": "tara", "tool": "scan"}
    for services in (HookServices(mcp_call=failing), HookServices(mcp_call=missing)):
        session = _session(tmp_path, "PreToolUse", handler, services)
        verdict = asyncio.run(session.emit(HookEvent.PRE_TOOL_USE, subjects=("Bash",)))
        assert not verdict.blocked and verdict.errors


def test_ajan_turu_mcp_aracini_defterden_bulur(tmp_path):
    async def run(args, context):
        return ToolResult(output=f"tamam {args['x']}")

    tool = SimpleNamespace(run=run)
    registry = SimpleNamespace(get=lambda name: tool if name == "tara__scan" else None)
    hooks = HookSession(root=tmp_path, loader=HookSet)
    deps = SimpleNamespace(hooks=hooks, base_registry=registry, tool_context=None, config=None)
    bind_hook_services(deps, run_agent=None)  # type: ignore[arg-type]
    assert hooks.services is not None and hooks.services.mcp_call is not None
    assert asyncio.run(hooks.services.mcp_call("tara", "scan", {"x": 1})) == ("tamam 1", False)


def test_model_alani_cozumu():
    judge = SimpleNamespace(model="anthropic/claude-haiku-4-5")
    config = SimpleNamespace(judge=judge, agent=judge, candidates=())
    assert hook_model_spec(config, "") is judge  # type: ignore[arg-type]
    assert hook_model_spec(config, "openai/gpt-x").model == "openai/gpt-x"  # type: ignore[arg-type]
    assert hook_model_spec(config, "haiku") is judge  # type: ignore[arg-type]


def test_status_message_kanca_calisirken_gosterilir(tmp_path):
    shown: list[str] = []
    session = _session(
        tmp_path,
        "Stop",
        {"type": "prompt", "prompt": "x", "statusMessage": "Testler denetleniyor"},
        _model('{"ok": true}'),
    )
    session.status_sink = shown.append
    asyncio.run(session.emit(HookEvent.STOP))
    assert shown == ["Testler denetleniyor"]


def test_ajan_turu_status_satirini_yayinciya_baglar(tmp_path):
    published: list[object] = []
    hooks = HookSession(root=tmp_path, loader=HookSet)
    deps = SimpleNamespace(
        hooks=hooks, publisher=SimpleNamespace(publish=published.append), config=None
    )
    bind_hook_services(deps, run_agent=None)  # type: ignore[arg-type]
    assert hooks.status_sink is not None
    hooks.status_sink("bekle")
    assert getattr(published[0], "text", "") == "bekle"


def test_async_kanca_json_baglami_sonraki_tura_gider(tmp_path):
    import sys

    body = json.dumps(
        {
            "systemMessage": "biçimlendi",
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": "dosya değişti",
            },
        }
    )
    script = tmp_path / "kanca.py"
    script.write_text(f"print({body!r})", encoding="utf-8")
    command = f"{sys.executable} {script}"
    commands, _ = _parse("PostToolUse", {"type": "command", "command": command, "async": True})
    session = HookSession(root=tmp_path, loader=lambda: HookSet(commands))

    async def run() -> None:
        await session.emit(HookEvent.POST_TOOL_USE, subjects=("Write",))
        await asyncio.gather(*session._background)

    asyncio.run(run())
    (note,) = session.take_rewake_notes()
    assert "biçimlendi" in note and "dosya değişti" in note
