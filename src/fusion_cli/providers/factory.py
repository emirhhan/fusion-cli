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
    hedge_delay_s: float,
    channel: Channel = Channel.MAIN,
    clock: Clock | None = None,
    background: bool = False,
) -> LlmProvider:
    """`ModelSpec`'ten kullanıma hazır ve dayanıklı bir sağlayıcı üret.

    `background=True` verilirse çağrı kullanıcıya ilerleme satırı olarak GÖSTERİLMEZ
    ama olayları yine de yayınlanır. Görünürlük ile muhasebe ayrı şeylerdir: hakem,
    sentez, öz-denetim ve ders çıkarımı arka planda çalışır ama harcadıkları token
    sayıma girmelidir.

    `publisher=None` yalnızca olay veriyolu hiç kurulmamışsa (ör. birim testi)
    kullanılır; bu durumda çağrı tamamen sessizdir ve muhasebeye de girmez.

    `hedge_delay_s` zorunludur ve varsayılanı YOKTUR: yedeklerin ne zaman devreye
    gireceği ürün kararıdır, kütüphane varsayılanı değil. Değer `defaults.yaml`'dan
    (`runtime.hedge_delay_s`) gelir ve GENEL varsayılandır; rolün kendi
    `spec.hedge_delay_s` değeri varsa o kazanır — pencere birincil modelin hızına
    aittir, motorun geneline değil (bkz. `ModelSpec.hedge_delay_s`).
    """
    configure_litellm()
    inner = HedgedProvider(
        [LiteLlmProvider(model, role=spec.name, clock=clock) for model in spec.models],
        role=spec.name,
        hedge_delay_s=spec.hedge_delay_s if spec.hedge_delay_s is not None else hedge_delay_s,
    )
    if publisher is None:
        return inner
    return EventingProvider(
        inner, publisher=publisher, role=spec.name, channel=channel, background=background
    )
