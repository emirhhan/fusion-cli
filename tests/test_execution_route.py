"""Basit ve profesyonel yürütme yolları arasındaki hibrit karar."""

from __future__ import annotations

from fusion_cli.core.execution_mode import ExecutionMode
from fusion_cli.engines.agent.classify import TaskClassification, TaskKind
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.execution_route import ExecutionRoute, choose_execution_route


def _policy(*, complex_task: bool = False, effect: str | None = None, tools: bool = True):
    return ExecutionPolicy(
        is_web=False,
        offer_tools=tools,
        requires_tool_evidence=effect is not None,
        required_effect=effect,
        complex_task=complex_task,
    )


def test_karmasik_gorev_otomatik_workflow_secer():
    classification = TaskClassification(primary=TaskKind.FEATURE, confidence=1.0)

    decision = choose_execution_route(
        "özellik ekle", classification, _policy(complex_task=True), ExecutionMode.AUTO
    )

    assert decision.route is ExecutionRoute.WORKFLOW
    assert decision.reasons == ("karmaşık görev türü: feature",)


def test_dis_etki_kisa_olsa_bile_workflow_secer():
    classification = TaskClassification(primary=TaskKind.GENERAL, confidence=0.0)

    decision = choose_execution_route(
        "repoyu pushla",
        classification,
        _policy(effect="git_push"),
        ExecutionMode.AUTO,
    )

    assert decision.route is ExecutionRoute.WORKFLOW
    assert decision.reasons == ("doğrulanması gereken dış etki: git_push",)


def test_acik_basit_sohbet_hizli_yolu_secer():
    classification = TaskClassification(primary=TaskKind.GENERAL, confidence=1.0)

    decision = choose_execution_route(
        "merhaba", classification, _policy(tools=False), ExecutionMode.AUTO
    )

    assert decision.route is ExecutionRoute.FAST
    assert decision.reasons == ("araç gerektirmeyen basit görev",)


def test_belirsiz_gorev_hizli_baslar_ama_yukseltilebilir():
    classification = TaskClassification(primary=TaskKind.GENERAL, confidence=0.0)

    decision = choose_execution_route(
        "şuna bir bak", classification, _policy(), ExecutionMode.AUTO
    )

    assert decision.route is ExecutionRoute.FAST_PROMOTABLE
    assert decision.reasons == ("görev kapsamı çalışma sırasında netleşecek",)


def test_always_modu_basit_sohbeti_de_workflowa_alir():
    classification = TaskClassification(primary=TaskKind.GENERAL, confidence=1.0)

    decision = choose_execution_route(
        "merhaba", classification, _policy(tools=False), ExecutionMode.ALWAYS
    )

    assert decision.route is ExecutionRoute.WORKFLOW
    assert decision.reasons == ("workflow_mode=always",)


def test_off_modu_karmasik_gorevi_eski_hizli_yolda_tutar():
    classification = TaskClassification(primary=TaskKind.FEATURE, confidence=1.0)

    decision = choose_execution_route(
        "özellik ekle", classification, _policy(complex_task=True), ExecutionMode.OFF
    )

    assert decision.route is ExecutionRoute.FAST
    assert decision.reasons == ("workflow_mode=off",)


def test_arastirma_arac_kullanacaksa_yukseltilebilir_yolu_secer():
    classification = TaskClassification(primary=TaskKind.EXPLORE, confidence=1.0)

    decision = choose_execution_route(
        "projeyi incele", classification, _policy(tools=True), ExecutionMode.AUTO
    )

    assert decision.route is ExecutionRoute.FAST_PROMOTABLE
    assert decision.reasons == ("araç kullanan görev çalışma sırasında büyüyebilir",)
