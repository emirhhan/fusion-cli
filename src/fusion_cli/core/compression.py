"""Güvenli mesaj sıkıştırma — token kısar, İÇERİĞİ BOZMAZ.

OmniRoute'un agresif çok-motorlu sıkıştırmasının aksine bu KASITLI olarak tutucudur:
yalnızca satır sonu boşluklarını kırpar ve arka arkaya üç ve daha fazla boş satırı
tek boş satıra indirir. Kod girintisi (satır BAŞINDAKİ boşluk) ve içerik korunur —
bir kodlama asistanında agresif sıkıştırma kodu bozabileceği için sınır burada çizilir.

Saftır (stdlib) ve `core` sözleşmesine uyar.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace

from .types import Message

_MULTI_BLANK = re.compile(r"\n{3,}")
#: Çitli kod bloğu (kapanmamışsa metnin sonuna kadar): içi AYNEN korunur.
_FENCE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)


def _compress_prose(text: str) -> str:
    trimmed = "\n".join(line.rstrip() for line in text.split("\n"))
    return _MULTI_BLANK.sub("\n\n", trimmed)


def compress_text(text: str) -> str:
    """Satır sonu boşluklarını kırp, 3+ boş satırı 2'ye indir. Girinti/içerik korunur.

    Çitli kod blokları (```) DOKUNULMAZ: içlerindeki çok satırlı dizeler, sert satır
    sonları ve diff bağlamı değişirse model `old` dizesini birebir üretemez.
    Ölçüldü (30 Ekim): kod bloğundaki satır sonu boşluğu ve 3+ boş satır siliniyordu.
    """
    parcalar: list[str] = []
    konum = 0
    for blok in _FENCE.finditer(text):
        parcalar.append(_compress_prose(text[konum : blok.start()]))
        parcalar.append(blok.group())
        konum = blok.end()
    parcalar.append(_compress_prose(text[konum:]))
    return "".join(parcalar)


def compress_messages(messages: Sequence[Message]) -> tuple[Message, ...]:
    """Her mesajın içeriğini güvenli biçimde sıkıştır (yeni demet döner).

    Araç (`tool`) mesajlarına dokunulmaz: dosya içeriği/komut çıktısı taşırlar ve
    `edit_file`'ın "birebir eşleşme" sözleşmesi bozulmamalı.
    """
    return tuple(
        message
        if message.role == "tool"
        else replace(message, content=compress_text(message.content))
        for message in messages
    )


def saved_chars(before: Sequence[Message], after: Sequence[Message]) -> int:
    """Sıkıştırmanın kazandırdığı karakter sayısı (negatif olmaz)."""
    delta = sum(len(m.content) for m in before) - sum(len(m.content) for m in after)
    return max(0, delta)
