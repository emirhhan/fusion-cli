"""Tarayıcıya giden prompt, mesaj kutusunun aldığından uzun olamaz.

Ölçüldü (deney, model çağrısı olmadan): Gemini composer'ına artan boylarda metin
yazılıp DOM'dan geri okundu. 32.000 karakter tam yerleşiyor; 33.000, 40.000 ve
50.864 isteklerinin ÜÇÜ de birebir aynı tavana düşüyor — 32.316 karakter. 12
saniye beklendiğinde de sonuç değişmiyor, yani bu bir işleme yarışı değil SERT
BİR TAVAN; parçalı yazmak da kurtarmaz.

Canlı koşuda 50.864 karakterlik prompt gönderildi, 18.548 karakteri hiç ulaşmadı
ve kaybolan kuyrukta kullanıcının GÖREV metni vardı. Model üç tur boyunca "somut
bir görev almadım" dedi.

Kesme ORTADAN yapılır: başta araç sözleşmesi, sonda görev vardır ve ikisi de
kritiktir. "Lost in the middle" bulgusu da aynı yeri işaret eder — uzun bağlamda
en az bakılan bölge ortadır.
"""

from __future__ import annotations

from fusion_cli.core.types import Message
from fusion_cli.providers.web_browser import (
    MAX_WEB_PROMPT_CHARS,
    format_browser_prompt,
    trim_to_prompt_budget,
)


def test_butce_altindaki_prompt_dokunulmadan_gecer() -> None:
    metin = "kısa prompt"

    assert trim_to_prompt_budget(metin) == metin


def test_butce_asilinca_metin_kisalir() -> None:
    metin = "x" * (MAX_WEB_PROMPT_CHARS + 20_000)

    kirpik = trim_to_prompt_budget(metin)

    assert len(kirpik) <= MAX_WEB_PROMPT_CHARS


def test_bas_ve_son_korunur_orta_atilir() -> None:
    """Görev sondadır ve ASLA kaybolmamalıdır — ölçülen hatanın tamamı budur."""
    bas = "SÖZLEŞME-BASI"
    son = "GÖREV: sidebar hatasını düzelt"
    metin = bas + ("d" * (MAX_WEB_PROMPT_CHARS * 2)) + son

    kirpik = trim_to_prompt_budget(metin)

    assert kirpik.startswith(bas)
    assert kirpik.endswith(son)
    assert len(kirpik) <= MAX_WEB_PROMPT_CHARS


def test_kirpma_gorunur_isaret_birakir() -> None:
    """Sessiz kırpma, ölçülen hatanın ta kendisiydi; model ne kaybettiğini BİLMELİ."""
    metin = "b" * (MAX_WEB_PROMPT_CHARS + 5_000)

    kirpik = trim_to_prompt_budget(metin)

    assert "KIRPILDI" in kirpik


def test_gercek_prompt_butceyi_asmaz() -> None:
    """`format_browser_prompt` çıktısı doğrudan mesaj kutusuna gider."""
    dev_icerik = "y" * 80_000
    mesajlar = [
        Message("system", "sistem talimatı"),
        Message("user", "asıl görev: hatayı düzelt"),
        Message("tool", dev_icerik),
    ]

    prompt = format_browser_prompt(mesajlar)

    assert len(prompt) <= MAX_WEB_PROMPT_CHARS
    # Görev hatırlatması promptun sonundadır ve kırpmadan SAĞ ÇIKMALIDIR.
    assert "asıl görev: hatayı düzelt" in prompt[-2_000:]
