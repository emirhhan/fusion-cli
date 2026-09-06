"""Döngü primitifi seçimi gerçek rota kararına bağlı.

Denetlendi (6 Eylül): `engines/agent/loops.py` yazıldı ve test edildi ama hiçbir
yerden çağrılmıyordu — rota kararı primitif seçimini hiç sormuyordu. Modülün var
olması, Fusion'ın onu kullanabildiği anlamına gelmez.

Kural: planlama hakkı olmayan bir görev türü, karmaşık sayılsa bile ağır yola
sokulmaz — mini-swe-agent'ın ölçümü, sade yolun basit işte daha iyi olduğunu
söylüyor.
"""

from __future__ import annotations

from fusion_cli.core.execution_mode import ExecutionMode
from fusion_cli.engines.agent.classify import TaskClassification, TaskKind
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.execution_route import ExecutionRoute, choose_execution_route


def _karar(kind: TaskKind, *, complex_task: bool = True):
    return choose_execution_route(
        "görev",
        TaskClassification(primary=kind, confidence=1.0),
        ExecutionPolicy(is_web=False, complex_task=complex_task),
        ExecutionMode.AUTO,
    )


def test_kesif_karmasik_sayilsa_bile_plana_sokulmaz():
    karar = _karar(TaskKind.EXPLORE)

    assert karar.route is not ExecutionRoute.WORKFLOW
    assert any("primitif" in gerekce for gerekce in karar.reasons)


def test_dokumantasyon_da_sade_yolda_kalir():
    assert _karar(TaskKind.DOCS).route is not ExecutionRoute.WORKFLOW


def test_ozellik_gorevi_planli_yolda_kalir():
    assert _karar(TaskKind.FEATURE).route is ExecutionRoute.WORKFLOW


def test_hata_duzeltme_planli_yolda_kalir():
    assert _karar(TaskKind.BUGFIX).route is ExecutionRoute.WORKFLOW
