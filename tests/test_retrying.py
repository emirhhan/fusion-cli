"""Yeniden deneme katmanı — geçici arızada AYNI model tekrar denenir.

Gerçek gecikmeler 34 ve 68 saniyedir; testler sahte uyutucu kullanır ve
BEKLENEN süreleri kaydeder. Beklemeyi gerçekten yapmak testi kullanılamaz
kılardı — soyutlamanın var olma sebebi budur.
"""

from __future__ import annotations

from fusion_cli.core.types import CompletionRequest, Message, ModelResult, StreamDone, TextChunk
from fusion_cli.providers.retrying import RetryingProvider, wrap

#: Testlerde kullanılan gecikmeler; gerçek değerler `defaults.yaml`'dadır.
GECIKMELER = (34.0, 68.0)


class SahteUyutucu:
    """Beklemeyi yapmaz, kaydeder."""

    def __init__(self) -> None:
        self.beklemeler: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.beklemeler.append(seconds)


class ScriptliProvider:
    """Sırayla verilen sonuçları döndüren, çağrı sayısını sayan sağlayıcı."""

    def __init__(self, *sonuclar: ModelResult) -> None:
        self._sonuclar = list(sonuclar)
        self.cagri_sayisi = 0

    @property
    def label(self) -> str:
        return "test-model"

    def _sonraki(self) -> ModelResult:
        self.cagri_sayisi += 1
        # Liste tükenirse son sonuç tekrarlanır: "hep aynı hata" senaryosu.
        index = min(self.cagri_sayisi - 1, len(self._sonuclar) - 1)
        return self._sonuclar[index]

    async def complete(self, request: CompletionRequest) -> ModelResult:
        return self._sonraki()

    async def stream(self, request: CompletionRequest):
        sonuc = self._sonraki()
        # Metin VARSA akıtılır, sonuç başarısız olsa bile: gerçek sağlayıcı da
        # böyle davranır (parçalar geldikçe akar, hata sonda ortaya çıkar).
        # Bu ayrım önemlidir — "metin aktı mı" ile "sonuç iyi mi" ayrı sorulardır.
        if sonuc.text:
            yield TextChunk(sonuc.text)
        yield StreamDone(sonuc)


def _istek() -> CompletionRequest:
    return CompletionRequest(
        messages=(Message("user", "x"),), temperature=0.0, max_tokens=16, timeout_s=5
    )


def _basarili(text: str = "cevap") -> ModelResult:
    return ModelResult(name="r", model="test-model", text=text, latency_ms=1, ok=True)


def _hata(error: str) -> ModelResult:
    return ModelResult(name="r", model="test-model", text="", latency_ms=1, ok=False, error=error)


def _sar(inner: ScriptliProvider, uyutucu: SahteUyutucu) -> RetryingProvider:
    return RetryingProvider(inner, delays_s=GECIKMELER, sleeper=uyutucu)


# --------------------------------------------------------------------------- #
# complete
# --------------------------------------------------------------------------- #


async def test_basarili_cevapta_hic_beklenmez():
    inner = ScriptliProvider(_basarili())
    uyutucu = SahteUyutucu()

    sonuc = await _sar(inner, uyutucu).complete(_istek())

    assert sonuc.ok
    assert inner.cagri_sayisi == 1
    assert uyutucu.beklemeler == []


async def test_gecici_hatada_ayni_model_tekrar_denenir():
    """Hatanın çözdüğü şey: 429 alan model eskiden doğrudan YEDEĞE düşüyordu.

    NIM'in hız sınırı model başınadır ve dakikalıktır; kısa bir beklemeden sonra
    aynı model çalışır. Kullanıcı seçtiği modeli geçici bir arıza yüzünden
    kaybetmemeli.
    """
    inner = ScriptliProvider(_hata("429 Too Many Requests"), _basarili("nihayet"))
    uyutucu = SahteUyutucu()

    sonuc = await _sar(inner, uyutucu).complete(_istek())

    assert sonuc.ok and sonuc.text == "nihayet"
    assert inner.cagri_sayisi == 2
    assert uyutucu.beklemeler == [34.0]


async def test_gecikme_sayisi_kadar_yeniden_denenir():
    """İki gecikme → toplam üç deneme. Sayı listeden TÜRER, ayrı ayar yoktur."""
    inner = ScriptliProvider(_hata("500 sunucu hatası"))
    uyutucu = SahteUyutucu()

    sonuc = await _sar(inner, uyutucu).complete(_istek())

    assert not sonuc.ok
    assert inner.cagri_sayisi == 3
    assert uyutucu.beklemeler == [34.0, 68.0]


