"""Yerel dosyaya YAZAN araçların hedef yolları — tek liste (P-001, P-002).

Korumalı yol denetimi (`protected_paths`), `Edit`/`Write` kuralı eşlemesi
(`permission_match`) ve kök-dışı yazma denetimi (`approval`) aynı soruyu sorar: "bu
çağrı hangi yola yazıyor?" Ölçüldü (31 Ekim): üç yerde üç ayrı `write_file/edit_file/…`
listesi vardı ve `download_file`, `extract_archive`, görsel araçları hiçbirinde yoktu;
`download_file path=.git/hooks/pre-commit` auto kipte sorulmadan geçiyordu.

Araç katmanında bu yollar zaten `files.writable_path` kapısından geçer (kök dışı ve
`block_writes_outside_root`); buradaki liste onay/kural katmanı içindir.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath

#: Araç adı → hedef yolu taşıyan argüman adları (sırayla ilk dolu olan alınır).
WRITE_PATH_ARGS: dict[str, tuple[str, ...]] = {
    "write_file": ("path",),
    "edit_file": ("path",),
    "multi_edit": ("path",),
    "create_file": ("path",),
    "download_file": ("path",),
    "extract_archive": ("dest",),
    "generate_image": ("path",),
    "optimize_image": ("out",),
    "browser_screenshot": ("path",),
    "desktop_screenshot": ("path",),
    "scaffold_web": ("path",),
    "scaffold_remotion": ("path",),
    "render_remotion": ("output",),
}
#: Hedef argümanı boşken KAYNAK dosyanın dizinine yazan araçlar (`extract_archive`: arşivin
#: dizini; `optimize_image`: görselin yanına `.webp`).
_DEFAULTS_TO_SOURCE_DIR = frozenset({"extract_archive", "optimize_image"})
#: Claude'un `Edit`/`Write` kurallarının çekirdek karşılığı: içerik yazan düz dosya araçları.
FILE_WRITE_TOOLS = frozenset({"write_file", "edit_file", "multi_edit", "create_file"})
#: Yerel yola yazan TÜM araçlar (kural eşlemesi ve korumalı yol denetimi bu kümeye bakar).
WRITE_TOOLS = frozenset(WRITE_PATH_ARGS)


def write_targets(tool_name: str, args: Mapping[str, object]) -> tuple[str, ...]:
    """Çağrının yazdığı yollar (verildiği gibi, çözülmemiş); yazmayan araçta boş."""
    keys = WRITE_PATH_ARGS.get(tool_name)
    if keys is None:
        return ()
    found = tuple(_text(args.get(key)) for key in keys if _text(args.get(key)))
    if found or tool_name not in _DEFAULTS_TO_SOURCE_DIR:
        return found
    source = _text(args.get("path"))
    if not source:
        return ()
    parent = PurePosixPath(source).parent.as_posix()
    return (parent or ".",)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""
