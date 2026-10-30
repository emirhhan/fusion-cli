"""Uzak MCP aracının Fusion/sağlayıcı araç adı.

Sağlayıcılar (OpenAI, Anthropic, Gemini) araç adını `^[a-zA-Z0-9_-]{1,64}$` ister.
Sunucu adı kullanıcıdan gelir ("META ADS") ve uzak araç adı sunucudan; ham
birleştirme geçersiz ad üretip bütün turu 400 ile düşürebilir.
"""

from __future__ import annotations

import hashlib
import re

__all__ = ["MAX_TOOL_NAME_CHARS", "fusion_tool_name"]

MAX_TOOL_NAME_CHARS = 64
_INVALID = re.compile(r"[^a-zA-Z0-9_-]")
_HASH_CHARS = 8


def fusion_tool_name(server: str, tool: str) -> str:
    """`<sunucu>__<araç>`; kurala uyan ad AYNEN kalır, uymayan temizlenir.

    Temizlenen ya da kısaltılan adın sonuna ham adın özeti eklenir: "A B" ile "A_B"
    gibi farklı kaynaklar aynı ada çökmez ve ad çağrılar arasında kararlı kalır.
    """
    raw = f"{server}__{tool}"
    clean = _INVALID.sub("_", raw)
    if clean == raw and len(raw) <= MAX_TOOL_NAME_CHARS:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:_HASH_CHARS]
    keep = MAX_TOOL_NAME_CHARS - _HASH_CHARS - 1
    return f"{clean[:keep]}_{digest}"
