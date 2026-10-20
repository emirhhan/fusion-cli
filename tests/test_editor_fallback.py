"""Mesaj kutusuna yazma, YÖNTEMİN başarısına değil SONUCA bakmalı.

Ölçüldü (11 Eylül, chatgpt_web/main, gerçek oturum): Cloudflare geçildikten sonra
tur `mesaj kutusu metni kırptı: 1483 karakter yazıldı, 0 karakter yerleşti` ile
düştü. Sebep: ChatGPT'nin Lexical editöründe `locator.fill()` HATA FIRLATMADAN
başarısız oluyor. Kod `fill` istisna atmadığı için "yazıldı" sayıyor, yedek
yolları (yazma, yapıştırma) hiç denemiyor ve turu düşürüyordu.

Doğru ölçüt tek: kutuda metin var mı? Yöntem sırayla denenir, her denemeden sonra
GERİ OKUNUR.
"""

from __future__ import annotations

import pytest

from fusion_cli.providers.web_browser import WebBrowserError, _fill_editor


class _LexicalEditor:
    """`fill()` sessizce hiçbir şey yapmaz; yalnız `insert_text()` çalışır."""

    def __init__(self) -> None:
        self.icerik = ""
        self.cagrilar: list[str] = []

    async def fill(self, text: str) -> None:
        self.cagrilar.append("fill")  # sessizce yutar

    async def click(self) -> None:
        self.cagrilar.append("click")

    async def press(self, key: str) -> None:
        self.cagrilar.append(f"press:{key}")

    async def insert_text(self, text: str) -> None:
        self.cagrilar.append("insert_text")
        self.icerik = text

    async def evaluate(self, script: str, *args: object) -> str:
        return self.icerik


class _OlmeyenEditor(_LexicalEditor):
    """Hiçbir yöntem işe yaramaz: tur sessizce sürdürülmemeli."""

    async def insert_text(self, text: str) -> None:
        self.cagrilar.append("insert_text")


async def test_fill_sessizce_basarisizsa_yazma_yolu_denenir():
    editor = _LexicalEditor()

    await _fill_editor(editor, "Fusion görev metni")

    assert editor.icerik == "Fusion görev metni"
    assert "fill" in editor.cagrilar and "insert_text" in editor.cagrilar


async def test_hicbir_yol_tutmazsa_gorunur_hata_verilir():
    editor = _OlmeyenEditor()

    with pytest.raises(WebBrowserError, match="yerleşti"):
        await _fill_editor(editor, "Fusion görev metni")


async def test_fill_calisiyorsa_fazladan_yol_denenmez():
    """Çalışan sağlayıcılarda davranış değişmemeli."""

    class _Calisan(_LexicalEditor):
        async def fill(self, text: str) -> None:
            self.cagrilar.append("fill")
            self.icerik = text

    editor = _Calisan()
    await _fill_editor(editor, "metin")

    assert editor.cagrilar == ["fill"]
