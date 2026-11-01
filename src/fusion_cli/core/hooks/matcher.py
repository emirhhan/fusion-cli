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
#: `FileChanged`/`StopFailure`: daha dar düz liste (yalnız harf/rakam/`_`/`|`; ayırıcı `|`).
_NARROW_LIST = re.compile(r"[A-Za-z0-9_|]+")


def matcher_matches(matcher: str, subjects: Iterable[str], *, narrow: bool = False) -> bool:
    """Eşleştirici verilen adlardan (araç adı ve Claude karşılıkları) birine uyuyor mu?

    `narrow`: Claude'un `FileChanged` ve `StopFailure` kuralı — tire, boşluk ya da virgül
    eşleştiriciyi düzenli ifade yoluna sokar, yalnız `|` seçenek ayırır.
    """
    text = matcher.strip()
    if text in ("", "*"):
        return True
    names = tuple(subjects)
    plain, separators = (_NARROW_LIST, r"[|]") if narrow else (_PLAIN_LIST, r"[|,]")
    if plain.fullmatch(text):
        options = {part.strip() for part in re.split(separators, text) if part.strip()}
        return any(name in options for name in names)
    try:
        pattern = re.compile(text)
    except re.error:
        return False
    return any(pattern.search(name) for name in names)
