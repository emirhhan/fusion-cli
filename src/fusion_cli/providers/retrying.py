"""Yeniden deneyen sağlayıcı — AYNI modeli, geçici arızada tekrar dener.

Neden dekoratör: sarmaladığı şeyin ne olduğunu bilmez, tek bir modeli temsil eden
her sağlayıcı için çalışır. Zincirdeki her modele ayrı ayrı takılır, dolayısıyla
"her modele iki yeniden deneme" kuralı zincirin uzunluğundan bağımsızdır.

Davranış:
- Sonuç KULLANILABİLİRSE (`is_usable`) hemen döner; bekleme yoktur.
- Geçici arızada gecikme kadar beklenip AYNI model tekrar çağrılır.
- Gecikme listesi bitince son başarısız sonuç döner ve zincir yedeğe geçer.
- Kalıcı hatada (olmayan model, geçersiz anahtar, günlük kota) hiç beklenmez.
- Hız sınırında (429), zincirde bu modelden sonra bir yedek varsa beklenmez; iş
  yedekle hemen sürer. Yedeksiz modelde aşağıdaki "aynı model" gerekçesi geçerlidir.
- Sonuç `retry_after_s` taşıyorsa (hız kapısının paylaşılan soğuması) bekleme
  `max(gecikme, retry_after_s)` olur: kapı soğuma bitene dek her denemeyi anında
  reddedeceği için daha kısa bekleme gecikmeleri boşa tüketirdi (P1-07; ölçüldü
  30 Ekim: 1,5 + 4 sn gecikme 60 sn'lik soğumanın içinde kalıyor, gerçek yeniden
  deneme hiç yapılmıyordu).

Neden aynı model: sağlayıcının hız sınırı MODEL BAŞINADIR (NVIDIA NIM'de ölçüldü)
ve 60 saniyede 40 isteğe izin verir. Dakikalık sınıra takılan bir çağrı, kısa bir
beklemeden sonra aynı modelde başarılı olur. Eskiden bu durumda doğrudan yedeğe
düşülüyordu: kullanıcı seçtiği modeli GEÇİCİ bir arıza yüzünden kaybediyordu.

Akışta yeniden deneme yalnızca HİÇ ÇIKTI ÜRETİLMEDEN başarısız olan çağrı için
yapılır. Bir kez metin aktıktan sonra tekrar denemek, kullanıcının ekranında
gördüğü cevabı ikinci kez baştan yazdırırdı.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace

from ..core.clock import SystemClock, SystemSleeper
from ..core.constants import RETRY_AFTER_MAX_WAIT_S
from ..core.protocols import Clock, LlmProvider, Sleeper
from ..core.provider_diagnostics import observe_phase
from ..core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    is_permanent_error,
)
from .stream_cleanup import closing_stream
from .stream_opening import is_liveness_chunk, is_provisional


class RetryingProvider:
    """Tek bir modeli geçici arızada yeniden deneyen sarmalayıcı."""

    def __init__(
        self,
        inner: LlmProvider,
        *,
        delays_s: Sequence[float],
        sleeper: Sleeper | None = None,
        yield_on_rate_limit: bool = False,
        clock: Clock | None = None,
        completion_deadline_s: float | None = None,
    ) -> None:
        #: Gecikme listesi deneme sayısını da TANIMLAR: n gecikme → n+1 deneme.
        #: Ayrı bir "max_attempts" ayarı olsaydı ikisi birbiriyle çelişebilirdi.
        self._delays_s = tuple(delays_s)
        #: Zincirde bu modelden sonra bir yedek varsa hız sınırında (429) beklenmez;
        #: sınır model başına olduğu için yedek hemen çalışabilir. Sonraki çağrı
        #: zincirin başından, yani seçili modelden yine başlar.
        self._yield_on_rate_limit = yield_on_rate_limit
        self._inner = inner
        self._sleeper = sleeper or SystemSleeper()
        self._clock = clock or SystemClock()
        self._completion_deadline_s = completion_deadline_s

    @property
    def label(self) -> str:
        return self._inner.label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        deadline = self._completion_deadline_s
        result = (
            await self._inner.complete(request)
            if deadline is None
            else await self._complete_before(request, deadline)
        )
        for delay in self._delays_s:
            if not self._should_retry(result):
                return result
            wait_s = _wait_s(delay, result)
            if deadline is not None and (
                (result.retry_after_s is not None and result.retry_after_s > RETRY_AFTER_MAX_WAIT_S)
                or wait_s >= deadline - self._clock.monotonic()
            ):
                return result
            observe_phase(
                request,
                "provider_retry_wait",
                wait_s=wait_s,
                wait_reason="rate_limit" if result.is_rate_limited else None,
            )
            await self._sleeper.sleep(wait_s)
            observe_phase(request, "provider_retry_wait_end")
            if deadline is not None:
                try:
                    result = await self._complete_before(request, deadline)
                except TimeoutError:
                    return result
            else:
                result = await self._inner.complete(request)
        return result

    async def _complete_before(self, request: CompletionRequest, deadline: float) -> ModelResult:
        remaining = deadline - self._clock.monotonic()
        if remaining <= 0:
            raise TimeoutError
        attempt = replace(request, timeout_s=min(request.timeout_s, remaining))
        async with asyncio.timeout(remaining) as timeout:
            result = await self._inner.complete(attempt)
        if timeout.expired() or self._clock.monotonic() >= deadline:
            raise TimeoutError
        return result

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        # Son tur `None` gecikmesiyle işaretlenir: "artık bekleme, sonucu ne olursa
        # olsun ver". Deneme sayısı yine gecikme listesinden türer, ayrı sayaç yok.
        for delay in (*self._delays_s, None):
            async with closing_stream(self._inner.stream(request)) as stream:
                first = await anext(stream, None)
                while is_provisional(first):
                    # Boş canlılık parçası atılmaz: üst katman modelin çalıştığını görmeli (P1-05).
                    if is_liveness_chunk(first):
                        assert first is not None
                        yield first
                    first = await anext(stream, None)
                # Metin akmadan gelen sonuç: hata da olabilir, araç çağrısından ibaret
                # başarılı bir cevap da. Ayrımı `_should_retry` yapar.
                erken = _opening_result(first, self._inner.label)
                if erken is None:
                    # Akış çıktı üretti; ekrana yazılmış metni tekrar denemek onu ikinci
                    # kez baştan yazdırırdı. Kalanı olduğu gibi geçiririz.
                    assert first is not None  # `erken is None` bunu garanti eder
                    yield first
                    async for item in stream:
                        yield item
                    return
            if delay is None or not self._should_retry(erken):
                yield StreamDone(erken)
                return
            wait_s = _wait_s(delay, erken)
            rate_hint = erken.retry_after_s if erken.is_rate_limited else None
            if rate_hint is not None and (
                rate_hint > RETRY_AFTER_MAX_WAIT_S or not _rate_wait_fits(request, wait_s)
            ):
                yield StreamDone(erken)
                return
            observe_phase(
                request,
                "provider_retry_wait",
                wait_s=wait_s,
                wait_reason="rate_limit" if erken.is_rate_limited else None,
            )
            await self._sleeper.sleep(wait_s)
            observe_phase(request, "provider_retry_wait_end")
            if rate_hint is not None and not _rate_wait_fits(request, 0.0):
                yield StreamDone(erken)
                return

    # ----------------------------------------------------------------------- #

    def _should_retry(self, result: ModelResult) -> bool:
        """Bu sonuç için beklemeye değer mi?

        Ölçüt `ok` DEĞİL `is_usable`: model bazen boş cevap döndürüyor (metin yok,
        araç çağrısı yok) ve bu teknik olarak başarılı bir yanıttır. Yeniden
        denenmezse tur hiçbir iş yapmadan biter.
        """
        if self._yield_on_rate_limit and result.is_rate_limited:
            return False
        if result.truncated and not result.is_usable:
            # Çıktı bütçesi doldu: aynı istek aynı bütçeyle aynı sonucu verir; beklemek
            # gecikme ve maliyet harcar (ölçüldü 30 Ekim). Kurtarma üst katmanda.
            return False
        return not result.is_usable and not is_permanent_error(result.error)


def _rate_wait_fits(request: CompletionRequest, wait_s: float) -> bool:
    """Bekleme, hem açılış sessizliğinden hem mutlak tur süresinden kısa olmalı."""
    opening_at = request.rate_retry_opening_at
    if opening_at is not None and wait_s >= opening_at - asyncio.get_running_loop().time():
        return False
    deadline = request.rate_retry_deadline
    return deadline is None or wait_s < deadline.remaining_s()


def _wait_s(delay_s: float, result: ModelResult) -> float:
    """Gecikme ile sonucun bildirdiği `retry_after_s`'in büyüğü (üst sınırlı)."""
    if result.retry_after_s is None:
        return delay_s
    return max(delay_s, min(result.retry_after_s, RETRY_AFTER_MAX_WAIT_S))


