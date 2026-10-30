"""Web oturumu hatası sınıfı: bekletmeden yedeğe geç, devreyi hemen aç (30 Ekim denemesi).

Ölçüldü (30 Ekim, Gemini web, "3.1 Pro" seçili): model menüsündeki seçenek
`aria-disabled="true"` iken tıklama 5 sn zaman aşımına uğradı. Bu hata geçici sanıldığı
için her model çağrısında önce Gemini yeniden deneniyor, sonra yedeğe düşülüyordu; bir
turda 9 kez "yedek devrede" basıldı ve devre ancak üçüncü başarısız ÇAĞRIDAN sonra açıldı.
"""

from __future__ import annotations

from fusion_cli.core.health import CircuitPhase, ModelHealth
from fusion_cli.core.types import ModelResult, is_permanent_error, is_web_session_error
from fusion_cli.providers.chain import FallbackProvider
from fusion_cli.providers.circuit import CIRCUIT_OPEN_ERROR, CircuitBreakingProvider
from fusion_cli.providers.retrying import wrap

from .fakes import FakeProvider, request

OTURUM_HATASI = "web oturumu hatası: Gemini Web model seçeneği tıklanamadı"


class _Saat:
    def __init__(self) -> None:
        self.t = 0.0

    def monotonic(self) -> float:
        return self.t

    def now(self) -> float:
        return self.t


class _Uyutucu:
    def __init__(self) -> None:
        self.beklemeler: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.beklemeler.append(seconds)


class _Sayac(FakeProvider):
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        self.cagri = 0

    async def complete(self, request):
        self.cagri += 1
        return await super().complete(request)


def _saglik(saat: _Saat) -> ModelHealth:
    return ModelHealth(failure_threshold=3, cooldown_s=60.0, alpha=0.3, clock=saat)


def test_oturum_hatasi_kalici_sinifta():
    assert is_web_session_error(OTURUM_HATASI)
    assert is_permanent_error(OTURUM_HATASI)
    # Playwright zaman aşımı da ("Timeout") oturum hatası sarmalıyla gelir.
    assert is_permanent_error("web oturumu hatası: click: Timeout 5000ms exceeded.")


def test_yavas_yanit_ve_gecici_sayfa_hatasi_oturum_hatasi_sayilmaz():
    """Süre aşımında komşu modele geçiş yeniden denemeye dayanır; kalıcı sayılırsa bozulur."""
    assert not is_web_session_error(
        "web oturumu hatası: Gemini Web yanıtı 180 saniyede tamamlanmadı"
    )
    assert not is_web_session_error(
        "web oturumu hatası: Gemini Web geçici bir hata bildirdi (kota DEĞİL)."
    )
    assert not is_web_session_error("web oturumu zaman aşımı")
    assert not is_web_session_error("429 rate limit")
    assert not is_web_session_error(None)


async def test_oturum_hatasi_ayni_modelle_yeniden_denenmez():
    ic = _Sayac("gemini", ok=False, error=OTURUM_HATASI)
    uyutucu = _Uyutucu()
    (sarmal,) = wrap([ic], delays_s=(1.5, 4.0), sleeper=uyutucu)

    await sarmal.complete(request())

    assert ic.cagri == 1
    assert uyutucu.beklemeler == []


def test_oturum_hatasi_devreyi_hemen_acar():
    saat = _Saat()
    saglik = _saglik(saat)

    saglik.record(False, session_error=True)

    assert saglik.phase is CircuitPhase.OPEN
    assert not saglik.allow()


def test_oturum_hatasi_devresi_birkac_dakika_sonra_yeniden_denenir():
    saat = _Saat()
    saglik = _saglik(saat)
    saglik.record(False, session_error=True)

    saat.t = 61.0  # sıradan cooldown dolmuş olurdu
    assert not saglik.allow()
    saat.t = 400.0
    assert saglik.allow()  # yarı-açık deneme
    saglik.record(True)
    assert saglik.phase is CircuitPhase.CLOSED


async def test_gemini_bir_kez_denenir_sonraki_cagrilar_dogrudan_yedege_gider():
    gemini = _Sayac("gemini_web/main/auto", ok=False, error=OTURUM_HATASI)
    yedek = _Sayac("nim", chunks=("tamam",))
    saat = _Saat()
    saglik_g = _saglik(saat)
    saglik_y = _saglik(saat)
    uyutucu = _Uyutucu()
    g, y = wrap([gemini, yedek], delays_s=(1.5, 4.0), sleeper=uyutucu)
    zincir = FallbackProvider(
        [
            CircuitBreakingProvider(g, health=saglik_g, role="agent"),
            CircuitBreakingProvider(y, health=saglik_y, role="agent"),
        ],
        role="agent",
    )

    sonuclar = [await zincir.complete(request()) for _ in range(5)]

    assert all(s.text == "tamam" for s in sonuclar)
    assert gemini.cagri == 1  # eskiden her çağrıda (ve her yeniden denemede) çağrılıyordu
    assert uyutucu.beklemeler == []
    assert saglik_g.phase is CircuitPhase.OPEN


class _Yayinci:
    def __init__(self) -> None:
        self.olaylar: list[object] = []

    def publish(self, event: object) -> None:
        self.olaylar.append(event)


async def test_devre_acik_yedek_bildirimi_ayni_zincirde_tekrarlanmaz():
    from fusion_cli.core.events import ModelFallbackActivated

    gemini = FakeProvider("gemini", ok=False, error=CIRCUIT_OPEN_ERROR)
    yedek = FakeProvider("nim", chunks=("tamam",))
    yayinci = _Yayinci()
    zincir = FallbackProvider([gemini, yedek], role="agent", publisher=yayinci)

    for _ in range(4):
        await zincir.complete(request())

    bildirimler = [o for o in yayinci.olaylar if isinstance(o, ModelFallbackActivated)]
    assert len(bildirimler) == 1


def _sonuc(hata: str) -> ModelResult:
    return ModelResult(name="a", model="m", text="", latency_ms=1, ok=False, error=hata)
