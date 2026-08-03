"""Routing stratejileri — bir modelin yedek zincirini hangi SIRAYLA deneyeceğimiz.

OmniRoute'un "combo" stratejilerinin sade ama gerçek karşılığı. Varsayılan `PRIORITY`
mevcut ölçülmüş sırayı KORUR (RULES: ölçülmüş karar bozulmaz); diğer stratejiler
kullanıcı açıkça seçerse devreye girer. Saf ve enjekte-edilebilir: rastgelelik ve
rotasyon dışarıdan verilir, böylece deterministik test edilir.
"""

from __future__ import annotations

import random as _random
from collections.abc import Sequence
from enum import Enum

from .health import HealthRegistry


class RoutingStrategy(Enum):
    """Yedek zincirinin deneme sırasını belirleyen strateji."""

    #: Yapılandırmadaki sıra (varsayılan; ölçülmüş kararı korur).
    PRIORITY = "priority"
    #: Ücretsiz (`:free`) modeller önce.
    FREE_FIRST = "free_first"
    #: Güvenilirlik skoru en yüksek olan önce (sağlık verisi gerekir).
    HEADROOM = "headroom"
    #: En az kullanılan (en az örnekli) model önce — yükü dağıtır.
    LEAST_USED = "least_used"
    #: Her istekte bir kaydırma — sırayla dolaş.
    ROUND_ROBIN = "round_robin"
    #: Rastgele sırala.
    RANDOM = "random"


def order_models(
    models: Sequence[str],
    *,
    strategy: RoutingStrategy,
    health: HealthRegistry | None = None,
    rotation: int = 0,
    rng: _random.Random | None = None,
) -> tuple[str, ...]:
    """Modelleri stratejiye göre sırala. Girdi sırası hiçbir modeli DÜŞÜRMEZ."""
    items = list(models)
    if len(items) <= 1 or strategy is RoutingStrategy.PRIORITY:
        return tuple(items)
    if strategy is RoutingStrategy.FREE_FIRST:
        # Kararlı: önce ':free' içerenler, sonra ötekiler; her grup içinde sıra korunur.
        return tuple(sorted(items, key=lambda m: 0 if ":free" in m else 1))
    if strategy is RoutingStrategy.ROUND_ROBIN:
        shift = rotation % len(items)
        return tuple(items[shift:] + items[:shift])
    if strategy is RoutingStrategy.RANDOM:
        generator = rng or _random.Random()
        return tuple(generator.sample(items, len(items)))
    if health is None:
        # Sağlık gerektiren stratejiler veri yoksa PRIORITY gibi davranır.
        return tuple(items)
    if strategy is RoutingStrategy.HEADROOM:
        return tuple(sorted(items, key=lambda m: -health.for_model(m).score))
    return tuple(sorted(items, key=lambda m: health.for_model(m).samples))  # LEAST_USED