def _opening_result(first: StreamItem | None, label: str) -> ModelResult | None:
    """Akış METİN AKMADAN mı bitti? Bittiyse o sonucu, metin aktıysa None döndür.

    Akışın ilk öğesi `StreamDone` ise hiç metin akmamış demektir — sağlayıcı sınırı
    hata durumunda tam olarak bunu yapar. İlk öğe metinse çağrı iş görmüştür.
    """
    if first is None:
        # Akış hiçbir şey üretmeden kapandı. Sessiz başarı sayılamaz: tur cevapsız
        # biterdi ve kullanıcı sebebini göremezdi.
        return ModelResult(
            name=label,
            model=label,
            text="",
            latency_ms=0,
            ok=False,
            error="Model akışı hiç öğe üretmeden bitti.",
        )
    if isinstance(first, StreamDone):
        return first.result
    return None


def wrap(
    providers: Sequence[LlmProvider],
    *,
    delays_s: Sequence[float],
    sleeper: Sleeper | None = None,
    clock: Clock | None = None,
    completion_deadline_s: float | None = None,
) -> tuple[LlmProvider, ...]:
    """Her sağlayıcıyı ayrı ayrı yeniden deneme katmanıyla sar.

    Gecikme listesi boşsa sarmalanmaz: davranışı değiştirmeyen bir katman eklemek
    yığını okumayı zorlaştırmaktan başka bir şey yapmaz.
    """
    if not delays_s:
        return tuple(providers)
    son = len(providers) - 1
    return tuple(
        RetryingProvider(
            provider,
            delays_s=delays_s,
            sleeper=sleeper,
            clock=clock,
            completion_deadline_s=completion_deadline_s,
            # Yalnız ardından yedek gelen halka hız sınırında beklemeden bırakır.
            yield_on_rate_limit=index < son,
        )
        for index, provider in enumerate(providers)
    )
