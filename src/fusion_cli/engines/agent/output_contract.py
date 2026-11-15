"""Kullanıcının teslim hedefini güvenli ve sürümlü bir çıktı sözleşmesine çevir."""

from __future__ import annotations

import re
from pathlib import Path

from ...core.tools import ToolContext

#: Ters tırnak içindeki göreli, uzantılı yol (adres ve mutlak yol değil).
_PATH = re.compile(
    r'(?<![\w./:@-])(?:`(?P<backtick>[^`\n]+)`|"(?P<quoted>[^"\n]+)"|'
    r"(?P<path>[\w./:@-]+\.[A-Za-z0-9]{1,5})(?![\w/-]))"
)
_OUTPUT_SUFFIX = re.compile(r".+\.[A-Za-z0-9]{1,5}$")
#: Yolun hemen ardında (ya da önünde) çıktı olduğunu söyleyen sözler.
_OUTPUT_WORDS = re.compile(
    r"olarak|olsun|kaydet|render|üret|uret|çıktı|cikti|dışa aktar|\bsave\b|\boutput\b|"
    r"\bexport\b|\bwrite to\b",
    re.IGNORECASE,
)
#: Yolun çevresinde bakılan pencere (karakter).
_WINDOW = 40


def requested_outputs_in(task: str, *, root: Path | None = None) -> tuple[str, ...]:
    """İsteğin çıktı olarak andığı göreli dosya yolları (sırası korunur, tekrarsız)."""
    found: list[str] = []
    for match in _PATH.finditer(task):
        around = task[max(0, match.start() - _WINDOW) : match.end() + _WINDOW]
        yol = match.group("backtick") or match.group("quoted") or match.group("path")
        if not _OUTPUT_SUFFIX.fullmatch(yol) or ".." in Path(yol).parts or ":" in yol:
            continue
        if Path(yol).is_absolute():
            if root is None:
                continue
            try:
                yol = Path(yol).resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
        if _OUTPUT_WORDS.search(around) and yol not in found:
            found.append(yol)
    return tuple(found)


def capture_output_baselines(context: ToolContext) -> None:
    """Kök turun teslim sözleşmesi kurulurken mevcut çıktı sürümlerini kaydet."""
    context.output_baselines.clear()
    root = context.root.resolve()
    for name in context.requested_outputs:
        path = (root / name).resolve()
        if path.is_relative_to(root):
            context.output_baselines[name] = output_file_version(path)


def output_file_version(path: Path) -> tuple[int, int] | None:
    try:
        version = path.stat()
        return version.st_size, version.st_mtime_ns
    except OSError:
        return None
