"""Öğretmen sorusunda ayrı zaman aşımı ve tek yeniden deneme (A4-31)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fusion_cli.core.events import StatusChanged
from fusion_cli.core.tools import ToolContext, ToolResult
from fusion_cli.engines.agent.teacher_flow import _ask


class _Publisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class _Kayit:
    """Sıradaki cevabı döndüren (ya da asılan) sahte `ask_teacher` kaydı."""

    def __init__(self, cevaplar: list[object]) -> None:
        self.cevaplar = list(cevaplar)
        self.cagri = 0

    async def execute(self, name, args, context):
        self.cagri += 1
        cevap = self.cevaplar.pop(0)
        if cevap == "asil":
            await asyncio.sleep(10)
        assert isinstance(cevap, ToolResult)
        return cevap


def _deps(tmp_path, *, teacher_timeout_s=0.05, request_timeout_s=600.0):
    return SimpleNamespace(
        config=SimpleNamespace(
            runtime=SimpleNamespace(
                request_timeout_s=request_timeout_s, teacher_timeout_s=teacher_timeout_s
            )
        ),
        tool_context=ToolContext(root=tmp_path),
        publisher=_Publisher(),
        teacher_unavailable_notified=False,
        teacher_lesson_sync_deferred=False,
    )


async def test_tek_gecici_hata_ogretmeni_kapatmaz(tmp_path):
    deps = _deps(tmp_path)
    kayit = _Kayit([ToolResult.failure("captcha"), ToolResult("plan")])

    cevap = await _ask(kayit, deps, question="q", durum="d")

    assert cevap == "plan"
    assert kayit.cagri == 2
    assert deps.teacher_unavailable_notified is False


async def test_iki_ardisik_hata_ogretmeni_kapatir(tmp_path):
    deps = _deps(tmp_path)
    kayit = _Kayit([ToolResult.failure("a"), ToolResult.failure("b")])

    assert await _ask(kayit, deps, question="q", durum="d") is None
    assert kayit.cagri == 2
    assert deps.teacher_unavailable_notified is True


async def test_zaman_asimi_ayri_teacher_timeout_ile_olculur(tmp_path):
    """Genel API zaman aşımı 600 sn iken öğretmen 0.05 sn'de düşer ve bir kez tekrarlanır."""
    deps = _deps(tmp_path)
    kayit = _Kayit(["asil", ToolResult("geç ama geldi")])

    cevap = await _ask(kayit, deps, question="q", durum="d")

    assert cevap == "geç ama geldi"
    assert deps.teacher_unavailable_notified is False
    mesajlar = [e.message for e in deps.publisher.events if isinstance(e, StatusChanged)]
    assert any("bir kez daha" in m for m in mesajlar)


async def test_iki_zaman_asimi_kapatir_ve_bir_kez_bildirir(tmp_path):
    deps = _deps(tmp_path)
    kayit = _Kayit(["asil", "asil"])

    assert await _ask(kayit, deps, question="q", durum="d") is None
    assert deps.teacher_unavailable_notified is True


async def test_reddedilen_soru_tekrarlanmaz_ve_kapatmaz(tmp_path):
    deps = _deps(tmp_path)
    kayit = _Kayit([ToolResult("reddetti", ok=False, structured={"teacher": "refused"})])

    assert await _ask(kayit, deps, question="q", durum="d") is None
    assert kayit.cagri == 1
    assert deps.teacher_unavailable_notified is False


async def test_web_oturum_hatasinda_ikinci_deneme_yapilmaz_ve_fazladan_mesaj_basilmaz(tmp_path):
    """Ölçüldü (30 Ekim): "bir kez daha deniyorum" sonrası çağrı sınırı hatası geliyordu."""
    deps = _deps(tmp_path)
    kayit = _Kayit(
        [
            ToolResult.failure(
                "Öğretmene ulaşılamadı: web oturumu hatası: tıklanamadı",
                structured={"teacher": "session_error"},
            ),
            ToolResult("hiç sorulmamalıydı"),
        ]
    )

    assert await _ask(kayit, deps, question="q", durum="d") is None

    assert kayit.cagri == 1
    assert deps.teacher_unavailable_notified is True
    mesajlar = [e.message for e in deps.publisher.events if isinstance(e, StatusChanged)]
    assert not any("bir kez daha" in m for m in mesajlar)
