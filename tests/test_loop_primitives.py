"""Döngü primitifleri: her görev aynı ağır akıştan geçmemeli.

Taksonomi çalışmasının bulgusu: bütün ajan mimarileri beş primitifin (ReAct,
üret-test-onar, planla-yürüt, çok-denemeli-tekrar, ağaç arama) bileşimidir.
mini-swe-agent'ın ölçümü ise ters yönden aynı şeyi söylüyor: basit görevde sade
yol, ağır scaffold kadar iyi — hatta daha iyi, çünkü modelin önüne geçmiyor.

Seçim GÖREV TÜRÜNDEN yapılır ve açıkça yapılandırılabilir: iskele modelin yolunu
kapatmamalı.
"""

from __future__ import annotations

from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.loops import LoopPrimitive, primitives_for


def test_basit_sohbet_tek_react_turu_alir():
    assert primitives_for(TaskKind.GENERAL) == (LoopPrimitive.REACT,)


def test_hata_duzeltme_uret_test_onar_kullanir():
    secim = primitives_for(TaskKind.BUGFIX)

    assert LoopPrimitive.GENERATE_TEST_REPAIR in secim
    assert LoopPrimitive.PLAN_EXECUTE in secim


def test_buyuk_ozellik_planla_yurut_ile_calisir():
    assert LoopPrimitive.PLAN_EXECUTE in primitives_for(TaskKind.FEATURE)


def test_kesif_agir_iskele_almaz():
    """Keşif turu planlama maliyeti ödememeli."""
    secim = primitives_for(TaskKind.EXPLORE)

    assert LoopPrimitive.PLAN_EXECUTE not in secim


def test_secim_daima_react_icerir():
    """Her akışın tabanı gözlem-eylem döngüsüdür; primitifler onun üstüne biner."""
    for kind in TaskKind:
        assert LoopPrimitive.REACT in primitives_for(kind)
