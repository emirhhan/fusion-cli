"""Çekirdek değer nesneleri."""

from __future__ import annotations

import pytest

from fusion_cli.core.errors import ConfigError, FusionError, ProviderError
from fusion_cli.core.types import ModelResult, TokenUsage, is_rate_limit_error


def test_token_toplami_hesaplanir():
    assert TokenUsage(prompt_tokens=3, completion_tokens=4).total_tokens == 7


@pytest.mark.parametrize(
    "error", ["429 Too Many Requests", "RateLimitError", "quota exceeded", "rate limit"]
)
def test_hiz_siniri_farkli_ifadelerde_taninir(error):
    result = ModelResult(name="a", model="m", text="", latency_ms=1, ok=False, error=error)

    assert result.is_rate_limited


def test_basarili_sonuc_hiz_siniri_sayilmaz():
    result = ModelResult(name="a", model="m", text="x", latency_ms=1, ok=True)

    assert not result.is_rate_limited


def test_hiz_siniri_disi_hata_ayirt_edilir():
    result = ModelResult(name="a", model="m", text="", latency_ms=1, ok=False, error="503")

    assert not result.is_rate_limited


def test_hiz_siniri_ham_metinden_de_taninir():
    """Agent motoru `ModelResult` değil yalnızca hata METNİ taşır; o yol da tanınmalı."""
    assert is_rate_limit_error("litellm.RateLimitError: ... 429 Too Many Requests")
    assert is_rate_limit_error("free-models-per-day quota exceeded")
    assert not is_rate_limit_error("503 Service Unavailable")
    assert not is_rate_limit_error("")
    assert not is_rate_limit_error(None)


def test_tum_proje_hatalari_tek_kokten_turer():
    assert issubclass(ConfigError, FusionError)
    assert issubclass(ProviderError, FusionError)


def test_gunluk_kota_gecici_sinirdan_ayrilir():
    """Aynı 429 iki farklı şey olabilir ve tepkileri zıttır.

    OpenRouter günlük kotayı AÇIKÇA söyler ("free-models-per-day"): o gün için
    biter, beklemek işe yaramaz. NVIDIA NIM ise çıplak 429 döner — dakikalık sınır
    da olabilir, tükenmiş kredi de. Ayırt edilmezse ya boşuna beklenir ya da geçici
    bir sınır yüzünden koşu gereksiz yere iptal edilir.
    """
    from fusion_cli.core.types import is_daily_quota_error, is_rate_limit_error

    openrouter = 'RateLimitError: {"message":"Rate limit exceeded: free-models-per-day..."}'
    nim = "RateLimitError: Nvidia_nimException - Error code: 429 - {'status': 429}"

    assert is_rate_limit_error(openrouter) and is_daily_quota_error(openrouter)
    assert is_rate_limit_error(nim) and not is_daily_quota_error(nim)
    assert not is_daily_quota_error("503 Service Unavailable")
    assert not is_daily_quota_error(None)


def test_bos_cevap_kullanilabilir_sayilmaz():
    """`ok=True` ama metin ve araç çağrısı YOKSA sonuç işe yaramaz.

    Ölçüldü: model bazen tamamen boş cevap döndürüyor (`ok=true`, `text=""`,
    `tool_calls=[]`). Fusion bunu başarılı tur sayıp bitiriyordu; yedek zinciri de
    devreye girmiyordu çünkü yarışı `ok` belirliyordu. Zor görevlerdeki "agent hiç
    dokunmadı" davranışının sebebi buydu.
    """
    from fusion_cli.core.types import ModelResult

    bos = ModelResult(name="a", model="m", text="", latency_ms=1, ok=True)
    bosluk = ModelResult(name="a", model="m", text="   \n", latency_ms=1, ok=True)

    assert not bos.is_usable
    assert not bosluk.is_usable


def test_metin_ya_da_arac_cagrisi_varsa_kullanilabilir():
    from fusion_cli.core.types import ModelResult, ToolCall

    metinli = ModelResult(name="a", model="m", text="cevap", latency_ms=1, ok=True)
    aracli = ModelResult(
        name="a",
        model="m",
        text="",
        latency_ms=1,
        ok=True,
        tool_calls=(ToolCall(id="1", name="write_file", arguments="{}"),),
    )

    assert metinli.is_usable
    assert aracli.is_usable, "araç çağıran cevap metinsiz de olsa iş yapar"


def test_basarisiz_sonuc_kullanilabilir_degildir():
    from fusion_cli.core.types import ModelResult

    assert not ModelResult(name="a", model="m", text="x", latency_ms=1, ok=False).is_usable


def test_hata_siniflandirma_ilgisiz_sayiyi_durum_kodu_saymaz():
    """Durum kodu işareti sözcük sınırıyla aranır (C1-13).

    Ölçüldü (30 Ekim): '4290 tokens' kota, 'line 500' altyapı, '14043' kalıcı hata
    sanılıyordu (düz alt-dize eşlemesi).
    """
    from fusion_cli.core.types import is_infrastructure_error, is_permanent_error

    assert not is_rate_limit_error("işlem 4290 token tuttu")
    assert not is_infrastructure_error("SyntaxError: line 500, column 3")
    assert not is_infrastructure_error("hata kodu 15004")
    assert not is_permanent_error("sonuç 14043 satır")
    # gerçek durum kodları yine tanınır
    assert is_rate_limit_error("HTTP 429: Too Many Requests")
    assert is_rate_limit_error("status=429")
    assert is_infrastructure_error("HTTP 503 Service Unavailable")
    assert is_infrastructure_error("502 Bad Gateway")
    assert is_permanent_error("HTTP 404")
    assert is_permanent_error("401 Unauthorized")
