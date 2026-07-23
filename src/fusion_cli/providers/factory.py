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
    publisher: EventPublisher | None,
    channel: Channel = Channel.MAIN,
    clock: Clock | None = None,
) -> LlmProvider:
    """`ModelSpec`'ten kullanıma hazır ve dayanıklı bir sağlayıcı üret.

    `publisher=None` verilirse olay yayını katmanı hiç eklenmez: çağrı SESSİZ olur.
    Hakem ve sentez böyle çağrılır — arka plan işleri kullanıcının okuduğu cevabın
    ortasına ilerleme satırı düşürmemelidir.
    """
    configure_litellm()
    inner = HedgedProvider(
        [LiteLlmProvider(model, role=spec.name, clock=clock) for model in spec.models],
        role=spec.name,
    )
    if publisher is None:
        return inner
    return EventingProvider(inner, publisher=publisher, role=spec.name, channel=channel)
