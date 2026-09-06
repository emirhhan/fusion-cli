"""Yükseltme gerçek model seçimine ve adım denemesine bağlı.

Strateji tek başına işe yaramaz: takılan adım ikinci denemesinde gerçekten bir üst
modele geçmeli, `/development` gibi tek-model akışları ise bozulmamalı.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.config.model_select import escalated_spec
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy

SPEC = ModelSpec(name="agent", model="ucuz/a", fallback=("orta/b", "guclu/c"))


def test_ilk_denemede_spec_degismez():
    assert escalated_spec(SPEC, 0) == SPEC


def test_ikinci_denemede_yedek_one_gecer():
    yeni = escalated_spec(SPEC, 1)

    assert yeni.model == "orta/b"
    assert yeni.fallback == ("guclu/c", "ucuz/a")


def test_ucuncu_denemede_en_guclu_one_gecer():
    assert escalated_spec(SPEC, 2).model == "guclu/c"


def test_yukseltme_zinciri_asmaz():
    assert escalated_spec(SPEC, 9).model == "guclu/c"


def test_strict_spec_yukseltilmez():
    """Kullanıcı tek model seçtiyse yükseltme onun kararını ezemez."""
    strict = ModelSpec(name="agent", model="ucuz/a", tags=("strict",), fallback=("orta/b",))

    assert escalated_spec(strict, 2) == strict


def test_yedegi_olmayan_spec_degismez():
    tek = ModelSpec(name="agent", model="ucuz/a")

    assert escalated_spec(tek, 3) == tek


def test_adim_denemesi_politikaya_gecer(tmp_path):
    from fusion_cli.engines.agent.plan_context import step_deps
    from tests.test_plan_repair import _deps, _step

    adim = replace(_step("yaz"), attempts=2)

    dar = step_deps(_deps(tmp_path), adim, remaining=4, observe=False)

    assert isinstance(dar.execution, ExecutionPolicy)
    assert dar.execution.escalation == 2
