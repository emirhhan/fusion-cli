"""MCP araç adları: Claude Code biçimi `mcp__<sunucu>__<araç>` (#242).

Claude Code'da (code.claude.com/docs/en/mcp, "Tool naming") uzak araç modele
`mcp__<sunucu>__<araç>` adıyla gider; eklenti sunucusunda sunucu adı zaten
`plugin_<eklenti>_<sunucu>` olduğundan ad `mcp__plugin_<e>_<s>__<araç>` olur.
`A-Z a-z 0-9 _ -` dışındaki karakterler `_` olur; tam adı 128 karakteri aşan araç
modele gönderilmez.

Fusion'ın eski kayıt adı `<sunucu>__<araç>` (öneksiz) bir sürüm boyunca takma ad
olarak okunur: izin kuralı, kanca eşleştirici ve `--allowed-tools` bu yazımı da
tanır. Bu modül yalnız stdlib kullanır; bütün katmanlar adı buradan ayrıştırır.
"""

from __future__ import annotations

import hashlib
import re

__all__ = [
    "MAX_CLAUDE_TOOL_NAME_CHARS",
    "MAX_PROVIDER_TOOL_NAME_CHARS",
    "MCP_TOOL_PREFIX",
    "canonical_mcp_name",
    "claude_mcp_tool_name",
    "is_legacy_mcp_name",
    "legacy_mcp_name",
    "mcp_server_of",
    "provider_mcp_tool_name",
    "split_mcp_tool_name",
]

MCP_TOOL_PREFIX = "mcp__"
#: Claude Code: tam adı bundan uzun araç modele hiç gönderilmez.
MAX_CLAUDE_TOOL_NAME_CHARS = 128
#: OpenAI ve Gemini işlev adı sınırı (`^[a-zA-Z0-9_-]{1,64}$`); Fusion çok sağlayıcılı.
MAX_PROVIDER_TOOL_NAME_CHARS = 64
_SEPARATOR = "__"
_INVALID = re.compile(r"[^a-zA-Z0-9_-]")
_HASH_CHARS = 8


def claude_mcp_tool_name(server: str, tool: str) -> str:
    """Claude'un tam adı: geçersiz karakterler `_`, özet yok (sınır denetimi yok)."""
    return f"{MCP_TOOL_PREFIX}{_INVALID.sub('_', server)}{_SEPARATOR}{_INVALID.sub('_', tool)}"


def provider_mcp_tool_name(server: str, tool: str) -> str | None:
    """Kayıt defteri ve sağlayıcı adı; 128'i aşan araçta None (modele gönderilmez).

    64 karakteri aşan ad OpenAI/Gemini 400 hatası verir: o aralıkta (65-128) ad 64'e
    kısaltılıp sonuna tam adın 8 haneli özeti eklenir (sağlayıcı sınırı; Claude'da yok).
    """
    full = claude_mcp_tool_name(server, tool)
    if len(full) > MAX_CLAUDE_TOOL_NAME_CHARS:
        return None
    if len(full) <= MAX_PROVIDER_TOOL_NAME_CHARS:
        return full
    digest = hashlib.sha256(full.encode("utf-8")).hexdigest()[:_HASH_CHARS]
    keep = MAX_PROVIDER_TOOL_NAME_CHARS - _HASH_CHARS - 1
    return f"{full[:keep]}_{digest}"


def split_mcp_tool_name(name: str) -> tuple[str, str] | None:
    """`mcp__s__t` ya da eski `s__t` → (`s`, `t`); MCP adı değilse None."""
    body = name[len(MCP_TOOL_PREFIX) :] if name.startswith(MCP_TOOL_PREFIX) else name
    server, separator, tool = body.partition(_SEPARATOR)
    if not (separator and server and tool):
        return None
    return server, tool


def mcp_server_of(name: str) -> str:
    """Aracın MCP sunucusu (`mcp__github__x` ve eski `github__x` → `github`); yoksa boş."""
    parts = split_mcp_tool_name(name)
    return parts[0] if parts else ""


def is_legacy_mcp_name(name: str) -> bool:
    """Öneksiz eski Fusion yazımı mı (`github__get_issue`)."""
    return not name.startswith(MCP_TOOL_PREFIX) and split_mcp_tool_name(name) is not None


def canonical_mcp_name(name: str) -> str:
    """Eski `s__t` yazımını `mcp__s__t` yap; diğer adlar (yerleşik araç) aynen kalır."""
    return f"{MCP_TOOL_PREFIX}{name}" if is_legacy_mcp_name(name) else name


def legacy_mcp_name(name: str) -> str:
    """`mcp__s__t` → eski `s__t` (kanca eşleştiricisinin geriye uyumu); diğerleri aynen."""
    if name.startswith(MCP_TOOL_PREFIX) and split_mcp_tool_name(name) is not None:
        return name[len(MCP_TOOL_PREFIX) :]
    return name
