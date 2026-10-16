"""Büyük metin dosyalarını sınırlı bellekle fiziksel satır aralığından oku."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Event

from ..core.tools import ToolResult

_CHUNK_CHARS = 8_192


def read_large_text(
    path: Path, label: str, *, offset: int, limit: int, byte_limit: int, cancelled: Event
) -> ToolResult:
    """Atlanan satırlar bütçeyi tüketmez; kısmi satır tam okuma sayılmaz."""
    lines: list[str] = []
    parts: list[str] = []
    line_number = 1
    used = 0
    partial = False
    reached_eof = False
    line_open = False
    try:
        with path.open("r", encoding="utf-8", newline=None) as source:
            while len(lines) < limit:
                if cancelled.is_set():
                    return ToolResult.failure("Dosya okuma iptal edildi.")
                fragment = source.readline(_CHUNK_CHARS)
                if not fragment:
                    reached_eof = True
                    if line_open:
                        if line_number >= offset:
                            lines.append("".join(parts))
                        line_number += 1
                    break
                line_open = True
                complete = fragment.endswith("\n")
                if line_number >= offset:
                    encoded = fragment.encode("utf-8")
                    remaining = byte_limit - used
                    if remaining == 0 and not parts:
                        break
                    if len(encoded) > remaining:
                        # Kaynak zaten strict UTF-8 çözüldü; yalnız sınırdaki
                        # yarım çok baytlı karakteri düşür, replacement üretme.
                        parts.append(encoded[:remaining].decode("utf-8", errors="ignore"))
                        lines.append("".join(parts).rstrip("\n"))
                        partial = True
                        break
                    parts.append(fragment)
                    used += len(encoded)
                if complete:
                    if line_number >= offset:
                        lines.append("".join(parts).removesuffix("\n"))
                    parts.clear()
                    line_open = False
                    line_number += 1
    except UnicodeDecodeError:
        return ToolResult.failure(f"Metin dosyası değil (UTF-8 çözülemedi): {label}")

    if not lines:
        count = line_number - 1
        return ToolResult.failure(
            f"{label} yalnızca {count} satır; offset={offset} dosyanın sonunu geçiyor."
        )
    output = "\n".join(f"{number:>5}\t{line}" for number, line in enumerate(lines, offset))
    if partial:
        output += (
            f"\n\n[… {byte_limit} baytlık okuma penceresinde KIRPILDI; son satır kısmi. "
            "Bu uzun satırın ilgili bölümünü search_code ile bul; tamamı okunmuş sayılmaz.]"
        )
    elif not reached_eof:
        next_call = json.dumps({"path": label, "offset": offset + len(lines)}, ensure_ascii=False)
        output += (
            f"\n\n[… okuma penceresinde KIRPILDI; kalan satır sayısı ölçülmedi. "
            f"Devamı için: read_file {next_call}]"
        )
    return ToolResult(output)
