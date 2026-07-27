"""Yapılandırmadan sağlayıcı kurma — kompozisyonun toplandığı tek yer.

    ModelSpec ──▶ her model kimliği için LiteLlmProvider
                 └─▶ RetryingProvider   (geçici arızada AYNI modeli tekrar dene)
                     └─▶ FallbackProvider   (tükenirse SIRADAKİ modele geç)
                         └─▶ EventingProvider  (yaşam döngüsünü olaya çevir)

Sıra anlamlıdır ve içten dışa okunur: yeniden deneme her modelin KENDİ içinde olur,
zincire geçiş ancak o model tamamen tükendiğinde. Katmanlar ters sırada olsaydı
"her modele iki deneme" kuralı zincirin tamamına iki deneme anlamına gelirdi.

Üst katmanlar bu fonksiyonu çağırır ve elinde tek bir `LlmProvider` olur; içindeki
katmanları bilmez. Yeni bir davranış eklemek (ör. önbellek, hız sınırı) buraya bir
sarmalayıcı daha eklemekten ibarettir.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..core.events import Channel, EventPublisher
from ..core.protocols import Clock, LlmProvider, Sleeper
from ..core.types import ModelSpec
from .chain import FallbackProvider
from .eventing import EventingProvider
from .litellm_provider import LiteLlmProvider, configure_litellm
from .retrying import wrap as wrap_with_retry


def build_provider(
    spec: ModelSpec,
    *,
    publisher: EventPublisher | None,
    retry_delays_s: Sequence[float],
    channel: Channel = Channel.MAIN,
    clock: Clock | None = None,
    sleeper: Sleeper | None = None,
    background: bool = False,
) -> LlmProvider:
    """`ModelSpec`'ten kullanıma hazır ve dayanıklı bir sağlayıcı üret.

    `background=True` verilirse çağrı kullanıcıya ilerleme satırı olarak GÖSTERİLMEZ
    ama olayları yine de yayınlanır. Görünürlük ile muhasebe ayrı şeylerdir: hakem,
    sentez, öz-denetim ve ders çıkarımı arka planda çalışır ama harcadıkları token
    sayıma girmelidir.

    `publisher=None` yalnızca olay veriyolu hiç kurulmamışsa (ör. birim testi)
    kullanılır; bu durumda çağrı tamamen sessizdir ve muhasebeye de girmez.

    `retry_delays_s` zorunludur ve varsayılanı YOKTUR: bir arızadan sonra ne kadar
    beklendiği ürün kararıdır, kütüphane varsayılanı değil. Değer `defaults.yaml`'dan
    (`runtime.retry_delays_s`) gelir. Boş liste "hiç yeniden deneme" demektir.
    """
    configure_litellm()
    models = [LiteLlmProvider(model, role=spec.name, clock=clock) for model in spec.models]
    inner = FallbackProvider(
        wrap_with_retry(models, delays_s=retry_delays_s, sleeper=sleeper),
        role=spec.name,
    )
    if publisher is None:
        return inner
    return EventingProvider(
        inner, publisher=publisher, role=spec.name, channel=channel, background=background
    )
