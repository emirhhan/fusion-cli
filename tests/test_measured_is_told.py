"""Değişmez: adımın ÖLÇÜLDÜĞÜ her hedef, adıma SÖYLENMİŞ olmalı.

Bugüne kadarki en pahalı koşu ölümü bu değişmezin ihlaliydi (7 Eylül canlı Godot
koşusu, `game-manager-eksiklerini-tamamla`): kontrol hedefi plan yazılırken, yani
depo keşfedilmeden üretiliyor; adım istemi ise yalnız başarı koşulunun metnini
taşıyordu. Model işi yaptı, kapı başka bir yola baktı, üç deneme de düştü.

Tek tek doğru yazılmış iki parça — "hedefi plan üretir" ve "kapı hedefi ölçer" —
arasındaki boşluk kilitlenmeyi doğurur. Bu dosya boşluğu makinece arar: hedef
üretmenin her biçimi, istemde görünmek ZORUNDADIR.
"""

from __future__ import annotations

from dataclasses import replace
from itertools import product

import pytest

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    VerificationCheck,
    VerificationCheckKind,
    validate_plan,
)
from fusion_cli.engines.agent.plan_context import step_prompt
from tests.test_plan_repair import _step

_YOL = "scripts/game_manager.gd"
_KOMUT = "godot --headless --path . --quit"

_ETKI_BICIMLERI = (
    (),
    ("workspace_mutation",),
    (f"file:{_YOL}",),
    (f"file:{_YOL}", "workspace_mutation"),
)


def _kontrol(kind, kosul):
    hedef = _KOMUT if kind is VerificationCheckKind.COMMAND else _YOL
    beklenen = "signal health_changed" if kind is VerificationCheckKind.FILE_CONTAINS else ""
    return VerificationCheck(kosul, kind, hedef, beklenen)


_KONTROL_BICIMLERI = (
    None,
    VerificationCheckKind.FILE_EXISTS,
    VerificationCheckKind.FILE_CONTAINS,
    VerificationCheckKind.COMMAND,
)


def _adim(effects, kind):
    temel = _step("adim", expected_effects=effects)
    if kind is None:
        return temel
    return replace(temel, verification_checks=(_kontrol(kind, temel.success_criteria[0]),))


def _olculen_hedefler(step):
    """Adımı DÜŞÜREBİLECEK her somut hedef."""
    hedefler = {
        effect.removeprefix("file:").strip()
        for effect in step.expected_effects
        if effect.startswith("file:")
    }
    hedefler.update(check.target for check in step.verification_checks)
    return hedefler


@pytest.mark.parametrize(("effects", "kind"), tuple(product(_ETKI_BICIMLERI, _KONTROL_BICIMLERI)))
def test_olculen_her_hedef_adim_istemine_yazilir(effects, kind):
    adim = _adim(effects, kind)
    if not validate_plan(ExecutionPlan(plan_id="p", task="iş", steps=(adim,))).ok:
        pytest.skip("plan zaten geçersiz; bu biçim adıma hiç ulaşmaz")

    istem = step_prompt("iş", adim, {})

    for hedef in _olculen_hedefler(adim):
        assert hedef in istem
