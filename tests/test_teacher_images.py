"""Öğretmen "göz": görseller Gemini web'e eklenir, ask_teacher yolları doğrular."""

from __future__ import annotations

import base64

from fusion_cli.core.tools import ToolContext, ToolResult
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.engine_tools import MAX_TEACHER_IMAGES, _teacher_images
from fusion_cli.providers.web_browser import MAX_WEB_IMAGES, _data_uri_bytes, pending_images

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nveri").decode()


def test_data_uri_cozulur_bilinmeyen_tur_reddedilir():
    assert _data_uri_bytes(f"data:image/png;base64,{PNG}") == (b"\x89PNG\r\n\x1a\nveri", ".png")
    assert _data_uri_bytes("data:image/gif;base64,AAAA") is None
    assert _data_uri_bytes("data:image/png;base64,***") is None


def test_gonderilecek_gorseller_en_yenileri_ve_sinirli():
    mesajlar = [Message("user", "a", images=tuple(f"g{i}" for i in range(6)))]
    assert pending_images(mesajlar) == tuple(f"g{i}" for i in range(6 - MAX_WEB_IMAGES, 6))
    assert pending_images([Message("user", "metin")]) == ()


def test_ogretmen_gorsel_yollari_data_uri_olur(tmp_path):
    (tmp_path / "onizleme.png").write_bytes(b"\x89PNG\r\n\x1a\nveri")
    context = ToolContext(root=tmp_path)

    sonuc = _teacher_images(["onizleme.png"], context)

    assert isinstance(sonuc, tuple) and sonuc[0].startswith("data:image/png;base64,")
    assert _teacher_images(None, context) == ()


def test_ogretmen_gorsellerinde_gecersiz_girdi_aciklayici_hata(tmp_path):
    context = ToolContext(root=tmp_path)
    (tmp_path / "not.txt").write_text("x", encoding="utf-8")

    for girdi in (["yok.png"], ["not.txt"], "tek.png", ["a.png"] * (MAX_TEACHER_IMAGES + 1)):
        sonuc = _teacher_images(girdi, context)
        assert isinstance(sonuc, ToolResult) and not sonuc.ok
