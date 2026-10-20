"""Yeni sohbet açma hızı — sağlayıcının bot sınırına takılmamanın tek yolu.

Ölçüldü (13 Eylül, kullanıcı makinesi): araç ölçümü senaryo başına yeni sohbet
açtı, birkaç dakikada on dörde yakın sohbet isteği sağlayıcı tarafında bot
davranışı sayıldı ve konuşma oranı sınırı uygulandı; o günün kotası bitti. Sınır
UYGULANDIKTAN sonra yapacak bir şey yoktur; korunma onu hiç tetiklememektir.
"""

from __future__ import annotations

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.providers import web_browser
from fusion_cli.providers.web_browser import (
    NEW_CONVERSATION_BURST,
    NEW_CONVERSATION_INTERVAL_S,
    ConversationPacer,
)

OTURUM = WebSessionConfig(
    model="chatgpt_web/main/auto",
    provider="chatgpt_web",
    account="main",
    transport="browser",
)


def test_kova_dolu_baslar_normal_kosu_beklemez():
    """Bir agent koşusu birkaç kök açar (ana tur, ders, sıkıştırma); ceza olmaz."""
    # Saat ENJEKTE edilir: `bekleme_suresi` mutlak zaman değil geçen süreye bakar.
    pacer = ConversationPacer(updated_at=0.0)

    for _ in range(NEW_CONVERSATION_BURST):
        assert pacer.bekleme_suresi(now=0.0) == 0.0
        pacer.harca()


def test_kova_bosaldiktan_sonra_aralik_zorunlu():
    # Saat ENJEKTE edilir: `bekleme_suresi` mutlak zaman değil geçen süreye bakar.
    pacer = ConversationPacer(updated_at=0.0)
    for _ in range(NEW_CONVERSATION_BURST):
        pacer.bekleme_suresi(now=0.0)
        pacer.harca()

    bekleme = pacer.bekleme_suresi(now=0.0)

    assert bekleme == NEW_CONVERSATION_INTERVAL_S


def test_zaman_gectikce_hak_geri_gelir():
    # Saat ENJEKTE edilir: `bekleme_suresi` mutlak zaman değil geçen süreye bakar.
    pacer = ConversationPacer(updated_at=0.0)
    for _ in range(NEW_CONVERSATION_BURST):
        pacer.bekleme_suresi(now=0.0)
        pacer.harca()

    # Yarım aralık geçti: hakkın yarısı doldu, kalan süre yarısı kadar.
    assert pacer.bekleme_suresi(now=NEW_CONVERSATION_INTERVAL_S / 2) == (
        NEW_CONVERSATION_INTERVAL_S / 2
    )
    # Tam aralık dolunca beklemesiz geçer.
    assert pacer.bekleme_suresi(now=NEW_CONVERSATION_INTERVAL_S) == 0.0


def test_kova_kapasitesinin_uzerine_birikmez():
    """Uzun sessizlik, sınırsız patlama hakkı kazandırmaz."""
    # Saat ENJEKTE edilir: `bekleme_suresi` mutlak zaman değil geçen süreye bakar.
    pacer = ConversationPacer(updated_at=0.0)

    pacer.bekleme_suresi(now=NEW_CONVERSATION_INTERVAL_S * 100)

    assert pacer.tokens == float(NEW_CONVERSATION_BURST)


async def test_hesaplar_birbirinin_hakkini_yemez():
    havuz = web_browser.BrowserSessionPool()

    biri = havuz.pacer_for("chatgpt_web", "main")
    obur = havuz.pacer_for("chatgpt_web", "is")

    assert biri is not obur
    assert havuz.pacer_for("chatgpt_web", "main") is biri


async def test_ardisik_sohbet_acmalari_beklemeye_zorlanir():
    """Sonda gibi arka arkaya sohbet açan yol yavaşlar; süre gerçekten beklenir."""
    havuz = web_browser.BrowserSessionPool()
    beklenenler: list[float] = []

    async def _sahte_bekle(sure: float) -> None:
        beklenenler.append(sure)

    for _ in range(NEW_CONVERSATION_BURST):
        assert await web_browser._pace_new_conversation(havuz, OTURUM, sleep=_sahte_bekle) == 0.0

    bekleme = await web_browser._pace_new_conversation(havuz, OTURUM, sleep=_sahte_bekle)

    assert bekleme > 0
    assert beklenenler == [bekleme]
