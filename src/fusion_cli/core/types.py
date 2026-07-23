"""Katmanlar arasında dolaşan değer nesneleri.

Hepsi `frozen`: mutasyon yerine `dataclasses.replace` kullanılır. Katmanlar arası
veri taşıması dict ile değil bu tiplerle yapılır (RULES.md "Katman Sınırları").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Bir çağrının token tüketimi."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class Message:
    """Sohbet mesajı. `role`: system | user | assistant | tool."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Bir model rolünün tanımı: birincil model + yedek zinciri.

    `fallback` yedek model kimlikleridir. Hedged çağrıda birincil ile AYNI ANDA
    denenirler; ilk başarılı yanıt kazanır (bkz. `providers.hedged`).
    """

    name: str
    model: str
    tags: tuple[str, ...] = ()
    fallback: tuple[str, ...] = ()

    @property
    def models(self) -> tuple[str, ...]:
        """Birincil + yedekler, sıra korunarak ve tekrarlar atılarak."""
        return tuple(dict.fromkeys([self.model, *self.fallback]))


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """Sağlayıcıya verilen çağrı isteği. Sağlayıcıdan bağımsızdır."""

    messages: tuple[Message, ...]
    temperature: float
    max_tokens: int
    timeout_s: float
    max_retries: int = 0


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

    @property
    def is_rate_limited(self) -> bool:
        """Başarısızlık ücretsiz kota/hız sınırından mı kaynaklandı?

        Sağlayıcılar bunu farklı sözcüklerle bildirir; kullanıcıya doğru öneriyi
        gösterebilmek için tek yerde sınıflandırılır.
        """
        if self.ok or not self.error:
            return False
        lowered = self.error.lower()
        return any(
            marker in lowered
            for marker in ("429", "ratelimit", "rate limit", "too many requests", "quota")
        )


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
