"""Eklenen görsel gerçekten modele gider mi?

Kullanıcı görsel ekliyor ama modele yalnız dosya YOLU metin olarak gidiyordu;
görebilen bir model bile resmi hiç görmüyordu. Görsel ekler artık kullanıcı
mesajına iliştirilir.
"""

from __future__ import annotations

import base64

from fusion_cli.appserver.session import _attachment_context, _attachment_images
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.loop import _initial_messages

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_gorsel_ek_veri_uri_olarak_taşinir(tmp_path):
    gorsel = tmp_path / "ekran.png"
    gorsel.write_bytes(TINY_PNG)

    images = _attachment_images([{"path": str(gorsel), "name": "ekran.png", "kind": "image"}])

    assert len(images) == 1
    assert images[0].startswith("data:image/png;base64,")


def test_gorsel_olmayan_ek_gorsel_olarak_gitmez(tmp_path):
    belge = tmp_path / "not.txt"
    belge.write_text("merhaba", encoding="utf-8")

    assert _attachment_images([{"path": str(belge), "name": "not.txt", "kind": "file"}]) == ()


def test_olmayan_dosya_cokertmez(tmp_path):
    assert _attachment_images([{"path": str(tmp_path / "yok.png"), "kind": "image"}]) == ()


def test_asiri_buyuk_gorsel_gonderilmez(tmp_path):
    """Büyük bir görsel isteği şişirir ve çoğu uçta reddedilir."""
    from fusion_cli.appserver.session import MAX_GORSEL_BAYT

    buyuk = tmp_path / "buyuk.png"
    buyuk.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_GORSEL_BAYT + 1))

    assert _attachment_images([{"path": str(buyuk), "kind": "image"}]) == ()


def test_gorseller_kullanici_mesajina_ilistirilir():
    mesajlar = _initial_messages(
        "bu ekranı incele",
        None,
        plan_mode=False,
        extra_system="",
        images=("data:image/png;base64,AAA",),
    )

    kullanici = [mesaj for mesaj in mesajlar if mesaj.role == "user"]
    assert kullanici[-1].images == ("data:image/png;base64,AAA",)


def test_gorselsiz_turda_mesaj_gorsel_tasimaz():
    mesajlar = _initial_messages("merhaba", None, plan_mode=False, extra_system="")

    assert all(mesaj.images == () for mesaj in mesajlar)


def test_ek_metni_hala_yol_bilgisini_tasir(tmp_path):
    """Görsel iliştirilse bile yol bağlamı kalır: model dosyayı ayrıca okuyabilir."""
    gorsel = tmp_path / "ekran.png"
    gorsel.write_bytes(TINY_PNG)

    metin, hata = _attachment_context([{"path": str(gorsel), "name": "ekran.png", "kind": "image"}])

    assert hata is None
    assert "ekran.png" in metin


def test_mesaj_tipi_gorsel_alanini_zaten_destekler():
    assert Message("user", "x", images=("data:image/png;base64,AAA",)).images
