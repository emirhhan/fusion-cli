"""Maliyet özet satırı: ölçülmemiş sıfır "0 token · $0.0000" diye gösterilmez (30 Ekim)."""

from __future__ import annotations

from fusion_cli.core.events import ModelCallFinished
from fusion_cli.core.types import ModelResult, TokenUsage
from fusion_cli.observability.cost import CostTracker
from fusion_cli.ui.tables import cost_summary


def _tracker(*usages: TokenUsage) -> CostTracker:
    izleyici = CostTracker()
    for sira, kullanim in enumerate(usages):
        sonuc = ModelResult(name="m", model="x/y", text="t", latency_ms=1, ok=True, usage=kullanim)
        izleyici.handle(ModelCallFinished(role="ana", result=sonuc, call_id=str(sira)))
    return izleyici


def test_olculmeyen_web_kullanimi_sifir_diye_yazilmaz():
    satir = cost_summary(_tracker(TokenUsage(), TokenUsage(), TokenUsage(), TokenUsage()))

    assert satir == "toplam: 4 çağrı · token bilinmiyor · maliyet bilinmiyor"
    assert "$0.0000" not in satir


def test_olculen_kullanim_ve_maliyet_aynen_gosterilir():
    olculen = TokenUsage(
        prompt_tokens=1000,
        completion_tokens=234,
        cost_usd=0.0123,
        prompt_measured=True,
        completion_measured=True,
        cost_known=True,
    )

    assert cost_summary(_tracker(olculen)) == "toplam: 1 çağrı · 1,234 token · $0.0123"


def test_olculen_ama_fiyati_bilinmeyen_model_maliyeti_bilinmiyor_der():
    olculen = TokenUsage(
        prompt_tokens=20_000,
        completion_tokens=2_197,
        prompt_measured=True,
        completion_measured=True,
    )

    satir = cost_summary(_tracker(olculen))

    assert satir == "toplam: 1 çağrı · 22,197 token · maliyet bilinmiyor"


def test_cagri_yokken_eski_bicim_korunur():
    assert cost_summary(CostTracker()) == "toplam: 0 çağrı · 0 token · $0.0000"
