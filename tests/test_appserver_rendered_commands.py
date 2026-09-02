"""Kendi çıktısını basan komutların masaüstünde de metin üretmesi.

Gerçek hata: `/tips`, `/help` gibi komutlar `RENDERED_COMMANDS` kümesindedir ve
çıktılarını TUI'de Rich ile basarlar; işleyicileri BOŞ dize döndürür. Masaüstü
yalnız işleyicinin dönüşünü gönderdiği için kullanıcı "komut çalıştırıldı"
görüyor ama ekranda hiçbir şey çıkmıyordu — sessiz başarı.
"""

from __future__ import annotations

import json

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


def _sonuc(satirlar, kimlik):
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(kimlik)


async def test_tips_komutu_metin_dondurur(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request("1", "komut.calistir", {"ad": "tips", "arguman": ""}))

    veri = _sonuc(satirlar, "1")
    assert veri["ok"] is True
    assert "/agent" in veri["metin"]
    assert "Fusion'ı verimli kullanmak" in veri["metin"]


async def test_help_komutu_komut_listesini_metin_olarak_dondurur(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request("2", "komut.calistir", {"ad": "help", "arguman": ""}))

    metin = _sonuc(satirlar, "2")["metin"]
    assert "/tips" in metin
    assert len(metin) > 200


async def test_ciktisini_basan_komutlar_sessizce_bos_donmez(tmp_path):
    """Kümeye yeni komut eklendiğinde de sessiz başarı üretilmemeli."""
    from fusion_cli.cli.repl.commands import RENDERED_COMMANDS

    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    for ad in sorted(RENDERED_COMMANDS):
        await oturum.handle(Request(ad, "komut.calistir", {"ad": ad, "arguman": ""}))
        veri = _sonuc(satirlar, ad)
        assert veri["ok"] is True, ad
        assert veri["metin"].strip(), f"{ad} sessizce boş döndü"


async def test_rich_bicimleme_isaretleri_metne_sizmaz(tmp_path):
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request("4", "komut.calistir", {"ad": "tips", "arguman": ""}))

    metin = _sonuc(satirlar, "4")["metin"]
    assert "[/" not in metin
    assert "\x1b[" not in metin


async def test_cok_uzun_cikti_kesilir_ve_kesildigi_soylenir(tmp_path):
    """Ölçüm: `/lessons` 86 KB üretebiliyor; arayüz bunu taşıyamaz."""
    from fusion_cli.core.constants import MAX_OUTPUT_CHARS
    from fusion_cli.ui import messages

    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request("5", "komut.calistir", {"ad": "lessons", "arguman": ""}))

    metin = _sonuc(satirlar, "5")["metin"]
    assert len(metin) <= MAX_OUTPUT_CHARS + len(messages.APP_COMMAND_TRUNCATED) + 2
    if len(metin) > MAX_OUTPUT_CHARS - 1000:
        assert messages.APP_COMMAND_TRUNCATED in metin
