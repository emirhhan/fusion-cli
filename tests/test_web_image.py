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
