"""Takılan adım bir üst modele yükseltilir.

Sektörde ölçülen desen: trafiğin büyük kısmı ucuz modelde çalışır, yalnız takılan
azınlık güçlüye yükseltilir. Fusion'da yedek zincir vardı ama yükseltme yalnız
sağlayıcı ARIZASINDA devreye giriyordu; modelin işi beceremediği durumda aynı model
tekrar tekrar deneniyordu (ölçüldü: 5 Eylül starter koşusunda başarısız görevlerde
0 yeniden deneme, aynı modelle duvara çarpma).

Yükseltme KANITA bağlıdır: aynı adım ikinci kez düştüğünde bir üst modele geçilir,
görev zorluğu tahmin edilmez.
"""

from __future__ import annotations

from fusion_cli.core.routing_strategy import RoutingStrategy, order_models

ZINCIR = ("ucuz/model-a", "orta/model-b", "guclu/model-c")


def test_ilk_denemede_ucuz_model_onde():
    sira = order_models(ZINCIR, strategy=RoutingStrategy.ESCALATE, escalation=0)

    assert sira[0] == "ucuz/model-a"


def test_ikinci_denemede_bir_ust_model_one_gecer():
    sira = order_models(ZINCIR, strategy=RoutingStrategy.ESCALATE, escalation=1)

    assert sira[0] == "orta/model-b"


def test_yukseltme_zinciri_asmaz():
    sira = order_models(ZINCIR, strategy=RoutingStrategy.ESCALATE, escalation=9)

    assert sira[0] == "guclu/model-c"


def test_hicbir_model_dusurulmez():
    sira = order_models(ZINCIR, strategy=RoutingStrategy.ESCALATE, escalation=1)

    assert set(sira) == set(ZINCIR)
    assert len(sira) == len(ZINCIR)


def test_atlanan_model_sonda_yedek_kalir():
    """Yükseltilen tur, ucuz modeli tamamen atmaz: yedek olarak sonda kalır."""
    sira = order_models(ZINCIR, strategy=RoutingStrategy.ESCALATE, escalation=1)

    assert sira[-1] == "ucuz/model-a"
