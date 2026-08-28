"""Olay ve soru köprüleri."""

from __future__ import annotations

import asyncio
import json

from fusion_cli.appserver.bridges import PendingQuestions, ProtocolPrompter, ProtocolSink
from fusion_cli.core.events import TurnOutcome
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalRequest


class _Tool:
    name = "write_file"


def _request(danger: str | None = None, args: dict[str, object] | None = None) -> ApprovalRequest:
    return ApprovalRequest(tool=_Tool(), args=args or {"path": "a.txt"}, danger=danger)


def test_olay_satir_olarak_yazilir() -> None:
    satirlar: list[str] = []

    ProtocolSink(satirlar.append).handle(TurnOutcome(status="completed", elapsed_s=1.0))

    yuk = json.loads(satirlar[0])
    assert yuk["tip"] == "olay"
    assert yuk["veri"]["olay"] == "TurnOutcome"
    assert yuk["veri"]["status"] == "completed"


async def test_onay_sorusu_cevapla_eslesir() -> None:
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)

    soru = json.loads(satirlar[0])
    assert soru["tip"] == "soru"
    assert soru["veri"]["tur"] == "onay"
    assert pending.resolve(soru["id"], {"secim": "once"}) is True

    assert await gorev is ApprovalAnswer.ONCE


async def test_yikici_istekte_oturum_secenegi_gonderilmez() -> None:
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request(danger="dosya siler")))
    await asyncio.sleep(0)

    secenekler = json.loads(satirlar[0])["veri"]["secenekler"]
    assert "session" not in [seçenek["deger"] for seçenek in secenekler]

    pending.resolve(json.loads(satirlar[0])["id"], {"secim": "deny"})
    await gorev


async def test_soru_serbest_metin_doner() -> None:
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.ask("hangi dil?"))
    await asyncio.sleep(0)
    pending.resolve(json.loads(satirlar[0])["id"], {"metin": "python"})

    assert await gorev == "python"


async def test_cevapsiz_kapanista_onay_reddedilir() -> None:
    """Uygulama cevap vermeden kapanırsa tur güvenli biçimde bitmeli."""
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(prompter.confirm(_request()))
    await asyncio.sleep(0)
    pending.cancel_all()

    assert await gorev is ApprovalAnswer.DENY


def test_eslesmeyen_kimlik_yok_sayilir() -> None:
    assert PendingQuestions().resolve("olmayan", {"secim": "once"}) is False


async def test_onay_yukunde_gizli_arguman_degeri_yoktur() -> None:
    """Onay teli, araç argümanlarının değerini hiçbir koşulda taşımaz."""
    sentinel = "gizli-deger-bu-telde-asla-gorunmemeli"
    satirlar: list[str] = []
    pending = PendingQuestions()
    prompter = ProtocolPrompter(satirlar.append, pending)

    gorev = asyncio.ensure_future(
        prompter.confirm(_request(args={"zeta": sentinel, "alpha": {"token": sentinel}}))
    )
    await asyncio.sleep(0)

    assert sentinel not in satirlar[0]
    yuk = json.loads(satirlar[0])
    assert yuk["veri"]["argumanlar"] == ["alpha", "zeta"]

    pending.resolve(yuk["id"], {"secim": "deny"})
    await gorev
