"""Model hata etiketleri, ham hata maskeleme, canlılık yoklaması (A2-16, A2-24, A2-25)."""

from __future__ import annotations

import pytest

from fusion_cli.core.types import ModelResult, ModelSpec
from fusion_cli.engines.agent import liveness
from fusion_cli.engines.agent.loop import _model_failure_message, _short_reason


@pytest.mark.parametrize(
    "metin", ["context length 50000 aşıldı", "limit 1500 token", "port 5001 kapalı", "id 15003"]
)
def test_sayi_icindeki_500_sunucu_hatasi_sayilmaz(metin):
    assert _short_reason(metin) == "yanıt veremedi"


@pytest.mark.parametrize(
    "metin", ["HTTP 503 Service Unavailable", "error code: 500", "529 overload"]
)
def test_gercek_durum_kodu_sunucu_hatasidir(metin):
    assert _short_reason(metin) == "sunucu hatası verdi"


def test_taninmayan_hatadaki_sir_kullaniciya_yazilmaz():
    sir = "sk-" + "a1b2c3d4e5f6g7h8i9j0k1l2"

    mesaj = _model_failure_message(f"Bad request base_url=http://x key={sir}")

    assert sir not in mesaj and "Model yanıt veremedi" in mesaj


@pytest.mark.parametrize("onek", ["llama_cpp", "llamacpp"])
def test_tek_yuvali_yerel_sunucular_yoklanmaz(onek):
    assert not liveness.is_api_model(ModelSpec(name="m", model=f"{onek}/qwen"))


def test_bulut_modeli_yoklanir():
    assert liveness.is_api_model(ModelSpec(name="m", model="openai/gpt-x"))


async def test_hiz_siniri_yanitiyla_yoklama_sunucuyu_olu_saymaz(monkeypatch):
    class _Saglayici:
        async def stream(self, request):
            from fusion_cli.core.types import StreamDone

            yield StreamDone(
                ModelResult(
                    name="m",
                    model="m",
                    text="",
                    latency_ms=1,
                    ok=False,
                    error="RateLimitError 429 too many requests",
                )
            )

    monkeypatch.setattr(liveness, "build_provider", lambda *a, **k: _Saglayici())

    assert await liveness.ping_for(ModelSpec(name="m", model="openai/x"))() is None
