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

from collections.abc import AsyncIterator, Sequence

from ..core.errors import ProviderError
from ..core.protocols import LlmProvider
from ..core.types import CompletionRequest, ModelResult, StreamDone, StreamItem


class FallbackProvider:
    """Sağlayıcıları sırayla deneyen sağlayıcı."""

    def __init__(self, providers: Sequence[LlmProvider], *, role: str) -> None:
        if not providers:
            raise ProviderError(f"'{role}' için tanımlı model yok.")
        self._providers = tuple(providers)
        self._role = role

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
        for provider in self._providers:
            result = await provider.complete(request)
            # Ölçüt `ok` DEĞİL `is_usable`: model bazen boş cevap döndürüyor
            # (metin yok, araç çağrısı yok) ve bu teknik olarak başarılı bir
            # yanıttır — turu hiçbir iş yapmadan bitiriyordu.
            if result.is_usable:
                return result
            failures.append(result)
        return self._all_failed(failures)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        failures: list[ModelResult] = []
        for provider in self._providers:
            stream = provider.stream(request)
            first = await anext(stream, None)
            if first is None:
                continue
            if isinstance(first, StreamDone) and not first.result.is_usable:
                # Metin akmadan başarısız bitti: sonraki modele geçilebilir.
                failures.append(first.result)
                await _close(stream)
                continue
            yield first
            if isinstance(first, StreamDone):
                return
            async for item in stream:
                yield item
            return
        yield StreamDone(self._all_failed(failures))

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
