"""Web görsel üretiminin saf parçaları; tarayıcı akışı canlı ölçülür."""

from __future__ import annotations

import base64
from datetime import datetime

from fusion_cli.providers.web_image import image_prompt, save_images
from tests.image_fixture import image_bytes

_PNG_1X1 = base64.b64encode(image_bytes("PNG")).decode()


def test_istem_gorsel_niyetini_acikca_soyler():
    assert image_prompt("kırmızı kask") == "Bir görsel oluştur: kırmızı kask"
    assert image_prompt("Bir görsel oluştur: mavi eldiven") == "Bir görsel oluştur: mavi eldiven"


def test_png_kayitlari_dosyaya_yazilir_png_olmayan_atlanir(tmp_path):
    zaman = datetime(2026, 9, 26, 22, 0, 0)
    kayitlar = save_images(
        [{"b64": _PNG_1X1, "w": 1, "h": 1}, {"b64": base64.b64encode(b"degil").decode()}],
        tmp_path,
        now=zaman,
    )

    assert [k.path.name for k in kayitlar] == ["fusion-20260926-220000-1.png"]
    assert kayitlar[0].path.read_bytes().startswith(b"\x89PNG")


async def test_gorsel_dogrulama_ve_disk_yazimi_olay_dongusunu_tutmaz(tmp_path, monkeypatch):
    import threading

    from fusion_cli.providers import web_image

    main_thread = threading.get_ident()
    writer_threads = []
    original_save = web_image.save_images

    def recorded_save(payloads, directory):
        writer_threads.append(threading.get_ident())
        return original_save(payloads, directory)

    class Page:
        async def evaluate(self, script, _arguments):
            if script == web_image._FIND_IMAGES_JS:
                return [{"src": "blob:sentetik"}]
            return [{"b64": _PNG_1X1}]

    monkeypatch.setattr(web_image, "save_images", recorded_save)
    monkeypatch.setattr(web_image, "_POLL_S", 0)
    monkeypatch.setattr(web_image, "IMAGE_SETTLE_S", 0)
    images = await web_image._wait_and_extract(Page(), None, ("img",), tmp_path, 2)
    assert len(images) == 1
    assert writer_threads and main_thread not in writer_threads


RED_CUMLESI = (
    "Bu talebi yerine getiremiyorum. Cinsel içerik barındıran veya bu tür ögeleri "
    "tasvir eden görseller oluşturamıyorum."
)
GEMINI_SAYFASI = "\n".join(
    [
        "Yeni sohbet",
        "Geçmiş sohbet başlığı",
        "Bir görsel oluştur: casio saatinin içerisinde bir maymun videosu "
        "izleyen bir kuş görseli üret",
        "Gemini şunu dedi:",
        RED_CUMLESI,
        "Flash",
        "Gemini bir yapay zeka modeli olduğu için hata yapabilir.",
        "Hatayı bildir",
        "Yeniden dene",
    ]
)


def test_red_cumlesi_yalniz_kendisi_cikarilir():
    from fusion_cli.providers.web_image import refusal_text

    istem = (
        "Bir görsel oluştur: casio saatinin içerisinde bir maymun videosu "
        "izleyen bir kuş görseli üret"
    )
    metin = refusal_text(GEMINI_SAYFASI, istem)
    assert metin == RED_CUMLESI
    for gurultu in ("Flash", "Hatayı bildir", "Yeniden dene", "Gemini", "casio"):
        assert gurultu not in metin


def test_red_yoksa_bos_ve_istem_yansimasi_red_sayilmaz():
    from fusion_cli.providers.web_image import refusal_text

    assert refusal_text("Yeni sohbet\nİşte görselin:\nFlash", "kedi") == ""
    # İstemin kendisi "oluşturamıyorum" gibi bir kalıp içerse de kullanıcının metni red sayılmaz.
    assert (
        refusal_text(
            "Bir görsel oluştur: neden oluşturamıyorum diye sor",
            "Bir görsel oluştur: neden oluşturamıyorum diye sor",
        )
        == ""
    )
    assert (
        refusal_text("I can't help with that request.\nFlash", "x")
        == "I can't help with that request."
    )


async def test_red_gelince_180_saniye_beklemeden_hemen_hata_verir(tmp_path, monkeypatch):
    import time

    import pytest

    from fusion_cli.providers import web_image
    from fusion_cli.providers.web_browser import WebBrowserError

    class Page:
        async def evaluate(self, script, _arguments):
            return []

        async def inner_text(self, _selector):
            return GEMINI_SAYFASI

    monkeypatch.setattr(web_image, "_POLL_S", 0)
    baslangic = time.monotonic()
    with pytest.raises(WebBrowserError) as hata:
        await web_image._wait_and_extract(Page(), None, ("img",), tmp_path, 180, prompt="kedi")
    assert time.monotonic() - baslangic < 2
    assert str(hata.value).startswith("Bu talebi yerine getiremiyorum.")
    assert "Flash" not in str(hata.value) and "sn içinde" not in str(hata.value)


async def test_zaman_asiminda_sayfa_metni_dokulmez(tmp_path, monkeypatch):
    import pytest

    from fusion_cli.providers import web_image
    from fusion_cli.providers.web_browser import WebBrowserError

    class Definition:
        name = "Gemini Web"

    class Page:
        async def evaluate(self, script, _arguments):
            return []

        async def inner_text(self, _selector):
            return "Yeni sohbet\nDüşünüyor…\nFlash"

    async def no_block(_page, _definition):
        return None

    monkeypatch.setattr(web_image, "_POLL_S", 0.01)
    monkeypatch.setattr(web_image, "_raise_if_blocked_early", no_block)
    with pytest.raises(WebBrowserError) as hata:
        await web_image._wait_and_extract(
            Page(), Definition(), ("img",), tmp_path, 0.05, prompt="kedi"
        )
    assert str(hata.value) == "Gemini Web görseli 0 sn içinde üretemedi."
