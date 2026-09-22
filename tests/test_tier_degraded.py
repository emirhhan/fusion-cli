"""Kademe düşme bildirimi (Faz 4, Görev 4) — saf fonksiyon + olay + render."""

from __future__ import annotations

import io

from rich.console import Console

from fusion_cli.core.events import ModelCallFinished, TierDegraded, TurnFinished
from fusion_cli.core.tier import expected_tier, tier_mismatch
from fusion_cli.core.types import ModelResult
from fusion_cli.providers.eventing import EventingProvider
from fusion_cli.ui import messages
from fusion_cli.ui.renderer import ConsoleRenderer

# --- core.tier: saf fonksiyonlar ------------------------------------------- #


def test_auto_kademede_beklenti_yoktur():
    assert expected_tier("gemini_web/main/auto") == ""


def test_kisa_model_kimliginde_beklenti_yoktur():
    assert expected_tier("nvidia_nim/nvidia/nemotron-3-super-120b-a12b") == ""


def test_acikca_secilen_kademe_beklenti_olur():
    assert expected_tier("gemini_web/main/pro") == "pro"


def test_beklenti_yoksa_uyusmazlik_bildirilmez():
    assert tier_mismatch("gemini_web/main/auto", "Flash-Lite") == ""


def test_gozlenen_bossa_uyusmazlik_bildirilmez():
    """Kademe bilinmiyorsa 'istenen gelmedi' denemez — belirsizlik hata sayılmaz."""
    assert tier_mismatch("gemini_web/main/pro", "") == ""


def test_beklenen_gozlende_geciyorsa_uyusmazlik_yok():
    assert tier_mismatch("gemini_web/main/pro", "Gemini 3 Pro") == ""


def test_beklenen_gozlende_gecmiyorsa_uyusmazlik_bildirilir():
    assert tier_mismatch("gemini_web/main/pro", "Flash-Lite") == "pro"


def test_karsilastirma_buyuk_kucuk_harf_duyarsizdir():
    assert tier_mismatch("gemini_web/main/PRO", "gemini 3 pro") == ""


# --- EventingProvider: olay yayınlama --------------------------------------- #


class _Publisher:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)


class _SahteSaglayici:
    def __init__(self, result):
        self._result = result

    @property
    def label(self):
        return self._result.model

    async def complete(self, request):
        return self._result


async def test_uyusmazlik_varsa_tier_degraded_yayinlanir():
    result = ModelResult(
        name="ogretmen", model="gemini_web/main/pro", text="c", latency_ms=1, ok=True,
        served_by="Flash-Lite",
    )
    publisher = _Publisher()
    provider = EventingProvider(_SahteSaglayici(result), publisher=publisher, role="ogretmen")

    await provider.complete(request=None)

    olaylar = [e for e in publisher.events if isinstance(e, TierDegraded)]
    assert len(olaylar) == 1
    assert olaylar[0].expected_tier == "pro"
    assert olaylar[0].served_by == "Flash-Lite"


async def test_auto_kademede_tier_degraded_yayinlanmaz():
    result = ModelResult(
        name="ogretmen", model="gemini_web/main/auto", text="c", latency_ms=1, ok=True,
        served_by="Flash-Lite",
    )
    publisher = _Publisher()
    provider = EventingProvider(_SahteSaglayici(result), publisher=publisher, role="ogretmen")

    await provider.complete(request=None)

    assert not any(isinstance(e, TierDegraded) for e in publisher.events)


async def test_uyusma_varsa_tier_degraded_yayinlanmaz():
    result = ModelResult(
        name="ogretmen", model="gemini_web/main/pro", text="c", latency_ms=1, ok=True,
        served_by="Gemini 3 Pro",
    )
    publisher = _Publisher()
    provider = EventingProvider(_SahteSaglayici(result), publisher=publisher, role="ogretmen")

    await provider.complete(request=None)

    assert not any(isinstance(e, TierDegraded) for e in publisher.events)


async def test_model_call_finished_yine_yayinlanir():
    """Yeni olay ESKİ olayın yerini almaz, YANINA eklenir."""
    result = ModelResult(
        name="ogretmen", model="gemini_web/main/pro", text="c", latency_ms=1, ok=True,
        served_by="Flash-Lite",
    )
    publisher = _Publisher()
    provider = EventingProvider(_SahteSaglayici(result), publisher=publisher, role="ogretmen")

    await provider.complete(request=None)

    assert any(isinstance(e, ModelCallFinished) for e in publisher.events)


# --- Renderer: görünür bildirim --------------------------------------------- #


def _renderer():
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    return ConsoleRenderer(console), buffer


def test_tier_degraded_gorunur_bir_satir_basar():
    renderer, buffer = _renderer()

    renderer.handle(
        TierDegraded(model="gemini_web/main/pro", expected_tier="pro", served_by="Flash-Lite")
    )
    renderer.handle(TurnFinished())  # bekleyen durum satırını boşaltır

    cikti = buffer.getvalue()
    assert "pro" in cikti
    assert "Flash-Lite" in cikti


def test_tier_degraded_mesaj_bicimi():
    metin = messages.TIER_DEGRADED.format(expected="pro", served="Flash-Lite", model="gemini_web")
    assert "pro" in metin
    assert "Flash-Lite" in metin
