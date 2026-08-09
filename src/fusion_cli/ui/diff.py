"""Diff render — unified diff'i satır numaralı, renkli bir bloğa çevirir.

Claude Code diziliminde değiştirici bir araç çalıştıktan sonra hangi satırların
eklendiği/silindiği görünür: eklenen satır yeşil, silinen kırmızı zeminle. Bu modül
saf tutulur — dosya okumaz, olay bilmez; yalnızca metin diff'i alır ve renkli bir
Rich `Text` üretir. Diff üretimi `tools/preview.py`'nin işidir; burası yalnızca sunum.

Girdi iki biçimden biri olabilir:

- Standart unified diff (`edit_file`/`multi_edit`/mevcut dosyaya `write_file`):
  `@@ -a,b +c,d @@` başlıklarından satır numaraları çıkarılır.
- Yeni dosya önizlemesi (`write_file` olmayan dosyaya): `@@` yok, yalnızca `+satır`
  listesi; numaralandırma 1'den başlatılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rich.text import Text

from ..core.constants import MAX_PREVIEW_LINES
from . import messages, theme

#: `@@ -eski_baş,eski_sayı +yeni_baş,yeni_sayı @@` başlığından başlangıç satırlarını çeker.
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

#: Satır numarası sütununun genişliği; tek haneli ve dört haneli dosyalar hizalı dizilir.
_LINE_NO_WIDTH = 4


@dataclass(frozen=True, slots=True)
class RenderedDiff:
    """Bir diff'in görsel karşılığı ve özet sayıları."""

    added: int
    removed: int
    body: Text


def render_diff(
    diff_text: str, *, max_lines: int = MAX_PREVIEW_LINES, width: int | None = None
) -> RenderedDiff:
    """Unified diff metnini renkli, satır numaralı, tavanlı bir bloğa çevir.

    `width` verilirse satır içeriği o genişliğe kırpılır. Kırpmamak sarmaya yol
    açıyor ve sarma sol oluğu (satır numarası + işaret) kaybettiriyordu: devam
    satırı hizasız düşüyor, diff okunmaz hale geliyordu.

    `added`/`removed` sayıları DAİMA tam diff'i yansıtır (tavandan bağımsız); yalnızca
    görünen satır sayısı `max_lines` ile sınırlanır — uzun bir diff ekranı sel gibi
    doldurmaz ama özet gerçek değişiklik boyutunu söyler.
    """
    added = 0
    removed = 0
    old_line = 1
    new_line = 1
    body = Text()
    shown = 0
    truncated = 0

    for raw in diff_text.splitlines():
        if raw.startswith("---") or raw.startswith("+++"):
            continue  # diff dosya başlıkları gürültü
        header = _HUNK_HEADER.match(raw)
        if header is not None:
            old_line, new_line = int(header.group(1)), int(header.group(2))
            continue
        kind = _classify(raw)
        if kind is _Kind.ADD:
            added += 1
        elif kind is _Kind.REMOVE:
            removed += 1

        if shown >= max_lines:
            truncated += 1  # görünmese de sayım ilerlesin diye türü yukarıda işlendi
            old_line, new_line = _step(kind, old_line, new_line)
            continue

        _append_row(body, kind, raw, old_line, new_line, width)
        old_line, new_line = _step(kind, old_line, new_line)
        shown += 1

    if truncated:
        body.append(messages.DIFF_TRUNCATED.format(count=truncated), style=theme.DIFF_CONTEXT)
        body.append("\n")
    return RenderedDiff(added=added, removed=removed, body=body)


# --------------------------------------------------------------------------- #


class _Kind:
    ADD = "add"
    REMOVE = "remove"
    CONTEXT = "context"
    OTHER = "other"


def _classify(raw: str) -> str:
    """Diff satırının türünü işaret karakterinden belirle."""
    if raw.startswith("+"):
        return _Kind.ADD
    if raw.startswith("-"):
        return _Kind.REMOVE
    if raw.startswith(" ") or raw == "":
        return _Kind.CONTEXT
    return _Kind.OTHER


def _content(raw: str, kind: str) -> str:
    """İşaret karakterini ayıkla; gövde metnini döndür."""
    if kind in (_Kind.ADD, _Kind.REMOVE) or (kind is _Kind.CONTEXT and raw.startswith(" ")):
        return raw[1:]
    return raw


def _append_row(
    body: Text, kind: str, raw: str, old_line: int, new_line: int, width: int | None = None
) -> None:
    """Tek bir diff satırını numarası, işareti ve zemin rengiyle ekle."""
    content = _content(raw, kind)
    if width is not None:
        # Oluk `_LINE_NO_WIDTH + 3` karakter yer kaplar; içerik ondan geriye kalana sığar.
        alan = max(8, width - _LINE_NO_WIDTH - 3)
        if len(content) > alan:
            content = content[: alan - 1] + "…"
    if kind is _Kind.ADD:
        _row(body, new_line, "+", content, theme.DIFF_ADD, theme.DIFF_ADD_BG)
    elif kind is _Kind.REMOVE:
        _row(body, old_line, "-", content, theme.DIFF_DEL, theme.DIFF_DEL_BG)
    elif kind is _Kind.CONTEXT:
        _row(body, new_line, " ", content, theme.DIFF_CONTEXT, None)
    else:
        body.append(content + "\n", style=theme.DIFF_CONTEXT)


def _row(body: Text, line_no: int, sign: str, content: str, color: str, bg: str | None) -> None:
    """`  12 + metin` biçiminde tek satır bas; zemin verilirse satırı boyar."""
    style = f"{color} on {bg}" if bg else color
    body.append(f"{line_no:>{_LINE_NO_WIDTH}} {sign} ", style=theme.DIFF_CONTEXT)
    body.append(content, style=style)
    body.append("\n")


def _step(kind: str, old_line: int, new_line: int) -> tuple[int, int]:
    """Satır türüne göre eski/yeni satır sayaçlarını ilerlet."""
    if kind is _Kind.ADD:
        return old_line, new_line + 1
    if kind is _Kind.REMOVE:
        return old_line + 1, new_line
    if kind is _Kind.CONTEXT:
        return old_line + 1, new_line + 1
    return old_line, new_line
