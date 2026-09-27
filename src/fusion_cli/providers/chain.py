"""Yedek zinciri — modelleri SIRAYLA dener, ilk kullanılabilir yanıt kazanır.

Neden dekoratör: eski projede yedeğe geçme mantığı çağrı fonksiyonunun içine
gömülüydü ve akış için ayrıca kopyalanmıştı. Burada tek bir generic sarmalayıcı
hem `complete` hem `stream` için çalışır ve sarmaladığı şeyin ne olduğunu bilmez.

SIRALI, YARIŞTIRMALI DEĞİL. Bu kasıtlıdır ve ölçülmüş bir hatanın sonucudur:

Zincir eskiden yarıştırılıyordu — birinciline bir "öncelik penceresi" tanınıyor,
pencere dolunca yedekler paralel başlatılıyor ve İLK BİTEN kazanıyordu. Yedekler
bilinçli olarak daha küçük ve hızlı modellerdir, dolayısıyla yavaş ama yetenekli
bir birincil kendi yarışını neredeyse her turda kaybediyordu:

    premium (glm-5.2, 38s)            -> cevabı nemotron-ultra veriyordu
    ultra   (nemotron-ultra, 5.8s)    -> cevabı nemotron-super veriyordu
    high    (deepseek-v4-flash, 6.5s) -> cevabı laguna-xs veriyordu

Kullanıcı bir kademe seçiyor, motor bir alt kademeyi çalıştırıyordu. Pencereyi
model başına ayarlamak bunu düzeltiyordu ama her yeni model için yeniden ölçüm
gerektiriyordu — kırılgan bir çözüm. Sıralı zincir aynı hatayı YAPISAL olarak
imkânsız kılar: yedek, birincil BAŞARISIZ OLMADAN hiç çalışmaz. Bir modelin
hızı artık hangi modelin cevap verdiğini belirleyemez.

Dayanıklılık kaybı yoktur, yeri değişmiştir: geçici arıza artık `providers.retrying`
katmanında AYNI modelle karşılanır (bkz. o modülün gerekçesi). Zincir yalnızca o
katman da tükendiğinde devreye girer.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Sequence
from typing import TypeVar

from ..core.errors import ProviderError
from ..core.events import EventPublisher, ModelFallbackActivated
from ..core.protocols import LlmProvider
from ..core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    is_unavailable_error,
)

T = TypeVar("T")


class FallbackProvider:
    """Sağlayıcıları sırayla deneyen sağlayıcı."""

    def __init__(
        self,
        providers: Sequence[LlmProvider],
        *,
        role: str,
        publisher: EventPublisher | None = None,
        background: bool = False,
        only_when_unavailable: bool = False,
    ) -> None:
        if not providers:
            raise ProviderError(f"'{role}' için tanımlı model yok.")
        self._providers = tuple(providers)
        self._role = role
        self._publisher = publisher
        self._background = background
        #: Kullanıcı modeli açıkça seçtiyse (strict) zincir YALNIZCA model hiç
        #: cevap veremediğinde ilerler; kötü cevap yedeğe geçiş sebebi değildir.
        self._only_when_unavailable = only_when_unavailable

    @property
    def label(self) -> str:
        """BİRİNCİL modelin kimliği — yedek zinciri değil.

        Etiket "bu sağlayıcı hangi modeldir" sorusunun cevabıdır; zincir dayanıklılık
        ayrıntısıdır ve kimliğin parçası değildir. Hangi modelin GERÇEKTEN cevap
        verdiği `ModelResult.model` içindedir ve arayüz onu gösterir.
        """
        return self._providers[0].label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        failures: list[ModelResult] = []
        for index, provider in enumerate(self._providers):
            if index and failures:
                self._publish_fallback(provider.label, failures[-1])
            try:
                result = await self._bounded(index, provider.complete(request), request)
            except TimeoutError:
                failures.append(self._timed_out(provider, request))
                continue
            # Ölçüt `ok` DEĞİL `is_usable`: model bazen boş cevap döndürüyor
            # (metin yok, araç çağrısı yok) ve bu teknik olarak başarılı bir
            # yanıttır — turu hiçbir iş yapmadan bitiriyordu.
            if result.is_usable:
                return result
            failures.append(result)
            if self._only_when_unavailable and not is_unavailable_error(result.error):
                break
        return self._all_failed(failures)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        failures: list[ModelResult] = []
        for index, provider in enumerate(self._providers):
            if index and failures:
                self._publish_fallback(provider.label, failures[-1])
            stream = provider.stream(request)
            try:
                first = await self._bounded(index, anext(stream, None), request)
            except TimeoutError:
                # Takılan model yedeğin süresini yemesin: sıradakine geç.
                failures.append(self._timed_out(provider, request))
                await _close(stream)
                continue
            if first is None:
                continue
            if isinstance(first, StreamDone) and not first.result.is_usable:
                # Metin akmadan başarısız bitti: sonraki modele geçilebilir.
                failures.append(first.result)
                await _close(stream)
                if self._only_when_unavailable and not is_unavailable_error(first.result.error):
                    break
                continue
            yield first
            if isinstance(first, StreamDone):
                return
            async for item in stream:
                yield item
            return
        yield StreamDone(self._all_failed(failures))

    async def _bounded(self, index: int, work: Awaitable[T], request: CompletionRequest) -> T:
        """Arkasında yedek olan modelin İLK çıktısını `request.timeout_s` ile sınırla.

        Ölçüldü (27 Eylül): Gemini web oturumu cevap üretmeden takıldı; tek sınır
        turun dış süresiydi ve o dolunca yedek hiç denenmeden tur düştü. Son model
        sınırlanmaz: onun süresini turun dış sınırı zaten tutar.
        """
        if index >= len(self._providers) - 1:
            return await work
        return await asyncio.wait_for(work, request.timeout_s)

    def _timed_out(self, provider: LlmProvider, request: CompletionRequest) -> ModelResult:
        return ModelResult(
            name=self._role,
            model=provider.label,
            text="",
            latency_ms=int(request.timeout_s * 1000),
            ok=False,
            error=(
                f"yanıt vermedi: {provider.label} {request.timeout_s:g} saniyede cevap üretmedi"
            ),
        )

    def _publish_fallback(self, fallback_model: str, failure: ModelResult) -> None:
        if self._publisher is None:
            return
        self._publisher.publish(
            ModelFallbackActivated(
                role=self._role,
                requested_model=self.label,
                fallback_model=fallback_model,
                reason=failure.error or "kullanılabilir yanıt üretilmedi",
                background=self._background,
            )
        )

    def _all_failed(self, failures: Sequence[ModelResult]) -> ModelResult:
        """Hiçbiri başaramadı: hata FIRLATILMAZ, hepsini birleştiren sonuç döner.

        Sağlayıcı arızası beklenen bir durumdur; motorun akışını istisna ile
        kesmek yerine `ok=False` sonuç taşınır (bkz. `core.errors` notu).
        """
        errors = "; ".join(failure.error or "bilinmeyen hata" for failure in failures)
        return ModelResult(
            name=self._role,
            model=self.label,
            text="",
            latency_ms=max((failure.latency_ms for failure in failures), default=0),
            ok=False,
            error=errors or "tüm sağlayıcılar yanıt veremedi",
        )


async def _close(stream: AsyncIterator[StreamItem]) -> None:
    """Vazgeçilen akışı kapat; arkada açık bağlantı bırakma."""
    closer = getattr(stream, "aclose", None)
    if closer is None:
        return
    # Kapanış hatası turu etkilemez; bilinçli olarak yutulur.
    try:
        await closer()
    except Exception:
        return
