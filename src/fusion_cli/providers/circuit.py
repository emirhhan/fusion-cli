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
from ..core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    TextChunk,
    is_authentication_error,
)

#: Devre açıkken dönen sonucun hata metni. `FallbackProvider` bunu görüp sıradakine geçer.
CIRCUIT_OPEN_ERROR = "devre açık: model geçici olarak sağlıksız, atlanıyor"


def _budget_exhausted(result: ModelResult) -> bool:
    """Çıktı bütçesi düşünmeye gitti: model sağlıklı, sorun istenen bütçede.

    Bu bir model arızası sayılmaz; sayılırsa üç denemede devre açılıyor ve
    motorun bütçe/düşünme kurtarması hiç çalışamıyordu (ölçüldü, 4 Ekim).
    """
    return result.truncated and not result.is_usable


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
        if _budget_exhausted(result):
            return result
        # Kota hatası sıradan arıza değildir: sağlayıcı "şimdi olmaz" diyor ve aynı
        # soğumayla dönmek tur bütçesini yakar. Ayrımı burada yapmak, artan geri
        # çekilmeyi bütün sağlayıcılar için tek yerde açar.
        self._health.record(
            ok=result.is_usable,
            latency_ms=result.latency_ms,
            rate_limited=result.is_rate_limited,
            auth_blocked=is_authentication_error(result.error),
        )
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
            elif isinstance(item, StreamDone) and _budget_exhausted(item.result):
                recorded = True
            elif isinstance(item, StreamDone):
                self._health.record(
                    ok=item.result.is_usable,
                    latency_ms=item.result.latency_ms,
                    rate_limited=item.result.is_rate_limited,
                    auth_blocked=is_authentication_error(item.result.error),
                )
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
