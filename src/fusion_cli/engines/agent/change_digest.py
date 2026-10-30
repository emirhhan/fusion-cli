"""Turda değişen dosyaların GERÇEK fark özeti — modelin anlatımına karşı kayıt.

Ölçüldü (30 Ekim, g2): model "encoding düzeltmesi çözdü" dedi; gerçek değişiklik
`yeni_id` hesabı ve `bekleyenler` filtresiydi. Kapanışta yalnız dosya adları yazıldığı
için kullanıcı iddiayı gerçek farkla karşılaştıramıyordu. Burada değişiklik kaydından
(`ChangeSet`: ilk hâl + şimdiki içerik) kısa ve sınırlı bir "değişen satırlar" özeti
üretilir. Model çağrısı YOKTUR; sır dosyaları ve sır desenli satırlar ayıklanır.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from ...core.redaction import redact
from ...core.tools import ToolContext
from ...tools.files import display_path
from ...tools.search import is_secret_file

#: Özette tek tek gösterilecek en fazla dosya (gerisi "+N dosya daha").
MAX_FILES = 4
#: Bir dosya için gösterilecek en fazla değişen satır (gerisi "+N satır daha").
MAX_LINES_PER_FILE = 6
#: Tek satırın en çok karakteri.
LINE_CHARS = 100
#: Bundan büyük dosya okunmaz (bellek/süre); teacher_flow ile aynı sınır.
_MAX_BYTES = 512 * 1024
#: Bundan fazla satırlı dosyada satır farkı hesaplanmaz (difflib ikinci derece yavaşlar).
_MAX_DIFF_LINES = 5_000


def change_digest(context: ToolContext) -> tuple[str, ...]:
    """Değişen dosyaların kısa özeti; değişiklik yoksa boş.

    Eşzamansız bağlamdan `asyncio.to_thread` ile çağrılmalıdır (dosya okur).
    """
    blocks: list[tuple[str, ...]] = []
    for snapshot in context.changes.snapshots:
        if is_secret_file(snapshot.path):
            continue
        block = _file_block(context, snapshot.path, snapshot.content)
        if block:
            blocks.append(block)
    lines: list[str] = []
    for block in blocks[:MAX_FILES]:
        lines.extend(block)
    if len(blocks) > MAX_FILES:
        lines.append(f"… (+{len(blocks) - MAX_FILES} dosya daha)")
    return tuple(lines)


def _file_block(context: ToolContext, path: Path, old_bytes: bytes | None) -> tuple[str, ...]:
    name = display_path(context, path)
    if not path.exists():
        # Turda yaratılıp sonradan silinen dosya kullanıcıya hiçbir şey değiştirmedi.
        return () if old_bytes is None else (f"{name} (silindi)",)
    try:
        with path.open("rb") as handle:
            current = handle.read(_MAX_BYTES + 1)
    except OSError:
        return ()
    if len(current) > _MAX_BYTES:
        return (f"{name} (çok büyük; satır farkı gösterilmedi)",)
    if b"\x00" in current or (old_bytes is not None and b"\x00" in old_bytes):
        return (f"{name} (ikili dosya değişti)",)
    new = current.decode("utf-8", errors="replace").splitlines()
    if old_bytes is None:
        return (f"{name} (yeni dosya, {len(new)} satır)",)
    old = old_bytes.decode("utf-8", errors="replace").splitlines()
    if max(len(old), len(new)) > _MAX_DIFF_LINES:
        return (f"{name} (çok büyük; satır farkı gösterilmedi)",)
    changes = _changed_lines(old, new)
    if not changes:
        return ()
    removed = sum(1 for sign, _ in changes if sign == "-")
    added = len(changes) - removed
    shown = [f"  {sign} {_clip(text)}" for sign, text in changes[:MAX_LINES_PER_FILE]]
    if len(changes) > MAX_LINES_PER_FILE:
        shown.append(f"  … (+{len(changes) - MAX_LINES_PER_FILE} satır daha)")
    return (f"{name} (+{added} -{removed})", *shown)


def _changed_lines(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    """(işaret, satır) çiftleri: önce silinenler, sonra eklenenler (bölge bölge)."""
    result: list[tuple[str, str]] = []
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        result.extend(("-", line) for line in old[i1:i2])
        result.extend(("+", line) for line in new[j1:j2])
    return result


def _clip(text: str) -> str:
    text = redact(text.strip())
    return text if len(text) <= LINE_CHARS else text[: LINE_CHARS - 1] + "…"
