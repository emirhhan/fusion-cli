"""Kök rota yalnız açık bir seçimden gelir: görev metni rotayı belirlemez.

Ölçülen hata (B2): kelime sınıflandırıcısı "Tamam yaz" gibi kısa bir onayı
oturumun ilk görevinin türüyle birleştirip plan motoruna sokuyordu. Rota artık
iki değerlidir ve yalnız `workflow_mode` ile kullanıcının `/plan-yurut` seçimine
bakar.
"""

from __future__ import annotations

from fusion_cli.core.execution_mode import ExecutionMode
from fusion_cli.engines.agent.execution_route import ExecutionRoute, choose_execution_route


def test_off_modu_tek_donguyu_secer():
    decision = choose_execution_route(ExecutionMode.OFF, requested=False)

    assert decision.route is ExecutionRoute.FAST


def test_always_modu_plan_motorunu_secer():
    decision = choose_execution_route(ExecutionMode.ALWAYS, requested=False)

    assert decision.route is ExecutionRoute.WORKFLOW
    assert decision.reasons == ("workflow_mode=always",)


def test_kullanici_secimi_off_modunda_da_plan_motorunu_acar():
    decision = choose_execution_route(ExecutionMode.OFF, requested=True)

    assert decision.route is ExecutionRoute.WORKFLOW
    assert decision.reasons == ("kullanıcı plan yürütmeyi seçti",)


def test_rota_yalniz_iki_degerlidir():
    assert {route.value for route in ExecutionRoute} == {"fast", "workflow"}
