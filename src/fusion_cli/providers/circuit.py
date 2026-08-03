"""Circuit breaker sarmalayıcısı — sağlıksız modeli hızlıca atlar.

Kompozisyondaki yeri, her modelin KENDİ yeniden-deneme katmanının DIŞIDIR:

    LiteLlmProvider → RetryingProvider → CircuitBreakingProvider → FallbackProvider

Devre AÇIKSA çağrı hiç yapılmaz; anında `ok=False` sonuç döner ve `FallbackProvider`
sıradaki modele geçer. Böylece ölü bir modeli yeniden denemek için `retry_delays_s`
kadar beklenmez — kullanıcı sağlıklı bir modele hızla yönlendirilir.

Sonuç her durumda `ModelHealth`'e kaydedilir: devre durumu ve güvenilirlik skoru
turlar arası güncel kalır (bkz. `core.health`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..core.health import ModelHealth
from ..core.protocols import LlmProvider
from ..core.types import CompletionRequest, ModelResult, StreamDone, StreamItem, TextChunk

#: Devre açıkken dönen sonucun hata metni. `FallbackProvider` bunu görüp sıradakine geçer.
CIRCUIT_OPEN_ERROR = "devre açık: model geçici olarak sağlıksız, atlanıyor"


class CircuitBreakingProvider:
    """Tek bir modeli, devresi açıksa atlayan sarmalayıcı."""

    def __init__(self, inner: LlmProvider, *, health: ModelHealth, role: str) -> None:
        self._inner = inner
        self._health = health
        self._role = role

    @property
    def label(self) -> str:
        return self._inner.label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        if not self._health.allow():
            return self._skipped()
        result = await self._inner.complete(request)
        self._health.record(ok=result.is_usable, latency_ms=result.latency_ms)
        return result

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        if not self._health.allow():
            yield StreamDone(self._skipped())
            return
        produced = False
        recorded = False
        async for item in self._inner.stream(request):
            if isinstance(item, TextChunk) and item.text:
                produced = True
            elif isinstance(item, StreamDone):
                self._health.record(ok=item.result.is_usable, latency_ms=item.result.latency_ms)
                recorded = True
            yield item
        # Protokol akışın tek `StreamDone` ile bitmesini garanti eder; yine de
        # savunmacı: hiç `StreamDone` görülmediyse üretilen metne göre kaydet.
        if not recorded:
            self._health.record(ok=produced)

    def _skipped(self) -> ModelResult:
        """Devre açık: çağrı yapılmadan dönen hızlı başarısızlık."""
        return ModelResult(
            name=self._role,
            model=self._inner.label,
            text="",
            latency_ms=0,
            ok=False,
            error=CIRCUIT_OPEN_ERROR,
        )
