"""Ajan `color` alanı (#25): Claude Code değerleri birincil, eski Türkçe adlar takma ad.

Claude Code yalnız `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan` kabul
eder. Arayüz (terminal teması, masaüstü avatarı) renkleri iç Türkçe anahtarlarla boyar; Claude
değeri bu anahtara çevrilir. Tanınmayan değer uyarıyla düşer (gri görünür).
"""

from __future__ import annotations

import logging

_LOG = logging.getLogger(__name__)

CLAUDE_COLORS: dict[str, str] = {
    "red": "kirmizi",
    "blue": "mavi",
    "green": "yesil",
    "yellow": "sari",
    "purple": "mor",
    "orange": "turuncu",
    "pink": "pembe",
    "cyan": "camgobegi",
}
_LEGACY = frozenset(CLAUDE_COLORS.values())


def normalize_agent_color(value: str) -> str:
    """Claude rengini iç anahtara çevir; eski Türkçe ad aynen kalır, geçersiz boş döner."""
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    if cleaned in CLAUDE_COLORS:
        return CLAUDE_COLORS[cleaned]
    if cleaned in _LEGACY:
        return cleaned
    _LOG.warning("ajan color değeri tanınmadı; uygulanmadı", extra={"renk": value})
    return ""
