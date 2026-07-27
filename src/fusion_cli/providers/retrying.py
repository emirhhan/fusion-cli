"""Yeniden deneyen sağlayıcı — AYNI modeli, geçici arızada tekrar dener.

Neden dekoratör: sarmaladığı şeyin ne olduğunu bilmez, tek bir modeli temsil eden
her sağlayıcı için çalışır. Zincirdeki her modele ayrı ayrı takılır, dolayısıyla
"her modele iki yeniden deneme" kuralı zincirin uzunluğundan bağımsızdır.

Davranış:
- Sonuç KULLANILABİLİRSE (`is_usable`) hemen döner; bekleme yoktur.
- Geçici arızada gecikme kadar beklenip AYNI model tekrar çağrılır.
- Gecikme listesi bitince son başarısız sonuç döner ve zincir yedeğe geçer.
- Kalıcı hatada (olmayan model, geçersiz anahtar, günlük kota) hiç beklenmez.

Neden aynı model: sağlayıcının hız sınırı MODEL BAŞINADIR (NVIDIA NIM'de ölçüldü)
ve 60 saniyede 40 isteğe izin verir. Dakikalık sınıra takılan bir çağrı, kısa bir
beklemeden sonra aynı modelde başarılı olur. Eskiden bu durumda doğrudan yedeğe
düşülüyordu: kullanıcı seçtiği modeli GEÇİCİ bir arıza yüzünden kaybediyordu.

Akışta yeniden deneme yalnızca HİÇ ÇIKTI ÜRETİLMEDEN başarısız olan çağrı için
yapılır. Bir kez metin aktıktan sonra tekrar denemek, kullanıcının ekranında
gördüğü cevabı ikinci kez baştan yazdırırdı.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from ..core.clock import SystemSleeper
from ..core.protocols import LlmProvider, Sleeper
from ..core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    is_permanent_error,
)


class RetryingProvider:
    """Tek bir modeli geçici arızada yeniden deneyen sarmalayıcı."""

    def __init__(
        self,
        inner: LlmProvider,
        *,
        delays_s: Sequence[float],
        sleeper: Sleeper | None = None,
    ) -> None:
        #: Gecikme listesi deneme sayısını da TANIMLAR: n gecikme → n+1 deneme.
        #: Ayrı bir "max_attempts" ayarı olsaydı ikisi birbiriyle çelişebilirdi.
        self._delays_s = tuple(delays_s)
        self._inner = inner
        self._sleeper = sleeper or SystemSleeper()

    @property
    def label(self) -> str:
        return self._inner.label

    async def complete(self, request: CompletionRequest) -> ModelResult:
        result = await self._inner.complete(request)
        for delay in self._delays_s:
            if not self._should_retry(result):
                return result
            await self._sleeper.sleep(delay)
            result = await self._inner.complete(request)
        return result

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        # Son tur `None` gecikmesiyle işaretlenir: "artık bekleme, sonucu ne olursa
        # olsun ver". Deneme sayısı yine gecikme listesinden türer, ayrı sayaç yok.
        for delay in (*self._delays_s, None):
            stream = self._inner.stream(request)
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
            await _close(stream)
            if delay is None or not self._should_retry(erken):
                yield StreamDone(erken)
                return
            await self._sleeper.sleep(delay)

    # ----------------------------------------------------------------------- #

    def _should_retry(self, result: ModelResult) -> bool:
        """Bu sonuç için beklemeye değer mi?

        Ölçüt `ok` DEĞİL `is_usable`: model bazen boş cevap döndürüyor (metin yok,
        araç çağrısı yok) ve bu teknik olarak başarılı bir yanıttır. Yeniden
        denenmezse tur hiçbir iş yapmadan biter.
        """
        return not result.is_usable and not is_permanent_error(result.error)


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


async def _close(stream: AsyncIterator[StreamItem]) -> None:
    """Yeniden denemeden önce kaybeden akışı kapat; arkada açık bağlantı bırakma."""
    closer = getattr(stream, "aclose", None)
    if closer is None:
        return
    # Kapanış hatası turu etkilemez; bilinçli olarak yutulur.
    try:
        await closer()
    except Exception:
        return


def wrap(
    providers: Sequence[LlmProvider],
    *,
    delays_s: Sequence[float],
    sleeper: Sleeper | None = None,
) -> tuple[LlmProvider, ...]:
    """Her sağlayıcıyı ayrı ayrı yeniden deneme katmanıyla sar.

    Gecikme listesi boşsa sarmalanmaz: davranışı değiştirmeyen bir katman eklemek
    yığını okumayı zorlaştırmaktan başka bir şey yapmaz.
    """
    if not delays_s:
        return tuple(providers)
    return tuple(
        RetryingProvider(provider, delays_s=delays_s, sleeper=sleeper) for provider in providers
    )