async def test_bos_cevap_da_yeniden_denenir():
    """`ok=True` ama metinsiz ve araçsız cevap iş görmez; tur boş biterdi."""
    inner = ScriptliProvider(_basarili(""), _basarili("gerçek cevap"))
    uyutucu = SahteUyutucu()

    sonuc = await _sar(inner, uyutucu).complete(_istek())

    assert sonuc.text == "gerçek cevap"
    assert inner.cagri_sayisi == 2


async def test_gunluk_kota_bitmisse_hic_beklenmez():
    """Günlük kota o gün için biter; 102 saniye beklemek yalnızca zaman kaybıdır."""
    inner = ScriptliProvider(_hata("429 free-models-per-day limit exceeded"))
    uyutucu = SahteUyutucu()

    sonuc = await _sar(inner, uyutucu).complete(_istek())

    assert not sonuc.ok
    assert inner.cagri_sayisi == 1, "kalıcı hatada tek deneme yeter"
    assert uyutucu.beklemeler == []


async def test_olmayan_model_icin_beklenmez():
    inner = ScriptliProvider(_hata("NotFoundError: model does not exist"))
    uyutucu = SahteUyutucu()

    await _sar(inner, uyutucu).complete(_istek())

    assert inner.cagri_sayisi == 1
    assert uyutucu.beklemeler == []


async def test_gecersiz_anahtar_icin_beklenmez():
    inner = ScriptliProvider(_hata("AuthenticationError: invalid api key"))
    uyutucu = SahteUyutucu()

    await _sar(inner, uyutucu).complete(_istek())

    assert inner.cagri_sayisi == 1


# --------------------------------------------------------------------------- #
# stream
# --------------------------------------------------------------------------- #


async def test_stream_gecici_hatada_yeniden_denenir():
    inner = ScriptliProvider(_hata("429"), _basarili("kurtarma"))
    uyutucu = SahteUyutucu()

    parcalar = [
        item.text
        async for item in _sar(inner, uyutucu).stream(_istek())
        if isinstance(item, TextChunk)
    ]

    assert parcalar == ["kurtarma"]
    assert uyutucu.beklemeler == [34.0]


async def test_stream_metin_aktiktan_sonra_yeniden_denenmez():
    """Ekrana yazılmış cevabı tekrar denemek onu ikinci kez baştan yazdırırdı."""
    akan_ama_bozuk = ModelResult(
        name="r", model="test-model", text="yarım", latency_ms=1, ok=False, error="500"
    )
    inner = ScriptliProvider(akan_ama_bozuk, _basarili("ikinci"))
    uyutucu = SahteUyutucu()

    parcalar = [
        item.text
        async for item in _sar(inner, uyutucu).stream(_istek())
        if isinstance(item, TextChunk)
    ]

    assert parcalar == ["yarım"], "akmış metnin üstüne ikinci cevap yazılmamalı"
    assert uyutucu.beklemeler == []


async def test_stream_daima_tek_streamdone_ile_biter():
    inner = ScriptliProvider(_hata("429"))
    uyutucu = SahteUyutucu()

    items = [item async for item in _sar(inner, uyutucu).stream(_istek())]

    assert len([item for item in items if isinstance(item, StreamDone)]) == 1
    assert not items[-1].result.ok


# --------------------------------------------------------------------------- #
# wrap
# --------------------------------------------------------------------------- #


def test_gecikme_yoksa_katman_hic_eklenmez():
    """Davranışı değiştirmeyen bir katman, yığını okumayı zorlaştırmaktan başka
    bir şey yapmaz."""
    inner = ScriptliProvider(_basarili())

    sarilmis = wrap([inner], delays_s=())

    assert sarilmis == (inner,)


def test_her_saglayici_ayri_sarilir():
    """Yeniden deneme MODEL BAŞINADIR: zincirin tamamına değil, her halkaya ayrı."""
    birinci, ikinci = ScriptliProvider(_basarili()), ScriptliProvider(_basarili())

    sarilmis = wrap([birinci, ikinci], delays_s=GECIKMELER)

    assert len(sarilmis) == 2
    assert all(isinstance(item, RetryingProvider) for item in sarilmis)
