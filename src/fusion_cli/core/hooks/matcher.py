"""Kanca eşleştiricisi (`matcher`) — Claude Code ile aynı sözdizimi.

    ""  ya da  "*"        her şey
    "Bash"                birebir ad
    "Edit|Write", "a,b"   ad listesi (yalnız harf/rakam/_/-/boşluk içeren parçalar)
    "mcp__github__.*"     aksi halde düzenli ifade, ÇAPASIZ (JavaScript `RegExp.test`):
                          `Edit.*` NotebookEdit'e de uyar; tam eşleşme için `^Edit$`

Bozuk düzenli ifade hiçbir şeyle eşleşmez (kanca sessizce her araçta çalışmaz).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_PLAIN_LIST = re.compile(r"[A-Za-z0-9_\- ,|]+")


def matcher_matches(matcher: str, subjects: Iterable[str]) -> bool:
    """Eşleştirici verilen adlardan (araç adı ve Claude karşılıkları) birine uyuyor mu?"""
    text = matcher.strip()
    if text in ("", "*"):
        return True
    names = tuple(subjects)
    if _PLAIN_LIST.fullmatch(text):
        options = {part.strip() for part in re.split(r"[|,]", text) if part.strip()}
        return any(name in options for name in names)
    try:
        pattern = re.compile(text)
    except re.error:
        return False
    return any(pattern.search(name) for name in names)
