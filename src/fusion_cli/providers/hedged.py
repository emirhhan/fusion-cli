"""Hedged sağlayıcı — N sağlayıcıyı YARIŞTIRIR, ilk başarılı yanıt kazanır.

Neden dekoratör: eski projede yarıştırma mantığı `acomplete` fonksiyonunun içine
gömülüydü ve streaming için ayrıca kopyalanmıştı. Burada tek bir generic sarmalayıcı
hem `complete` hem `stream` için çalışır ve sarmaladığı şeyin ne olduğunu bilmez;
yeni bir sağlayıcı eklendiğinde dayanıklılık davranışı bedava gelir.

Davranış:
- Birincil sağlayıcıya bir ÖNCELİK PENCERESİ (`hedge_delay_s`) tanınır; o pencerede
  çıktı üretirse yedekler hiç başlatılmaz.
- Pencere dolar ya da birincil hata verirse yedekler başlatılır ve yarış başlar.
- İlk başarılı yanıt kazanır; kalanlar iptal edilir.
- Hiçbiri başaramazsa hata fırlatılmaz; tüm hataları birleştiren `ok=False` sonuç döner.
- Akışta ilk ÇIKTI ÜRETEN akış kazanır (yalnız bağlantı açan değil): soğuk ya da hemen
  hata veren bir uç turu kilitleyemez.

Öncelik penceresi neden var: yedek zinciri bilinçli olarak farklı SAĞLAYICI ve farklı
MODEL içerir, dolayısıyla yedekler çoğu zaman birincilden küçük ve hızlıdır. Gecikmesiz
yarıştırmada küçük model neredeyse her turda kazanır ve yapılandırmada yazan birincil
model pratikte hiç kullanılmaz — dayanıklılık sessizce kalite kaybına dönüşür. Pencere,
yedekleri yalnızca GERÇEK arıza durumunda (yavaşlık, 429, soğuk uç) devreye sokar.

PENCERENİN BİRİMİ — iki yol farklı şey ölçer ve değer buna göre yazılır:

    complete()  pencere, birincilin ÇAĞRIYI TAMAMLAMASINA tanınır.
    stream()    pencere, birincilin İLK ÇIKTIYI üretmesine tanınır.

Bu yüzden değer, birincil modelin ÖLÇÜLEN TAM YANIT SÜRESİNE göre yazılır (bkz.
`defaults.yaml`: kademe etiketlerindeki süreler, üç katı alınarak). Tam süreye göre
yazılan bir pencere `complete()` için doğrudur ve `stream()` için fazlasıyla
cömerttir — ikisinde de yedek yalnızca gerçek arızada devreye girer.

Tersi yapılırsa hata sessizdir: pencere ilk-token süresine göre yazılmıştı (2.5s,
tek bir hızlı modelden) ve `complete()` yolunda hiçbir model o sürede BİTMEDİĞİ için
yedekler her turda başlıyordu. Yavaş ama yetenekli model kendi yarışını küçük
yedeğine kaybediyordu; kullanıcı bir kademe seçip bir alt kademenin cevabını alıyordu.

Pencere ROL BAŞINADIR (`ModelSpec.hedge_delay_s`): hız birincil modelin özelliğidir,
motorun geneline ait bir sabit değildir. Rol yazmazsa `runtime.hedge_delay_s` geçerli.

`hedge_delay_s=0` bugüne kadarki "hepsi aynı anda" davranışıdır; artık varsayılan değil,
açık bir tercihtir.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from ..core.errors import ProviderError
from ..core.protocols import LlmProvider
from ..core.types import CompletionRequest, ModelResult, StreamDone, StreamItem

#: Bir akışın ilk öğesi: (sıra numarası, öğe). Öğe None ise akış hiç üretmeden bitti.
_Opened = tuple[int, StreamItem | None]


class HedgedProvider:
    """Birden çok sağlayıcıyı yarıştıran sağlayıcı."""

    def __init__(
        self, providers: Sequence[LlmProvider], *, role: str, hedge_delay_s: float = 0.0
    ) -> None:
        if not providers:
            raise ProviderError(f"'{role}' için tanımlı model yok.")
        self._providers = tuple(providers)
        self._role = role
        # Mekanizmanın nötr değeri: gecikme yok. Ürünün gerçek değeri yapılandırmadan
        # (`defaults.yaml` → `runtime.hedge_delay_s`) gelir; burada varsayılan TUTULMAZ.
        self._hedge_delay_s = hedge_delay_s

    @property
    def label(self) -> str:
        return " | ".join(provider.label for provider in self._providers)

    async def complete(self, request: CompletionRequest) -> ModelResult:
        if len(self._providers) == 1:
            return await self._providers[0].complete(request)

        primary = asyncio.create_task(self._providers[0].complete(request))
        tasks = [primary]
        yarisacaklar = tasks
        failures: list[ModelResult] = []
        try:
            if await _priority_window(primary, self._hedge_delay_s):
                # Birincil pencerede bitti: KULLANILABİLİR sonuç verdiyse yedekler
                # hiç başlatılmaz. Ölçüt `ok` DEĞİL `is_usable`: model bazen boş
                # cevap döndürüyor (metinsiz, araçsız) ve bu teknik olarak
                # başarılıdır — yarışı kazanıp turu hiçbir iş yapmadan bitiriyordu.
                result = primary.result()
                if result.is_usable:
                    return result
                # Başarısız: sonucu burada tükettik, yarışa tekrar sokmuyoruz.
                failures.append(result)
                yarisacaklar = []

            yedekler = [
                asyncio.create_task(provider.complete(request)) for provider in self._providers[1:]
            ]
            tasks.extend(yedekler)
            for finished in asyncio.as_completed([*yarisacaklar, *yedekler]):
                result = await finished
                if result.is_usable:
                    return result
                failures.append(result)
        finally:
            await _cancel_all(tasks)
        return self._all_failed(failures)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        if len(self._providers) == 1:
            async for item in self._providers[0].stream(request):
                yield item
            return

        # Akış nesnesi tembeldir: oluşturmak sağlayıcıyı ÇAĞIRMAZ, ilk `anext` çağırır.
        # Bu yüzden yedeklerin akışı pencere dolmadan yaratılsa bile ağ trafiği doğmaz;
        # yedek yalnızca `_open` görevi başlatıldığında gerçekten çalışır.
        streams = [provider.stream(request) for provider in self._providers]
        primary = asyncio.create_task(_open(0, streams[0]))
        openers = [primary]
        yarisacaklar = openers
        winner: tuple[int, StreamItem] | None = None
        failures: list[ModelResult] = []

        try:
            if await _priority_window(primary, self._hedge_delay_s):
                index, opened = primary.result()
                if opened is not None and not _is_failed_open(opened):
                    winner = (index, opened)
                else:
                    if opened is not None:
                        failures.append(opened.result)  # type: ignore[union-attr]
                    yarisacaklar = []

            if winner is None:
                yedekler = [
                    asyncio.create_task(_open(index, stream))
                    for index, stream in enumerate(streams)
                    if index > 0
                ]
                openers.extend(yedekler)
                winner, failures = await self._yaris([*yarisacaklar, *yedekler], failures, winner)
        finally:
            await _cancel_all(openers)

        if winner is None:
            await _close_all(streams)
            yield StreamDone(self._all_failed(failures))
            return

        winning_index, first_item = winner
        await _close_all([s for position, s in enumerate(streams) if position != winning_index])

        yield first_item
        if isinstance(first_item, StreamDone):
            return
        async for item in streams[winning_index]:
            yield item

    async def _yaris(
        self,
        openers: Sequence[asyncio.Task[_Opened]],
        failures: list[ModelResult],
        winner: tuple[int, StreamItem] | None,
    ) -> tuple[tuple[int, StreamItem] | None, list[ModelResult]]:
        """Açılan akışlar arasında ilk ÇIKTI ÜRETENİ seç."""
        for finished in asyncio.as_completed(openers):
            index, opened = await finished
            if opened is None:
                continue
            if _is_failed_open(opened):
                failures.append(opened.result)  # type: ignore[union-attr]
                continue
            return (index, opened), failures
        return winner, failures

    def _all_failed(self, failures: Sequence[ModelResult]) -> ModelResult:
        errors = "; ".join(failure.error or "bilinmeyen hata" for failure in failures)
        return ModelResult(
            name=self._role,
            model=self._providers[0].label,
            text="",
            latency_ms=max((failure.latency_ms for failure in failures), default=0),
            ok=False,
            error=errors or "tüm sağlayıcılar yanıt veremedi",
        )


def _is_failed_open(opened: StreamItem) -> bool:
    """Akış hiç çıktı üretmeden başarısız mı bitti?"""
    return isinstance(opened, StreamDone) and not opened.result.ok


async def _priority_window(primary: asyncio.Task[Any], delay_s: float) -> bool:
    """Birinciline öncelik penceresi tanı; pencerede bittiyse True.

    Gecikme 0 ise beklenmez ve False döner: yedekler hemen başlar (eski davranış).
    Birincil pencereden ÖNCE hata verirse de True döner — çağıran sonucu inceleyip
    yedeklere geçer, yani hata anında geldiğinde pencere boşuna beklenmez.
    """
    if delay_s <= 0:
        return False
    await asyncio.wait({primary}, timeout=delay_s)
    return primary.done()


async def _open(index: int, stream: AsyncIterator[StreamItem]) -> _Opened:
    """Akıştan ilk öğeyi çek; akış hiç üretmeden biterse None döndür."""
    try:
        return index, await anext(stream)
    except StopAsyncIteration:
        return index, None


async def _cancel_all(tasks: Sequence[asyncio.Task[Any]]) -> None:
    pending = [task for task in tasks if not task.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def _close_all(streams: Sequence[AsyncIterator[StreamItem]]) -> None:
    """Kaybeden akışları kapat; arkada açık bağlantı bırakma."""
    for stream in streams:
        closer = getattr(stream, "aclose", None)
        if closer is None:
            continue
        # Kaybeden akışın kapanış hatası turu etkilemez; bilinçli olarak yutulur.
        try:
            await closer()
        except Exception:
            continue
