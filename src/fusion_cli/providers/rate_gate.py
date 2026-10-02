"""Hız kapısı — 429'a düşmeden ÖNCE yavaşlatan ve 429'u sekmelerle paylaşan katman.

Kompozisyondaki yeri en içtedir (tek bir model ya da tek bir anahtar):

    LiteLlmProvider → RateGatedProvider → RetryingProvider → Circuit → Fallback

İki iş yapar:

1. **Önden ayar.** Sağlayıcının dakikalık sınırı biliniyorsa (NIM: model başına
   40 istek/60 sn, bkz. `defaults.yaml`) çağrı ortak kovadan hak alır. Hak kısa
   sürede doluyorsa beklenir; uzunsa çağrı yapılmadan "hız sınırı" sonucu döner
   ve zincir hemen yedeğe geçer. Paralel alt ajanlar ve birden çok sekme aynı
   kovayı paylaştığı için sınır, kimse 429 almadan korunur.
2. **Paylaşılan soğuma.** 429 alan model bütün süreçlerde `cooldown_s` boyunca
   çağrılmadan atlanır; öteki sekme aynı duvara tekrar çarpmaz.

Defter erişilemezse kapı hiçbir şey yapmaz (bkz. `rate_ledger`); çağrı yine olur.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator

from ..core.clock import SystemClock, SystemSleeper
from ..core.protocols import Clock, LlmProvider, RateLedger, Sleeper
from ..core.rate_control import RateControl
from ..core.types import CompletionRequest, ModelResult, StreamDone, StreamItem

#: Kapının ürettiği sonucun hata öneki. "rate limit" içerir: `is_rate_limit_error`
#: onu gerçek bir 429 gibi sınıflandırır ve zincir aynı yoldan yedeğe geçer.
GATE_ERROR_PREFIX = "rate limit (paylaşılan hız defteri):"


class RateGatedProvider:
    """Tek bir modeli/anahtarı ortak hız defterine bağlayan sarmalayıcı."""

    def __init__(
        self,
        inner: LlmProvider,
        *,
        ledger: RateLedger,
        key: str,
        per_minute: float | None,
        pace_max_wait_s: float,
        cooldown_s: float,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        self._inner = inner
        self._ledger = ledger
        self._key = key
        self._per_minute = per_minute
        self._pace_max_wait_s = pace_max_wait_s
        self._cooldown_s = cooldown_s
        self._clock = clock or SystemClock()
        self._sleeper = sleeper or SystemSleeper()

    @property
    def label(self) -> str:
        return self._inner.label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        blocked = await self._admit()
        if blocked is not None:
            return blocked
        result = await self._inner.complete(request)
        self._record(result)
        return result

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        blocked = await self._admit()
        if blocked is not None:
            yield StreamDone(blocked)
            return
        async for item in self._inner.stream(request):
            if isinstance(item, StreamDone):
                self._record(item.result)
            yield item

    async def _admit(self) -> ModelResult | None:
        """Çağrıya izin ver ya da çağrı yapmadan dönülecek sonucu üret."""
        until = self._ledger.cooled_until(self._key)
        if until:
            remaining = max(0.0, until - self._clock.now())
            return self._blocked(f"başka bir çağrı 429 aldı; {remaining:.0f} sn soğumada")
        if not self._per_minute:
            return None
        wait_s = self._ledger.take_token(self._key, self._per_minute)
        if wait_s == 0.0:
            return None
        if wait_s > self._pace_max_wait_s:
            return self._blocked(f"dakikalık sınır dolu; {wait_s:.0f} sn sonra hak açılıyor")
        await self._sleeper.sleep(wait_s)
        # Beklerken hakkı başka süreç almış olabilir: ikinci kez de dolu ise yedeğe bırak.
        if self._ledger.take_token(self._key, self._per_minute) == 0.0:
            return None
        return self._blocked("dakikalık sınır dolu; yedeğe bırakılıyor")

    def _record(self, result: ModelResult) -> None:
        if result.is_rate_limited and self._cooldown_s > 0:
            self._ledger.cool(self._key, self._clock.now() + self._cooldown_s)

    def _blocked(self, reason: str) -> ModelResult:
        return ModelResult(
            name=self._inner.label,
            model=self._inner.label,
            text="",
            latency_ms=0,
            ok=False,
            error=f"{GATE_ERROR_PREFIX} {reason}",
        )


def keyed_label(model: str, api_key: str) -> str:
    """Anahtara özgü defter kimliği. Anahtarın KENDİSİ deftere yazılmaz, özeti yazılır."""
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
    return f"{model}#{digest}"


def gate(
    inner: LlmProvider,
    rate: RateControl,
    *,
    key: str,
    provider_id: str,
    clock: Clock | None = None,
    sleeper: Sleeper | None = None,
) -> RateGatedProvider:
    """`RateControl` ayarlarıyla bir yaprağı kapıya bağla."""
    return RateGatedProvider(
        inner,
        ledger=rate.ledger,
        key=key,
        per_minute=rate.per_minute.get(provider_id),
        pace_max_wait_s=rate.pace_max_wait_s,
        cooldown_s=rate.cooldown_s,
        clock=clock,
        sleeper=sleeper,
    )
