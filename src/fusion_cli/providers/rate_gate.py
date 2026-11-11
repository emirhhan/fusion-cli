"""Hız kapısı — 429'a düşmeden ÖNCE yavaşlatan ve 429'u sekmelerle paylaşan katman.

Kompozisyondaki yeri en içtedir (tek bir model ya da tek bir anahtar):

    LiteLlmProvider → RateGatedProvider → RetryingProvider → Circuit → Fallback

İki iş yapar:

1. **Önden ayar.** Dakikalık sınır yapılandırılmışsa çağrı ortak kovadan hak
   alır. Tam model girdisi kovada bir hak tutar ve çağrıları aralıklı gönderir. Hak kısa
   sürede doluyorsa beklenir; uzunsa çağrı yapılmadan "hız sınırı" sonucu döner
   ve zincir hemen yedeğe geçer. Paralel alt ajanlar ve birden çok sekme aynı
   kovayı paylaştığı için sınır, kimse 429 almadan korunur.
2. **Paylaşılan soğuma.** 429 bekleme süresi bütün süreçler için kaydedilir.
   Tam model girdilerinde sunucu süre belirtmezse soğuma aralıklı gönderim süresinden
   başlayıp `cooldown_s` sınırına kadar artar.

Defter erişilemezse kapı hiçbir şey yapmaz (bkz. `rate_ledger`); çağrı yine olur.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncIterator
from dataclasses import replace

from ..core.clock import SystemClock, SystemSleeper
from ..core.protocols import Clock, LlmProvider, RateLedger, Sleeper
from ..core.provider_diagnostics import observe_phase
from ..core.rate_control import RateControl, model_pacing_rate, rate_wait_fits
from ..core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    is_daily_quota_error,
)
from .stream_cleanup import closing_stream

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
        smooth: bool = False,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        self._inner = inner
        self._ledger = ledger
        self._key = key
        self._per_minute = per_minute
        self._pace_max_wait_s = pace_max_wait_s
        self._cooldown_s = cooldown_s
        self._smooth = smooth
        self._backoff_base_s = (
            60.0 / per_minute if smooth and per_minute and cooldown_s > 0.0 else None
        )
        self._pace_key = inner.label if smooth else key
        self._clock = clock or SystemClock()
        self._sleeper = sleeper or SystemSleeper()

    @property
    def label(self) -> str:
        return self._inner.label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        observe_phase(request, "rate_admission_enter")
        blocked = await self._admit(request)
        observe_phase(request, "rate_rejected" if blocked is not None else "rate_admitted")
        if blocked is not None:
            return blocked
        dispatched_at = self._clock.now() if self._backoff_base_s is not None else None
        result = await self._inner.complete(request)
        return self._record(result, dispatched_at)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        observe_phase(request, "rate_admission_enter")
        blocked = await self._admit(request)
        observe_phase(request, "rate_rejected" if blocked is not None else "rate_admitted")
        if blocked is not None:
            yield StreamDone(blocked)
            return
        dispatched_at = self._clock.now() if self._backoff_base_s is not None else None
        async with closing_stream(self._inner.stream(request)) as stream:
            async for item in stream:
                if isinstance(item, StreamDone):
                    item = StreamDone(self._record(item.result, dispatched_at))
                yield item

    async def _admit(self, request: CompletionRequest) -> ModelResult | None:
        """Çağrıya izin ver ya da çağrı yapmadan dönülecek sonucu üret."""
        if (blocked := self._cooldown_result()) is not None:
            return blocked
        if not self._per_minute:
            return None
        if self._smooth:
            return await self._admit_smoothed(request, self._per_minute)
        wait_s = self._ledger.take_token(self._key, self._per_minute)
        if wait_s == 0.0:
            return None
        if wait_s > self._pace_max_wait_s:
            return self._blocked(
                f"dakikalık sınır dolu; {wait_s:.0f} sn sonra hak açılıyor", retry_after_s=wait_s
            )
        observe_phase(request, "rate_wait", wait_s=wait_s)
        await self._sleeper.sleep(wait_s)
        observe_phase(request, "rate_wait_end")
        if (blocked := self._cooldown_result()) is not None:
            return blocked
        # Beklerken hakkı başka süreç almış olabilir: ikinci kez de dolu ise yedeğe bırak.
        if self._ledger.take_token(self._key, self._per_minute) == 0.0:
            return None
        return self._blocked("dakikalık sınır dolu; yedeğe bırakılıyor")

    async def _admit_smoothed(
        self, request: CompletionRequest, per_minute: float
    ) -> ModelResult | None:
        # A model-specific setting needs at least one slot interval. A caller
        # that explicitly disables pacing can still request an immediate result.
        pace = max(self._pace_max_wait_s, 60.0 / per_minute) if self._pace_max_wait_s > 0 else 0.0
        started = self._clock.monotonic()
        while True:
            if (blocked := self._cooldown_result()) is not None:
                return blocked
            if not rate_wait_fits(request, 0.0):
                return self._blocked("çağrı süresi doldu")
            wait_s = self._ledger.take_token(self._pace_key, per_minute, burst=1.0)
            elapsed = self._clock.monotonic() - started
            if wait_s == 0.0:
                if (blocked := self._cooldown_result()) is not None:
                    return blocked
                if self._clock.monotonic() - started >= request.timeout_s or not rate_wait_fits(
                    request, 0.0
                ):
                    return self._blocked("çağrı süresi doldu")
                return None
            if (
                wait_s > pace - elapsed
                or wait_s >= request.timeout_s - elapsed
                or not rate_wait_fits(request, wait_s)
            ):
                return self._blocked(
                    f"dakikalık sınır dolu; {wait_s:.1f} sn sonra hak açılıyor",
                    retry_after_s=wait_s,
                )
            observe_phase(request, "rate_wait", wait_s=wait_s)
            await self._sleeper.sleep(wait_s)
            observe_phase(request, "rate_wait_end")

    def _cooldown_result(self) -> ModelResult | None:
        until = self._ledger.cooled_until(self._key)
        if not until:
            return None
        remaining = max(0.0, until - self._clock.now())
        return self._blocked(
            f"başka bir çağrı 429 aldı; {remaining:.0f} sn soğumada", retry_after_s=remaining
        )

    def _record(self, result: ModelResult, dispatched_at: float | None) -> ModelResult:
        """429'u deftere yaz ve sonuca soğuma süresini `retry_after_s` olarak işle.

        Yeniden deneme katmanı bu alanı görür ve kısa sabit gecikme yerine soğuma
        bitene dek bekler; yoksa ilk deneme kapıdan anında "soğumada" döner (P1-07).
        """
        if result.ok and dispatched_at is not None:
            self._ledger.reset_backoff(self._key, dispatched_at)
        if not result.is_rate_limited:
            return result
        hint = result.retry_after_s
        if hint is not None and math.isfinite(hint) and hint >= 0:
            if hint > 0.0:
                self._ledger.cool(self._key, self._clock.now() + hint)
            return result

        wait_s = max(0.0, self._cooldown_s)
        if self._backoff_base_s is not None and not is_daily_quota_error(result.error):
            remaining = self._ledger.record_backoff(self._key, self._backoff_base_s, wait_s)
            if remaining is not None:
                return replace(result, retry_after_s=remaining)
        if wait_s > 0.0:
            self._ledger.cool(self._key, self._clock.now() + wait_s)
        return replace(result, retry_after_s=wait_s or None)

    def _blocked(self, reason: str, *, retry_after_s: float | None = None) -> ModelResult:
        return ModelResult(
            name=self._inner.label,
            model=self._inner.label,
            text="",
            latency_ms=0,
            ok=False,
            error=f"{GATE_ERROR_PREFIX} {reason}",
            retry_after_s=retry_after_s,
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
    model_rate = model_pacing_rate(rate.per_minute, inner.label, provider_id)
    return RateGatedProvider(
        inner,
        ledger=rate.ledger,
        key=key,
        per_minute=rate.per_minute.get(provider_id) if model_rate is None else model_rate,
        pace_max_wait_s=rate.pace_max_wait_s,
        cooldown_s=rate.cooldown_s,
        smooth=model_rate is not None,
        clock=clock,
        sleeper=sleeper,
    )
