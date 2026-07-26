"""Katmanlar arasında dolaşan değer nesneleri.

Hepsi `frozen`: mutasyon yerine `dataclasses.replace` kullanılır. Katmanlar arası
veri taşıması dict ile değil bu tiplerle yapılır (RULES.md "Katman Sınırları").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from .errors import ConfigError


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Bir çağrının token tüketimi ve tahmini maliyeti.

    Maliyet SAĞLAYICI SINIRINDA hesaplanır: fiyat model kimliğine bağlıdır ve
    yalnızca orada bilinir. Üst katmanlar yalnızca toplama yapar — eski projede
    maliyet takibi bazı çağrı yollarını atlıyordu, çünkü toplama birden çok yerde
    yapılıyordu.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: Tahmini maliyet (USD). Ücretsiz modellerde 0.
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
        )


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Modelin yapmak istediği araç çağrısı.

    `arguments` modelin ürettiği HAM JSON metnidir; bozuk olabilir. Ayrıştırma
    araç katmanının sınırında yapılır, burada değil.
    """

    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class Message:
    """Sohbet mesajı.

    `role`: system | user | assistant | tool. Araç sonucu mesajlarında `tool_call_id`
    ve `name` doldurulur; modelin araç isteğini taşıyan assistant mesajında `tool_calls`.
    """

    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None
    #: Araç sonucu mesajlarında aracın başarılı olup olmadığı. Diğer rollerde None.
    #: Başarı metinden TAHMİN EDİLMEZ; üreten taraf bu alanı doldurur.
    ok: bool | None = None
    #: Mesaja eklenen görseller (data URI). Doluysa sağlayıcı sınırında içerik
    #: çok parçalı biçime çevrilir; boşsa mesaj düz metin kalır ve mevcut davranış
    #: birebir korunur.
    images: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Bir model rolünün tanımı: birincil model + yedek zinciri.

    `fallback` yedek model kimlikleridir. Hedged çağrıda birincile bir öncelik
    penceresi tanınır, pencere dolarsa yedekler yarışa girer ve ilk kullanılabilir
    yanıt kazanır (bkz. `providers.hedged`).
    """

    name: str
    model: str
    tags: tuple[str, ...] = ()
    fallback: tuple[str, ...] = ()
    #: Bu role özgü öncelik penceresi (saniye). None ise `runtime.hedge_delay_s`
    #: genel varsayılanı kullanılır.
    #:
    #: Neden role özgü: pencere tek bir sabitken (2.5s, nemotron-super ölçülerek
    #: belirlenmişti) yavaş modeller kendi yarışlarını yedeklerine KAYBEDİYORDU.
    #: Ölçülen sürelerle (`defaults.yaml` kademe etiketleri) doğrulandı: premium
    #: seçen kullanıcıya glm-5.2 yerine nemotron-ultra, ultra seçene nemotron-super
    #: cevap veriyordu. Pencere birincilin hızına ait bir değerdir; motorun geneline
    #: ait değil.
    hedge_delay_s: float | None = None

    def __post_init__(self) -> None:
        """Negatif pencere anlamsızdır ve sessizce 'yedekler hemen başlasın'a dönerdi.

        Doğrulama yükleyicide değil BURADA durur: spec'i yalnızca `config.loader`
        kurmuyor (kademe uygulama, `/development`, testler de kuruyor) ve değişmezin
        tek bir yolda tutulması onu ötekilerde geçersiz kılardı.
        """
        if self.hedge_delay_s is not None and self.hedge_delay_s < 0:
            raise ConfigError(
                f"'{self.name}': hedge_delay_s negatif olamaz, gelen: {self.hedge_delay_s}"
            )

    @property
    def models(self) -> tuple[str, ...]:
        """Birincil + yedekler, sıra korunarak ve tekrarlar atılarak."""
        return tuple(dict.fromkeys([self.model, *self.fallback]))


#: Sağlayıcıların kota/hız sınırını bildirirken kullandığı sözcükler.
_RATE_LIMIT_MARKERS = ("429", "ratelimit", "rate limit", "too many requests", "quota")


#: GÜNLÜK kotanın bittiğini AÇIKÇA söyleyen işaretler.
#
# Aynı 429 iki farklı şey olabilir ve tepkileri zıttır: günlük kota o gün için
# biter (beklemek işe yaramaz, koşu durmalı), dakikalık sınır ise geçicidir
# (beklenip tekrar denenmeli). OpenRouter bunu açıkça yazar; NVIDIA NIM çıplak
# 429 döner ve hangisi olduğunu SÖYLEMEZ — ölçüldü (2026-07-26): 70 saniye arayla
# üç tek istek de 429 aldı, yani NIM'in 429'u dakikalık sınır olmak zorunda değil.
# Ayırt edemediğimizde geçici varsayıp sınırlı sayıda yeniden denemek doğrudur.
_DAILY_QUOTA_MARKERS = ("per-day", "per day", "daily limit", "günlük")


def is_daily_quota_error(detail: str | None) -> bool:
    """Hata GÜNLÜK kotanın bittiğini açıkça söylüyor mu?

    False dönmek "geçici" demek değildir; "sağlayıcı söylemedi" demektir.
    """
    if not detail:
        return False
    return any(marker in detail.lower() for marker in _DAILY_QUOTA_MARKERS)


def is_rate_limit_error(detail: str | None) -> bool:
    """Hata metni ücretsiz kota/hız sınırını mı anlatıyor?

    Sağlayıcılar bunu farklı sözcüklerle bildirir. Sınıflandırma tek yerdedir:
    fusion motoru sonucu `ModelResult` üzerinden, agent motoru ise yalnızca hata
    METNİNİ taşıyarak (`AgentOutcome`) buraya gelir; iki yol ayrı yazılsaydı
    kullanıcı motoruna göre farklı yönlendirme görürdü.
    """
    if not detail:
        return False
    lowered = detail.lower()
    return any(marker in lowered for marker in _RATE_LIMIT_MARKERS)


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """Sağlayıcıya verilen çağrı isteği. Sağlayıcıdan bağımsızdır."""

    messages: tuple[Message, ...]
    temperature: float
    max_tokens: int
    timeout_s: float
    max_retries: int = 0
    #: Modele verilecek araç şemaları. Boşsa araç çağrısı istenmez.
    tools: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ModelResult:
    """Bir model çağrısının sonucu.

    Beklenen başarısızlıklar exception ile değil `ok=False` + `error` ile taşınır;
    çağıran taraf try/except yazmak zorunda kalmaz.
    """

    name: str
    model: str
    text: str
    latency_ms: int
    ok: bool
    usage: TokenUsage = field(default_factory=TokenUsage)
    error: str | None = None
    #: Modelin bu turda yapmak istediği araç çağrıları.
    tool_calls: tuple[ToolCall, ...] = ()
    #: Reasoning modellerinin düşünme metni. Nihai cevaba KARIŞTIRILMAZ; ayrı taşınır
    #: ki teşhis ve gösterim kararı üst katmanlara kalsın.
    reasoning: str = ""
    #: Çıktı bütçesi dolduğu için yanıt yarıda mı kesildi? Metin gelmiş olabilir ama
    #: TAMAMLANMAMIŞTIR: JSON'a, talimata ya da koda güvenilmemelidir.
    truncated: bool = False

    @property
    def is_rate_limited(self) -> bool:
        """Başarısızlık ücretsiz kota/hız sınırından mı kaynaklandı?"""
        return False if self.ok else is_rate_limit_error(self.error)

    @property
    def is_usable(self) -> bool:
        """Sonuç GERÇEKTEN iş görür mü?

        `ok=True` yetmez: model bazen tamamen boş cevap döndürüyor (metin yok,
        araç çağrısı yok) ve bu teknik olarak başarılı bir yanıttır. Ölçüldü —
        agent'ın "hiç dokunmadan bitirmesi" davranışının sebebi buydu: boş ama
        başarılı sonuç yedek zincirindeki yarışı kazanıyor, sonra tur bitiyordu.

        Araç çağıran cevap METİNSİZ de olsa kullanılabilirdir: iş yapar.
        """
        return self.ok and bool(self.text.strip() or self.tool_calls)


@dataclass(frozen=True, slots=True)
class TextChunk:
    """Akış sırasında gelen metin parçası."""

    text: str


@dataclass(frozen=True, slots=True)
class StreamDone:
    """Akışın sonu; toparlanmış nihai sonucu taşır."""

    result: ModelResult


#: Bir akışın ürettiği öğeler. Akış daima tek bir `StreamDone` ile biter.
StreamItem = TextChunk | StreamDone


class VerdictSource(Enum):
    """Kazananın nasıl belirlendiği. Motor METİN üretmez; kullanıcıya gösterilecek
    açıklamayı bu koda bakarak `ui` katmanı seçer."""

    JUDGE = "judge"  # hakem değerlendirdi ve seçti
    SINGLE = "single"  # tek geçerli cevap vardı, hakem atlandı
    FALLBACK = "fallback"  # hakem yetişemedi/bozuk çıktı verdi, ilk aday seçildi
    NONE = "none"  # hiçbir aday yanıt veremedi


@dataclass(frozen=True, slots=True)
class Verdict:
    """Hakem kararı."""

    winner: str
    scores: dict[str, float]
    reason: str
    #: Hakem çıktısı ayrıştırılabildi mi? False ise sezgisel kazanan seçilmiştir.
    parsed: bool


@dataclass(frozen=True, slots=True)
class FusionResult:
    """Bir fusion turunun tüm çıktısı: kazanan, nihai cevap ve aday kayıtları."""

    task: str
    task_type: str
    winner: str
    final_answer: str
    source: VerdictSource
    candidates: tuple[ModelResult, ...]
    #: Hakemin kendi gerekçesi (model çıktısı). Hakem çalışmadıysa boştur.
    reason: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    synthesized: bool = False

    @property
    def successful(self) -> tuple[ModelResult, ...]:
        """Metin üretebilen adaylar."""
        return tuple(candidate for candidate in self.candidates if candidate.ok and candidate.text)
