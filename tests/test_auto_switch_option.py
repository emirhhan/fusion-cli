"""Onay kartında "Yes, and switch to auto mode" — Claude gibi (#82).

Claude (permissions#permission-system; permission-modes#switch-permission-modes): Manuel ve
acceptEdits kiplerinde, auto kullanılabiliyorsa kart bu seçeneği sunar; seçilirse çağrı
çalışır ve oturum auto kipine geçer. Plan, auto, bypass ve dontAsk kiplerinde sunulmaz.
"""

from __future__ import annotations

from fusion_cli.appserver.bridges import _approval_options
from fusion_cli.cli.prompter import parse_console_answer
from fusion_cli.core.tools import Tool
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)
from fusion_cli.engines.agent.auto_switch import AutoSwitch
from fusion_cli.ui import messages


def _kabuk() -> Tool:
    return Tool(name="run_shell", description="", parameters={}, run=lambda a, c: None)


class _Soran:
    def __init__(self, cevap: object) -> None:
        self.cevap = cevap
        self.soruldu: list[object] = []

    async def confirm(self, request):
        self.soruldu.append(request)
        return self.cevap


def _bellek(kip: list[ApprovalMode], kullanilabilir: bool = True) -> ApprovalMemory:
    bellek = ApprovalMemory()

    def _gec() -> None:
        kip.append(ApprovalMode.AUTO)

    bellek.auto_switch = AutoSwitch(available=lambda: kullanilabilir, switch=_gec)
    return bellek


async def test_manuel_kipte_auto_secenegi_sunulur_secilince_kip_gecer(tmp_path):
    kipler: list[ApprovalMode] = []
    bellek = _bellek(kipler)
    soran = _Soran(ApprovalAnswer.AUTO)
    politika = build_policy(ApprovalMode.SECURITY, soran, bellek)
    istek = build_request(_kabuk(), {"command": "npm install"}, root=tmp_path)
    assert await politika.decide(istek) is Decision.ALLOW
    assert soran.soruldu[0].offers_auto is True
    assert kipler == [ApprovalMode.AUTO]
    assert bellek.auto_review.mode_switches == 1


async def test_accept_edits_kipinde_de_sunulur(tmp_path):
    kipler: list[ApprovalMode] = []
    soran = _Soran(ApprovalAnswer.ONCE)
    politika = build_policy(ApprovalMode.ACCEPT_EDITS, soran, _bellek(kipler))
    istek = build_request(_kabuk(), {"command": "npm install"}, root=tmp_path)
    assert await politika.decide(istek) is Decision.ALLOW
    assert soran.soruldu[0].offers_auto is True and kipler == []


async def test_auto_kullanilamiyorsa_ya_da_plan_kipinde_sunulmaz(tmp_path):
    kipler: list[ApprovalMode] = []
    soran = _Soran(ApprovalAnswer.AUTO)
    politika = build_policy(ApprovalMode.SECURITY, soran, _bellek(kipler, kullanilabilir=False))
    istek = build_request(_kabuk(), {"command": "npm install"}, root=tmp_path)
    # Sunulmayan seçenek seçilmiş gibi gelirse kip değişmez, çağrı yine çalışmaz.
    assert await politika.decide(istek) is Decision.DENIED
    assert soran.soruldu[0].offers_auto is False and kipler == []
    plan = build_policy(ApprovalMode.PLAN, _Soran(ApprovalAnswer.ONCE), _bellek(kipler))
    plan_soran = plan._prompter
    await plan.decide(build_request(_kabuk(), {"command": "npm install"}, root=tmp_path))
    assert plan_soran.soruldu[0].offers_auto is False


def test_kart_seceneklerinde_ve_satir_icinde_auto_gecisi(tmp_path):
    istek = build_request(_kabuk(), {"command": "npm install"}, root=tmp_path)
    assert "auto" not in {s["deger"] for s in _approval_options(istek, tmp_path)}
    from dataclasses import replace

    sunulan = replace(istek, offers_auto=True)
    secenek = {s["deger"]: s for s in _approval_options(sunulan, tmp_path)}["auto"]
    assert secenek["etiket"] == messages.APPROVAL_AUTO_SWITCH
    assert parse_console_answer("oto", sunulan) is ApprovalAnswer.AUTO
    assert parse_console_answer("oto", istek) is not ApprovalAnswer.AUTO


def test_repl_durumu_gecisi_baglar_ve_disable_auto_mode_kapatir(tmp_path):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    state = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    state.approval = ApprovalMode.SECURITY
    gecis = state.approval_memory.auto_switch
    assert gecis is not None and gecis.available()
    gecis.switch()
    assert state.approval is ApprovalMode.AUTO
    assert not gecis.available()  # auto'da seçenek sunulmaz
    state.approval = ApprovalMode.ACCEPT_EDITS
    state.auto_available = False
    assert not gecis.available()


async def test_dongude_gecis_onaylanan_cagriyi_iptal_etmez(monkeypatch, tmp_path):
    from fusion_cli.core.tools import ToolContext, ToolEffect, ToolResult
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent

    from .fakes import RecordingSink, ScriptedProvider, make_config, model_result, tool_call

    ajan = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("store_update_price", sku="A1", price=10)]),
            model_result("Fiyat güncellendi."),
        ]
    )
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **_: ajan)
    kip = [ApprovalMode.SECURITY]
    bellek = ApprovalMemory()
    bellek.auto_switch = AutoSwitch(
        available=lambda: kip[-1] is ApprovalMode.SECURITY,
        switch=lambda: kip.append(ApprovalMode.AUTO),
    )
    soran = _Soran(ApprovalAnswer.AUTO)
    cagrilar: list[object] = []

    class _Yayinci:
        def __init__(self) -> None:
            self.sink = RecordingSink()

        def publish(self, event: object) -> None:
            self.sink.handle(event)

    deps = AgentDeps(
        config=make_config(runtime={"auto_classifier": "off"}),
        publisher=_Yayinci(),
        policy=build_policy(ApprovalMode.SECURITY, soran, bellek),
        tool_context=ToolContext(root=tmp_path),
        approval_mode=lambda: kip[-1],
        policy_factory=lambda: build_policy(kip[-1], soran, bellek),
        approval_revision=lambda: (kip[-1], bellek.revision),
        auto_review=bellek.auto_review,
    )
    deps.base_registry.register(
        Tool(
            "store_update_price",
            "Mağazada fiyat güncelle",
            {"type": "object", "properties": {"sku": {}, "price": {}}},
            lambda args, context: cagrilar.append(args) or ToolResult("tamam"),
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )
    await run_agent("A1 fiyatını 10 yap", deps, verify=False, self_review=False)
    assert cagrilar and len(soran.soruldu) == 1
    assert kip[-1] is ApprovalMode.AUTO
