"""Çalışma dizinleri dışından okuma — Claude Code ile birebir (#56).

Kaynak: code.claude.com/docs/en/permissions#permission-system (Read-only satırı): okumalar
yalnız çalışma dizini ve ek dizinler (`--add-dir`, `/add-dir`, `additionalDirectories`)
içinde sorulmadan yapılır. Dışındaki okuma Manuel, acceptEdits ve plan kipinde sorulur;
dontAsk'ta reddedilir; auto ve bypass sormaz.

Okuma araçları (`permission_match.READ_TOOLS`) için hedef `path`tir; yolsuz arama/listeleme
proje kökünde çalıştığı için içeride sayılır. Kabuk okuma komutları burada değil.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from ..core.tools import ToolContext

#: Okuma araçları (`permission_match.READ_TOOLS` ile aynı küme; döngüsel içe aktarmasız).
_READ_TOOLS = frozenset(
    {"read_file", "view_file", "list_dir", "list_files", "glob", "grep_search", "search_code",
     "view_image"}
)  # fmt: skip

OUTSIDE_READ_REASON = "çalışma dizinleri dışından okuyor ({yol})"


def is_read_tool(tool_name: str) -> bool:
    return tool_name in _READ_TOOLS


def outside_read_target(
    tool_name: str,
    args: Mapping[str, object],
    root: Path | None,
    extra_roots: Iterable[Path] = (),
) -> str | None:
    """Okuma aracının hedefi çalışma dizinleri dışındaysa çözülmüş yolu; değilse `None`."""
    if root is None or tool_name not in _READ_TOOLS:
        return None
    raw = args.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        path = Path(raw.strip()).expanduser()
        target = (path if path.is_absolute() else root / path).resolve()
        allowed = [root.resolve(), *(Path(extra).resolve() for extra in extra_roots)]
    except (OSError, RuntimeError, ValueError):
        return raw.strip()
    if any(target == base or base in target.parents for base in allowed):
        return None
    return str(target)


def read_roots(context: ToolContext | None) -> tuple[Path, ...]:
    """Okumanın sorulmadığı ek kökler: `--add-dir` dizinleri ve Fusion'ın çıktı deposu.

    Bağlamı şişiren araç çıktısı depoya alınır ve model onu `read_file` ile açar (Claude'un
    kendi `tool-results` dosyaları gibi); bu iç okuma sorulmaz.
    """
    if context is None:
        return ()
    found = list(context.extra_roots)
    store = getattr(context, "artifacts", None)
    if store is not None:
        found.append(store.root)
    return tuple(found)


def reads_outside(tool_name: str, args: Mapping[str, object], context: ToolContext | None) -> bool:
    """Okuma aracı çalışma dizinleri dışını mı okuyor? (Onay kapısını açar.)"""
    if context is None:
        return False
    return outside_read_target(tool_name, args, context.root, read_roots(context)) is not None
