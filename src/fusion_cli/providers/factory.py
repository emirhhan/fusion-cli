"""Yapılandırmadan sağlayıcı kurma — kompozisyonun toplandığı tek yer.

    ModelSpec ──▶ her model kimliği için LiteLlmProvider
                 └─▶ HedgedProvider    (hepsini yarıştır)
                     └─▶ EventingProvider  (yaşam döngüsünü olaya çevir)

Üst katmanlar bu fonksiyonu çağırır ve elinde tek bir `LlmProvider` olur; içindeki
katmanları bilmez. Yeni bir davranış eklemek (ör. önbellek, hız sınırı) buraya bir
sarmalayıcı daha eklemekten ibarettir.
"""

from __future__ import annotations

from ..core.events import Channel, EventPublisher
from ..core.protocols import Clock, LlmProvider
from ..core.types import ModelSpec
from .eventing import EventingProvider
from .hedged import HedgedProvider
from .litellm_provider import LiteLlmProvider, configure_litellm


def build_provider(
    spec: ModelSpec,
    *,
    publisher: EventPublisher,
    channel: Channel = Channel.MAIN,
    clock: Clock | None = None,
) -> LlmProvider:
    """`ModelSpec`'ten kullanıma hazır, dayanıklı ve olay yayınlayan sağlayıcı üret."""
    configure_litellm()
    inner = HedgedProvider(
        [LiteLlmProvider(model, role=spec.name, clock=clock) for model in spec.models],
        role=spec.name,
    )
    return EventingProvider(inner, publisher=publisher, role=spec.name, channel=channel)
