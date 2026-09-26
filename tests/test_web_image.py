"""Web görsel üretiminin saf parçaları; tarayıcı akışı canlı ölçülür."""

from __future__ import annotations

import base64
from datetime import datetime

from fusion_cli.providers.web_image import image_prompt, save_images

_PNG_1X1 = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
    )
).decode()


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
