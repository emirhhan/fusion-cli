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
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

from ..core.types import ModelSpec
from .models import Config

#: Ortam değişkeni adları. Tek yerde tutulur; `.env` şablonu ve kurulum sihirbazı
#: da buradan okur, iki listenin ayrışması mümkün olmasın.
OPENROUTER_ENV = "OPENROUTER_API_KEY"
NIM_ENV = "NVIDIA_NIM_API_KEY"
#: Resmî API sağlayıcılarının anahtar ortam değişkenleri. Bunlar ürünün ücretsiz
#: taban çizgisine (OpenRouter + NIM) dahil DEĞİLDİR; kullanıcı isterse resmî API'yi
#: kendi anahtarıyla ekler. LiteLLM bu önekleri doğrudan çalıştırır.
OPENAI_ENV = "OPENAI_API_KEY"
GEMINI_ENV = "GEMINI_API_KEY"
ANTHROPIC_ENV = "ANTHROPIC_API_KEY"

#: Model kimliği önekleri.
OPENROUTER_PREFIX = "openrouter/"
NIM_PREFIX = "nvidia_nim/"
OPENAI_PREFIX = "openai/"
GEMINI_PREFIX = "gemini/"
ANTHROPIC_PREFIX = "anthropic/"


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


#: Şifreli credential deposunun ana anahtarı (Fernet). Kullanıcı ortama koyar;
#: koda/dosyaya/git'e ASLA girmez. Yoksa depo devre dışı kalır ve kullanıcı bilgilendirilir.
FUSION_SECRET_ENV = "FUSION_SECRET_KEY"


def secret_key() -> str | None:
    """Credential deposunun ana anahtarını ortamdan oku. Yoksa/boşsa None."""
    value = os.environ.get(FUSION_SECRET_ENV, "").strip()
    return value or None


def environ_snapshot() -> dict[str, str]:
    """Ortam değişkenlerinin anlık kopyası. Ortam erişimi config katmanındadır
    (RULES.md): üst katmanlar `os.environ`'a doğrudan dokunmaz, bunu çağırır."""
    return dict(os.environ)


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


class ProviderPreference(Enum):
    """Kullanıcının hangi sağlayıcıya kilitlendiği.

    Neden gerekli: bir sağlayıcının tükenmesi ötekini de tüketiyordu. NIM kredisi
    bitince her çağrı yedeğe düştü, hepsi OpenRouter'a gitti ve günlük 50 istek
    birkaç dakikada bitti — kullanıcı iki kotayı birden kaybetti ve sebebini
    göremedi. Tercih belirlenince ötekinin kotasına HİÇ dokunulmaz.

    `AUTO` varsayılandır ve mevcut davranışı korur: zincir iki sağlayıcıya yayılır,
    biri yavaşsa/hata verirse öteki devreye girer. Dayanıklılık ile kota
    öngörülebilirliği arasındaki takas kullanıcının kararıdır.
    """

    AUTO = "auto"
    NVIDIA = "nvidia"
    OPENROUTER = "openrouter"

    @property
    def prefix(self) -> str:
        """Bu tercihin izin verdiği model öneki. AUTO'da anlamsızdır."""
        return NIM_PREFIX if self is ProviderPreference.NVIDIA else OPENROUTER_PREFIX

    @property
    def excluded_prefix(self) -> str:
        """Bu tercihte zincirden çıkarılacak önek."""
        return OPENROUTER_PREFIX if self is ProviderPreference.NVIDIA else NIM_PREFIX


def apply_preference(config: Config, preference: ProviderPreference) -> Config:
    """Zincirleri tek bir sağlayıcıya indir. `AUTO` ise yapılandırma değişmez."""
    if preference is ProviderPreference.AUTO:
        return config
    return _map_specs(config, lambda spec: _only(spec, preference.excluded_prefix))


def _only(spec: ModelSpec, excluded: str) -> ModelSpec:
    """Zincirden bir sağlayıcıyı çıkar.

    Zincirin tamamı düşerse spec DEĞİŞMEZ: modelsiz rol turu çökertir ve "hiç model
    yok" hatası, kullanıcının anlayabileceği bir şey değildir. Tanınmayan önekler
    (ollama, vLLM) hiç elenmez — yönettiğimiz iki sağlayıcıdan biri değildirler.
    """
    kalan = tuple(model for model in spec.models if not model.startswith(excluded))
    if not kalan or kalan == spec.models:
        return spec
    return replace(spec, model=kalan[0], fallback=kalan[1:])


def _map_specs(config: Config, donustur: Callable[[ModelSpec], ModelSpec]) -> Config:
    """Tüm rollerin spec'lerine aynı dönüşümü uygula (kademeler dahil)."""
    return replace(
        config,
        agent=donustur(config.agent),
        judge=donustur(config.judge),
        candidates=tuple(donustur(spec) for spec in config.candidates),
        vision=donustur(config.vision) if config.vision else None,
        tiers=tuple(
            replace(
                tier,
                agent=donustur(tier.agent),
                judge=donustur(tier.judge),
                candidates=tuple(donustur(spec) for spec in tier.candidates),
            )
            for tier in config.tiers
        ),
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
    return _map_specs(config, lambda spec: prune_spec(spec, keys))
