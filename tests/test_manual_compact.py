"""Elle `/compact [talimat]` eşikten bağımsız özetler, talimat özet istemine girer (#186)."""

from __future__ import annotations

from fusion_cli.core.types import Message
from fusion_cli.engines.agent import compaction


def _kisa_konusma() -> list[Message]:
    return [
        Message("system", "sistem"),
        Message("user", "oyun yaz"),
        Message("assistant", "yazdım"),
        Message("user", "testleri ekle"),
        Message("assistant", "ekledim"),
    ]


async def test_elle_compact_esik_altinda_da_ozetler_ve_odagi_iletir(monkeypatch):
    istemler: list[str] = []

    async def _ozet(trace, config, publisher, *, focus=""):
        istemler.append(compaction.summary_prompt(trace, focus))
        return "özet"

    monkeypatch.setattr(compaction, "_summarize", _ozet)

    sonuc = await compaction.compress(
        _kisa_konusma(), config=None, manual=True, focus="test kararlarına odaklan"
    )

    # Kök tur ve ara kullanıcı düzeltmesi birebir kalır; eski asistan açıklaması özetlenir.
    assert [m.content for m in sonuc[:3]] == ["sistem", "oyun yaz", "yazdım"]
    assert "özet" in sonuc[3].content and sonuc[3].harness_note
    assert sonuc[4:] == [Message("user", "testleri ekle")]
    assert compaction.FOCUS_HEADER in istemler[0]
    assert "test kararlarına odaklan" in istemler[0]


async def test_otomatik_sikistirma_esik_altinda_dokunmaz(monkeypatch):
    async def _ozet(*_args, **_kwargs):
        raise AssertionError("eşik altında özet istenmemeli")

    monkeypatch.setattr(compaction, "_summarize", _ozet)
    mesajlar = _kisa_konusma()

    assert await compaction.compress(mesajlar, config=None) is mesajlar


def test_odaksiz_istem_degismez():
    assert compaction.summary_prompt("iz") == compaction.summary_prompt("iz", "  ")
    assert compaction.FOCUS_HEADER not in compaction.summary_prompt("iz")
