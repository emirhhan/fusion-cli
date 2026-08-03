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
from ..core.health import HealthRegistry
from ..core.protocols import Clock, LlmProvider, Sleeper
from ..core.types import ModelSpec
from .chain import FallbackProvider
from .circuit import CircuitBreakingProvider
from .eventing import EventingProvider
from .key_pool import KeyPoolRegistry
from .key_rotation import KeyRotatingProvider
from .litellm_provider import LiteLlmProvider, configure_litellm
from .registry import provider_for_model
from .retrying import wrap as wrap_with_retry
from .web_registry import WebSessionRegistry


def build_provider(
    spec: ModelSpec,
    *,
    publisher: EventPublisher | None,
    retry_delays_s: Sequence[float],
    channel: Channel = Channel.MAIN,
    clock: Clock | None = None,
    sleeper: Sleeper | None = None,
    background: bool = False,
    health: HealthRegistry | None = None,
    key_pools: KeyPoolRegistry | None = None,
    web_sessions: WebSessionRegistry | None = None,
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

    def _leaf(model: str) -> LlmProvider:
        # Model kullanıcının yetkili bir web (oturum tabanlı) ucuyla eşleşiyorsa API
        # yerine web transport'u kullanılır. Diğer katmanlar (retry/fallback/circuit)
        # bunu da sarar; web ucu da bir `LlmProvider`'dır.
        if web_sessions is not None:
            web = web_sessions.build(model, clock=clock)
            if web is not None:
                return web
        # Sağlayıcının anahtar havuzunda BİRDEN ÇOK anahtar varsa istekler bunlar
        # arasında döndürülür (biri hız sınırına takılınca öteki devreye girer).
        if key_pools is not None:
            definition = provider_for_model(model)
            if definition is not None and definition.auth_env is not None:
                pool = key_pools.for_env(definition.auth_env)
                if pool.size > 1:
                    return KeyRotatingProvider(
                        lambda key: LiteLlmProvider(
                            model, role=spec.name, clock=clock, api_key=key
                        ),
                        pool,
                        label=model,
                    )
        return LiteLlmProvider(model, role=spec.name, clock=clock)

    models = [_leaf(model) for model in spec.models]
    retrying = wrap_with_retry(models, delays_s=retry_delays_s, sleeper=sleeper)
    # `health` verilirse her modelin yeniden-deneme katmanı circuit breaker ile sarılır:
    # devresi açık model çağrılmadan atlanır ve zincir sıradakine geçer. Verilmezse
    # (varsayılan) mevcut davranış birebir korunur.
    resilient: Sequence[LlmProvider]
    if health is not None:
        resilient = [
            CircuitBreakingProvider(
                provider, health=health.for_model(provider.label), role=spec.name
            )
            for provider in retrying
        ]
    else:
        resilient = retrying
    inner = FallbackProvider(resilient, role=spec.name)
    if publisher is None:
        return inner
    return EventingProvider(
        inner, publisher=publisher, role=spec.name, channel=channel, background=background
    )
