"""Diğer araçların bellek dosyalarını sistem promptuna hazırlar.

`project_instructions.py` hedef projenin KENDİ talimat dosyasını okuyor. Bu modül
onun eşleniğidir: kullanıcının başka araçlarda biriktirdiği KALICI belleği okur.
Aynı "sığ tarama" ilkesi geçerlidir — dosya varsa okunur, yoksa sessizce atlanır.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from .claude_source import slug_for

#: Tek bir bellek dosyasından okunacak en fazla karakter.
MAX_CHARS = 6_000


def _candidates(home: Path, root: Path) -> tuple[tuple[Path, str], ...]:
    return (
        (home / ".claude" / "projects" / slug_for(root) / "memory" / "MEMORY.md", "claude"),
        (home / ".hermes" / "memories" / "MEMORY.md", "hermes"),
        (home / ".hermes" / "memories" / "USER.md", "hermes"),
    )


def read_external_memory(home: Path, root: Path) -> str:
    """Bulunan bellek dosyalarını tek bir etiketli blok olarak döndür."""
    blocks: list[str] = []
    for path, source in _candidates(home, root):
        content = _read_regular_file(path)
        if content is None:
            continue
        if not content:
            continue
        trimmed = len(content) > MAX_CHARS
        if trimmed:
            content = content[:MAX_CHARS]
        suffix = "\n[…kırpıldı…]" if trimmed else ""
        blocks.append(
            f'<dis_bellek kaynak="{source}" dosya="{path.name}">\n{content}{suffix}\n</dis_bellek>'
        )
    return "\n".join(blocks)


def _read_regular_file(path: Path) -> str | None:
    """Sembolik bağ izlemeden düzenli dosyadan sınırlı UTF-8 metin oku.

    `O_NOFOLLOW` bulunan platformlarda son yol bileşeni açma anında da bağa
    dönüşemez. Desteklenmeyen platformlarda `lstat` ile alınan kimlik, açılan
    dosyanın `fstat` kimliğiyle karşılaştırılır; yarışta başka dosyaya geçilirse
    içerik kullanılmaz.
    """
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    before = _safe_lstat(path) if no_follow == 0 else None
    if before is not None and (stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode)):
        return None
    try:
        descriptor = os.open(path, os.O_RDONLY | no_follow)
    except OSError:
        return None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_file(before, opened):
            return None
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            descriptor = -1
            return handle.read(MAX_CHARS + 1).strip()
    except (OSError, UnicodeError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _safe_lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except OSError:
        return None


def _same_file(before: os.stat_result | None, opened: os.stat_result) -> bool:
    if before is None:
        return True
    return (before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino)
