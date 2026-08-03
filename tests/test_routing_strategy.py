"""Routing stratejileri — yedek zincirini sıralama (saf, deterministik)."""

from __future__ import annotations

import random

from fusion_cli.core.health import HealthRegistry
from fusion_cli.core.routing_strategy import RoutingStrategy, order_models

_MODELS = ("nvidia_nim/a", "openrouter/b:free", "nvidia_nim/c", "openrouter/d:free")


class _Clock:
    def monotonic(self):
        return 0.0

    def now(self):
        return 0.0


def test_priority_sirayi_korur():
    assert order_models(_MODELS, strategy=RoutingStrategy.PRIORITY) == _MODELS


def test_tek_model_degismez():
    assert order_models(("x",), strategy=RoutingStrategy.RANDOM) == ("x",)


def test_free_first_ucretsizleri_one_alir():
    sirali = order_models(_MODELS, strategy=RoutingStrategy.FREE_FIRST)
    assert ":free" in sirali[0] and ":free" in sirali[1]
    # Grup içi sıra korunur (kararlı).
    assert sirali == ("openrouter/b:free", "openrouter/d:free", "nvidia_nim/a", "nvidia_nim/c")


def test_round_robin_kaydirir():
    assert order_models(_MODELS, strategy=RoutingStrategy.ROUND_ROBIN, rotation=1)[0] == _MODELS[1]
    assert order_models(_MODELS, strategy=RoutingStrategy.ROUND_ROBIN, rotation=2)[0] == _MODELS[2]


def test_random_tum_modelleri_korur():
    sirali = order_models(_MODELS, strategy=RoutingStrategy.RANDOM, rng=random.Random(1))
    assert set(sirali) == set(_MODELS)
    assert len(sirali) == len(_MODELS)


def test_headroom_yuksek_skoru_one_alir():
    reg = HealthRegistry(failure_threshold=1, cooldown_s=60.0, alpha=0.5, clock=_Clock())
    reg.for_model("nvidia_nim/a").record(ok=False)  # skoru düşür
    reg.for_model("nvidia_nim/c").record(ok=True)  # yüksek kalır
    sirali = order_models(_MODELS, strategy=RoutingStrategy.HEADROOM, health=reg)
    # En yüksek skorlu 'c' (ve dokunulmamış :free'ler skor=1) önde, düşük 'a' arkada.
    assert sirali[-1] == "nvidia_nim/a"


def test_least_used_az_kullanilani_one_alir():
    reg = HealthRegistry(failure_threshold=1, cooldown_s=60.0, alpha=0.5, clock=_Clock())
    for _ in range(3):
        reg.for_model("nvidia_nim/a").record(ok=True)  # çok kullanıldı
    sirali = order_models(_MODELS, strategy=RoutingStrategy.LEAST_USED, health=reg)
    assert sirali[-1] == "nvidia_nim/a"  # en çok kullanılan sona


def test_saglik_yoksa_priority_gibi():
    # HEADROOM sağlık verisi olmadan sırayı bozmaz.
    assert order_models(_MODELS, strategy=RoutingStrategy.HEADROOM, health=None) == _MODELS


def test_config_yukler():
    from fusion_cli.config.loader import load_config

    assert load_config().runtime.routing_strategy is RoutingStrategy.PRIORITY
