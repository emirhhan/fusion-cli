"""Kullanıcıya görünmemesi gereken çerçeve metinlerini ayıkla.

Harness'ın modele yazdığı notlar (`[eylem-kanıtı-zorunlu]`, `FUSION_NOT:`) ve araç
çağrısı çerçevesi (`FUSION_TOOL_CALL … FUSION_TOOL_CALL_END`) kullanıcı içeriği
değildir. Web modelleri bunları cevaba yansıtabiliyor; kalıcı sohbet kaydına
girince de uygulama yeniden açıldığında kullanıcıya görünüyordu.
"""

from __future__ import annotations

import re

from .tool_emulation import CALL_CLOSE, CALL_OPEN

#: Harness notunun başladığı satır önekleri. Not, bir sonraki boş satıra kadar sürer.
_NOTE_PREFIXES = ("[eylem-kanıtı-zorunlu]", "FUSION_NOT:", "[kayıt]")

_CALL_BLOCK = re.compile(
    rf"(?:```[a-z]*\s*)?{CALL_OPEN}\b.*?{CALL_CLOSE}(?:\s*```)?", re.DOTALL | re.IGNORECASE
)
_STRAY_MARKER = re.compile(rf"^[ \t]*(?:{CALL_CLOSE}|{CALL_OPEN})[ \t]*$", re.MULTILINE)
_BLANKS = re.compile(r"\n{3,}")


def is_harness_note(text: str) -> bool:
    """Metin tümüyle bir harness notu mu (kullanıcı mesajı olarak gösterilmemeli)?"""
    return text.lstrip().startswith(_NOTE_PREFIXES)


def strip_harness_leaks(text: str) -> str:
    """Araç çağrısı çerçevesini ve harness not paragraflarını metinden çıkar."""
    if not text:
        return text
    cleaned = _CALL_BLOCK.sub("", text)
    cleaned = _STRAY_MARKER.sub("", cleaned)
    paragraphs = [
        paragraph
        for paragraph in re.split(r"\n\s*\n", cleaned)
        if not paragraph.lstrip().startswith(_NOTE_PREFIXES)
    ]
    return _BLANKS.sub("\n\n", "\n\n".join(paragraphs)).strip()
