"""Ertelenen çağrı sürdürülen oturumda PreToolUse'tan yeniden geçer (#114).

Claude Code: `-p --resume` ile sürdürülen oturumda `defer` edilmiş çağrı yeniden
değerlendirilir; kanca `allow` derse araç çalışır, `defer` derse tur yine ertelenir.
"""

from __future__ import annotations

from fusion_cli.core.hooks.events import HookEvent
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.deferred_resume import take_deferred
from fusion_cli.engines.agent.hook_bridge import TOOL_DEFERRED
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.hooks.notify import notifying

from .fakes import RecordingSink, ScriptedProvider, make_config, model_result, tool_call
from .test_hooks_loop import _kanca, _Kaydeden, _oturum, _Publisher, _satirlar

_YAZ = tool_call("write_file", path="a.txt", content="x")


def _gecmis() -> list[Message]:
    return [
        Message("user", "a.txt yaz"),
        Message("assistant", "", tool_calls=(_YAZ,)),
        Message("tool", TOOL_DEFERRED, tool_call_id=_YAZ.id, name=_YAZ.name, ok=False),
    ]


def _karar(kayit, karar: str) -> str:
    return (
        f"open({str(kayit)!r}, 'a').write(json.dumps(data) + '\\n')\n"
        "print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PreToolUse',"
        f" 'permissionDecision': {karar!r}}}}}))\n"
    )


async def _surdur(monkeypatch, tmp_path, results, session, *, interactive=False):
    provider = ScriptedProvider(results)
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, notifying(_Kaydeden(), session)),
        tool_context=ToolContext(root=tmp_path),
        hooks=session,
    )
    deps.interactive = interactive
    outcome = await run_agent("devam", deps, history=_gecmis())
    return outcome, provider


async def test_surdurulen_ertelenen_cagri_allow_ile_calisir(monkeypatch, tmp_path):
    kayit = tmp_path / "pre.jsonl"
    session = _oturum(
        tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _karar(kayit, "allow"), "Write")
    )
    outcome, provider = await _surdur(monkeypatch, tmp_path, [model_result("tamam")], session)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "x"
    assert [row["tool_name"] for row in _satirlar(kayit)] == ["Write"]
    # Model, tool_use'un hemen ardından GERÇEK sonucu görür; erteleme metni kalmaz.
    istek = provider.seen_messages[0]
    sonuc = next(m for m in istek if m.role == "tool")
    assert sonuc.tool_call_id == _YAZ.id and sonuc.content != TOOL_DEFERRED
    roller = [m.role for m in istek if m.role != "system"]
    assert roller[-3:] == ["assistant", "tool", "user"]
    assert outcome.stop_reason != TOOL_DEFERRED


async def test_surdurulen_cagri_yine_defer_edilirse_tur_ertelenir(monkeypatch, tmp_path):
    kayit = tmp_path / "pre.jsonl"
    session = _oturum(
        tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _karar(kayit, "defer"), "Write")
    )
    outcome, provider = await _surdur(monkeypatch, tmp_path, [model_result("x")], session)
    assert not (tmp_path / "a.txt").exists()
    assert outcome.stop_reason == TOOL_DEFERRED
    assert outcome.deferred_tool_use is not None
    assert provider.calls == 0


async def test_surdurulen_cagri_deny_ile_calismaz(monkeypatch, tmp_path):
    kayit = tmp_path / "pre.jsonl"
    session = _oturum(
        tmp_path, _kanca(tmp_path, HookEvent.PRE_TOOL_USE, _karar(kayit, "deny"), "Write")
    )
    _, provider = await _surdur(monkeypatch, tmp_path, [model_result("tamam")], session)
    assert not (tmp_path / "a.txt").exists()
    sonuc = next(m for m in provider.seen_messages[0] if m.role == "tool")
    assert sonuc.content != TOOL_DEFERRED and sonuc.ok is False


def test_ertelemeden_sonra_yeni_arac_turu_varsa_yeniden_degerlendirilmez():
    gecmis = [
        *_gecmis(),
        Message("assistant", "", tool_calls=(tool_call("read_file", path="b"),)),
    ]
    assert take_deferred(gecmis) is None
    assert len(gecmis) == 4
    duz = _gecmis()
    assert take_deferred(duz) == (2, _YAZ)
    assert len(duz) == 2
