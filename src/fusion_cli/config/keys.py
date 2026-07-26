"""Hangi sağlayıcı anahtarlarının kurulu olduğu — tek doğruluk kaynağı.

Ürün iki sağlayıcıyla çalışır ve BİRİ yeterlidir:

- **OpenRouter** zorunludur. Ücretsiz katmanı anahtarla açılır ve merdivenin her
  kademesinde en az bir OpenRouter modeli vardır; bu yüzden ürünün taban çizgisidir.
- **NVIDIA NIM** opsiyoneldir. Varsa ayrı bir ücretsiz kotadan çalışır ve bazı
  roller ona kayar; yoksa hiçbir kademe boşta kalmaz.

Model zincirleri buna göre BUDANIR. Eskiden NIM anahtarı olmayan kullanıcıda her
tur önce başarısız bir `nvidia_nim/` çağrısı yapılıyor, sonra yedeğe düşülüyordu:
çalışıyordu ama her rolde bir boşa çağrı ve gereksiz gecikme demekti.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from ..core.types import ModelSpec
from .models import Config

#: Ortam değişkeni adları. Tek yerde tutulur; `.env` şablonu ve kurulum sihirbazı
#: da buradan okur, iki listenin ayrışması mümkün olmasın.
OPENROUTER_ENV = "OPENROUTER_API_KEY"
NIM_ENV = "NVIDIA_NIM_API_KEY"

#: Model kimliği önekleri.
OPENROUTER_PREFIX = "openrouter/"
NIM_PREFIX = "nvidia_nim/"


@dataclass(frozen=True, slots=True)
class ProviderKeys:
    """Kurulu olan sağlayıcılar."""

    openrouter: bool
    nim: bool

    @property
    def any_configured(self) -> bool:
        return self.openrouter or self.nim

    def supports(self, model_id: str) -> bool:
        """Bu model kimliği kurulu bir sağlayıcıya mı ait?

        Tanınmayan önekler (ollama, openai, yerel uçlar) True döner: kullanıcı
        onları bilerek yazmıştır ve anahtar gereksinimlerini biz bilemeyiz.
        Budama yalnızca YÖNETTİĞİMİZ iki sağlayıcı için yapılır.
        """
        if model_id.startswith(NIM_PREFIX):
            return self.nim
        if model_id.startswith(OPENROUTER_PREFIX):
            return self.openrouter
        return True


def detect(environ: dict[str, str] | None = None) -> ProviderKeys:
    """Ortamdan kurulu sağlayıcıları oku.

    Boş string kurulu SAYILMAZ: `.env` şablonu anahtarları `OPENROUTER_API_KEY=`
    olarak bırakır ve doldurulmamış bir satır "kurulu" sayılsaydı ürün, anahtarı
    olmayan kullanıcıda kurulumu tamamlanmış gibi davranırdı.
    """
    source = environ if environ is not None else dict(os.environ)
    return ProviderKeys(
        openrouter=bool(source.get(OPENROUTER_ENV, "").strip()),
        nim=bool(source.get(NIM_ENV, "").strip()),
    )


def prune_spec(spec: ModelSpec, keys: ProviderKeys) -> ModelSpec:
    """Bir rolün model zincirinden anahtarı olmayan sağlayıcıları çıkar.

    Zincirin TAMAMI düşerse spec olduğu gibi bırakılır: modelsiz bir rol turu
    çökertir ve "hiç model yok" hatası, "anahtarın yok" hatasından çok daha
    anlaşılmazdır. Bu durumda çağrı yine başarısız olur ama sebebi sağlayıcıdan
    gelen açık bir kimlik doğrulama hatası olur.
    """
    kalan = tuple(model for model in spec.models if keys.supports(model))
    if not kalan or kalan == spec.models:
        return spec
    return replace(spec, model=kalan[0], fallback=kalan[1:])


def prune_config(config: Config, keys: ProviderKeys) -> Config:
    """Tüm rollerin zincirlerini kurulu sağlayıcılara göre buda.

    Hiç anahtar yoksa yapılandırma DEĞİŞTİRİLMEZ: budama kurulum eksikliğini
    gizlerdi ve kullanıcı "model yok" hatasıyla karşılaşırdı; oysa asıl sorun
    anahtarın hiç girilmemiş olmasıdır ve onu kurulum akışı söylemelidir.
    """
    if not keys.any_configured:
        return config
    if keys.openrouter and keys.nim:
        return config
    return replace(
        config,
        agent=prune_spec(config.agent, keys),
        judge=prune_spec(config.judge, keys),
        candidates=tuple(prune_spec(spec, keys) for spec in config.candidates),
        vision=prune_spec(config.vision, keys) if config.vision else None,
        tiers=tuple(
            replace(
                tier,
                agent=prune_spec(tier.agent, keys),
                judge=prune_spec(tier.judge, keys),
                candidates=tuple(prune_spec(spec, keys) for spec in tier.candidates),
            )
            for tier in config.tiers
        ),
    )
