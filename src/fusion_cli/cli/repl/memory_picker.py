"""`/memory` bellek dosyası seçicisi Claude Code ile birebir (#154).

Claude Code (code.claude.com/docs/en/memory, "View and edit with /memory"): `/memory` oturumda
yüklenen CLAUDE.md, CLAUDE.local.md ve kural dosyalarını listeler, otomatik belleği aç/kapat
ve bellek klasörünü açma seçeneği verir; seçilen dosya düzenleyicide açılır. Kullanıcı ve
proje dosyası henüz yoksa da listelenir, seçilince oluşturulur.

Terminal REPL'de seçici numaralı listedir: `/memory` listeler, `/memory <n>` açar.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ...config.paths import editor_command
from ...ui import messages
from .state import ReplState


@dataclass(frozen=True, slots=True)
class MemoryFile:
    label: str
    path: Path


def memory_files(state: ReplState) -> tuple[MemoryFile, ...]:
    """Seçicideki dosyalar: kullanıcı, proje, yerel proje, kurallar, otomatik bellek."""
    root = state.root
    project = root / "CLAUDE.md"
    if not project.exists() and (root / ".claude" / "CLAUDE.md").exists():
        project = root / ".claude" / "CLAUDE.md"
    items = [
        MemoryFile("Kullanıcı belleği", state.home / ".claude" / "CLAUDE.md"),
        MemoryFile("Proje belleği", project),
        MemoryFile("Yerel proje belleği", root / "CLAUDE.local.md"),
    ]
    rules = root / ".claude" / "rules"
    if rules.is_dir():
        items += [
            MemoryFile(f"Kural: {path.relative_to(rules)}", path)
            for path in sorted(rules.rglob("*.md"))
        ]
    if state.plain_memory is not None:
        items.append(MemoryFile("Otomatik bellek", state.plain_memory.index_path))
    return tuple(items)


def render_picker(state: ReplState) -> str:
    """Numaralı liste + otomatik bellek durumu ve klasörü."""
    lines = [messages.MEMORY_PICKER_HEADER]
    for index, item in enumerate(memory_files(state), start=1):
        mark = "" if item.path.exists() else messages.MEMORY_PICKER_NEW
        lines.append(f"  {index}. {item.label}: {item.path}{mark}")
    auto = messages.REPL_ON if state.plain_memory is not None else messages.REPL_OFF
    folder = state.plain_memory.index_path.parent if state.plain_memory is not None else "-"
    lines.append(messages.MEMORY_PICKER_AUTO.format(state=auto, folder=folder))
    return "\n".join(lines)


def open_choice(state: ReplState, choice: str) -> str:
    """`/memory <n>`: seçilen dosyayı (yoksa oluşturup) düzenleyicide aç."""
    items = memory_files(state)
    index = int(choice) - 1
    if not 0 <= index < len(items):
        return messages.MEMORY_PICKER_RANGE.format(count=len(items))
    path = items[index].path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    if not sys.stdin.isatty():
        return messages.MEMORY_EDIT_NO_TTY.format(path=path)
    try:
        subprocess.run([*editor_command(), str(path)], check=False)
    except OSError as error:
        return f"Düzenleyici açılamadı: {error}. Dosya: {path}"
    return messages.MEMORY_EDIT_OPENED
