"""Mesaj kutusuna yazılan metnin GERÇEKTEN yerleştiği doğrulanır.

Ölçüldü (10 Ağustos 2026, Pro kademesi): fusion 50.864 karakterlik bir prompt
gönderdi, modele yalnızca bir öneki ulaştı. Model "mesajınızın sonundaki metin
kesilmiş görünüyor" dedi, üç tur boyunca "somut bir görev almadım" diye döndü ve
koşu hiçbir dosyayı değiştirmeden düştü.

Sınır ayrı bir deneyle ölçüldü (model çağrısı olmadan, Gemini composer'ına artan
boylarda yazıp DOM'dan geri okuyarak): 32.000 karakter tam yerleşiyor, 33.000 ve
üzeri isteklerin HEPSİ aynı tavana düşüyor — 32.316 karakter.

Zararı iki katmanlı: kesilme sessizdi ÇÜNKÜ `_fill_editor` yazdığını geri
okumuyordu, ve iz dosyası da yakalayamıyordu çünkü `gonderilen` alanına fusion'ın
göndermek İSTEDİĞİ metin yazılıyor, editöre ULAŞAN değil. Yani teşhis eldeki
kayıtlarla imkânsızdı.
"""

from __future__ import annotations

import pytest

from fusion_cli.providers.web_browser import WebBrowserError, _fill_editor


class SahteEditor:
    """Belirtilen karakterden sonrasını sessizce kırpan mesaj kutusu."""

    def __init__(self, *, cap: int | None = None) -> None:
        self.cap = cap
        self.icerik = ""
        self.fill_cagrisi = 0

    async def fill(self, text: str) -> None:
        self.fill_cagrisi += 1
        yeni = text if self.cap is None else text[: self.cap]
        # `fill` alanı sıfırlayıp yeniden yazar; parçalı yazımda bu KAYBA yol açar,
        # bu yüzden üretim kodunun ekleme yapması beklenir (bkz. `insert_text`).
        self.icerik = yeni

    async def insert_text(self, text: str) -> None:
        kalan = text if self.cap is None else text[: max(0, self.cap - len(self.icerik))]
        self.icerik += kalan

    async def click(self) -> None:
        return None

    async def press(self, tus: str) -> None:
        if tus == "Backspace":
            self.icerik = ""

    async def evaluate(self, _script: str) -> str:
        return self.icerik


async def test_kisa_metin_oldugu_gibi_yerlesir() -> None:
    editor = SahteEditor()

    await _fill_editor(editor, "kısa görev")

    assert editor.icerik == "kısa görev"


async def test_kirpilan_metin_sessizce_gecmez() -> None:
    """Ölçülen asıl hata: 18.548 karakter düştü ve hiçbir yerde iz bırakmadı.

    Kırpılmış bir promptun sonunda görev metni yoktur; o promptla devam etmek
    modele "görevini söylemeden iş iste" demektir. Hata fırlatmak, sessizce
    yanlış iş yapmaktan iyidir.
    """
    editor = SahteEditor(cap=1_000)

    with pytest.raises(WebBrowserError) as hata:
        await _fill_editor(editor, "g" * 5_000)

    # Hata mesajı teşhisi TAŞIMALI: kaç karakter istendi, kaçı ulaştı.
    assert "5000" in str(hata.value)
    assert "1000" in str(hata.value)


async def test_dogrulama_gercek_uzunluga_bakar() -> None:
    """Tavana tam oturan metin geçerlidir; kenar durumu hata sayılmamalı."""
    editor = SahteEditor(cap=2_000)

    await _fill_editor(editor, "g" * 2_000)

    assert len(editor.icerik) == 2_000
