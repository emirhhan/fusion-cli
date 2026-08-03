"""Değişiklik önizlemesi — araç ÇALIŞMADAN önce ne yapacağını gösterir.

Onay ekranında gösterilir. Önizleme üretimi saf tutulur: dosyaları yalnızca OKUR,
hiçbir şey yazmaz. Bu yüzden "önizlemeyi görüp reddettim ama dosya değişmişti" gibi
bir durum oluşamaz.

Yazma araçlarının tamamı için önizleme üretilebilir; üretilemeyen bir durumda None
döner ve onay ekranı ham argümanları gösterir.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from ..core.constants import MAX_PREVIEW_LINES
from ..core.tools import ToolArgs, ToolContext
from .args import ArgumentError
from .files import parse_edits, resolve_path

#: Renderlanabilir DOSYA diff'i üreten araçlar. `run_shell` de önizleme üretir ama
#: onunki komut satırıdır, diff değil; diff bloğu olarak basılmamalıdır.
FILE_DIFF_TOOLS = frozenset({"write_file", "edit_file", "multi_edit"})


def preview_change(tool_name: str, args: ToolArgs, context: ToolContext) -> str | None:
    """Değiştirici araç için okunabilir önizleme; üretilemezse None."""
    builder = _BUILDERS.get(tool_name)
    if builder is None:
        return None
    try:
        return builder(args, context)
    except (ArgumentError, OSError, UnicodeDecodeError):
        # Önizleme üretilemedi; onay ekranı ham argümanlara düşer. Aracın kendisi
        # zaten çalıştığında aynı sorunu anlaşılır bir hatayla bildirecek.
        return None


def file_diff(tool_name: str, args: ToolArgs, context: ToolContext) -> str | None:
    """Dosya değiştiren araçlar için, ÇALIŞMADAN ÖNCE hesaplanmış diff; değilse None.

    Diff yalnızca dosya değişmeden önce üretilebilir; çağıran taraf bunu aracı
    çalıştırmadan hemen önce çağırmalıdır.
    """
    if tool_name not in FILE_DIFF_TOOLS:
        return None
    return preview_change(tool_name, args, context)


def display_path(path: Path, context: ToolContext) -> str:
    """Diff başlığında gösterilecek yol: mümkünse köke göre kısa, değilse mutlak.

    Uzun mutlak yollar onay ekranını okunmaz hale getirir; proje içindeki bir dosya
    için `src/app.py` yeterlidir.
    """
    try:
        return str(path.relative_to(context.root))
    except ValueError:
        return str(path)


def unified_diff(old: str, new: str, path: str) -> str:
    """İki metin arasındaki farkı standart unified diff biçiminde üret."""
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )


# --------------------------------------------------------------------------- #


def _preview_write(args: ToolArgs, context: ToolContext) -> str:
    path = resolve_path(context, _path_of(args))
    new = args.get("content")
    new_text = new if isinstance(new, str) else ""
    if not path.exists():
        return _new_file_preview(path, new_text)
    old_text = path.read_text(encoding="utf-8")
    return unified_diff(old_text, new_text, display_path(path, context)) or "(değişiklik yok)"


def _preview_edit(args: ToolArgs, context: ToolContext) -> str:
    path = resolve_path(context, _path_of(args))
    if not path.exists():
        return f"(dosya yok: {path})"
    old_text = path.read_text(encoding="utf-8")
    search, replacement = args.get("old"), args.get("new")
    if not isinstance(search, str) or not isinstance(replacement, str):
        raise ArgumentError("'old' ve 'new' metin olmalı.")
    # Önizleme uygulanacak değişikliğin AYNISINI göstermelidir: toplu değiştirmeyi
    # tek eşleşme gibi göstermek, kullanıcıya yanlış şeyi onaylatır.
    limit = -1 if args.get("replace_all") is True else 1
    new_text = old_text.replace(search, replacement, limit)
    return (
        unified_diff(old_text, new_text, display_path(path, context))
        or "(eşleşme yok / değişiklik yok)"
    )


def _preview_multi_edit(args: ToolArgs, context: ToolContext) -> str:
    path = resolve_path(context, _path_of(args))
    if not path.exists():
        return f"(dosya yok: {path})"
    old_text = path.read_text(encoding="utf-8")
    new_text = old_text
    for search, replacement, replace_all in parse_edits(args.get("edits")):
        # Önizleme, uygulanacak değişikliğin AYNISINI göstermelidir; toplu değiştirme
        # tek eşleşme gibi gösterilirse kullanıcı yanlış şeyi onaylar.
        new_text = new_text.replace(search, replacement, -1 if replace_all else 1)
    return unified_diff(old_text, new_text, display_path(path, context)) or "(değişiklik yok)"


def _preview_shell(args: ToolArgs, context: ToolContext) -> str:
    command = args.get("command")
    return f"$ {command if isinstance(command, str) else ''}"


def _new_file_preview(path: Path, content: str) -> str:
    lines = content.splitlines()
    head = "\n".join(f"+{line}" for line in lines[:MAX_PREVIEW_LINES])
    more = (
        f"\n… (+{len(lines) - MAX_PREVIEW_LINES} satır)" if len(lines) > MAX_PREVIEW_LINES else ""
    )
    return f"YENİ DOSYA: {path} ({len(lines)} satır)\n{head}{more}"


def _path_of(args: ToolArgs) -> str:
    path = args.get("path")
    if not isinstance(path, str) or not path:
        raise ArgumentError("'path' alanı gerekli.")
    return path


_BUILDERS = {
    "write_file": _preview_write,
    "edit_file": _preview_edit,
    "multi_edit": _preview_multi_edit,
    "run_shell": _preview_shell,
}
