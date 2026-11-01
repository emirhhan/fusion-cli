"""Kabuk aracının kalıcı çalışma dizini (#126; Claude Code Bash aracı ile aynı).

Claude Code: kabuk komutunun `cd`'si sonraki komutlara taşınır; proje kökü (ve ek
dizinler) dışına çıkan dizin köke sıfırlanır ve model bunu araç sonucunda görür.
`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` her komuttan sonra proje köküne döndürür.
Dizin değişince ana konuşmada `CwdChanged` kancası tetiklenir (kanca köprüsü).

Komutun bitişteki dizini, komuttan sonra eklenen tek satırlık bir işaretle okunur
(`wrap` / `split_marker`); işaret her çağrıda rastgeledir, komut çıktısı onu taklit
edemez. Yalnız stdlib (core katmanı).
"""

from __future__ import annotations

import os
import shlex
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

#: Claude Code ortam değişkeni: doğruysa çalışma dizini komutlar arasında sürmez.
MAINTAIN_ENV = "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"
_TRUE = frozenset({"1", "true", "yes", "on"})
_MARK_PREFIX = "__FUSION_CWD_"
#: Modele giden notlar (Claude: "Shell cwd was reset to <dizin>").
RESET_NOTE = "Kabuk çalışma dizini proje dışına çıktığı için sıfırlandı: {root}"
MOVED_NOTE = "Kabuk çalışma dizini artık {path}; sonraki komutlar burada başlar."


@dataclass(slots=True)
class ShellCwd:
    """Oturumun kabuk dizini (taşıyıcı nesne; `ToolContext` donmuş olduğu için)."""

    #: Kökten farklı kalıcı dizin; `None` = proje kökü.
    path: Path | None = None
    #: Son komutun yaptığı (eski, yeni) dizin değişikliği; kanca köprüsü alıp temizler.
    changed: tuple[Path, Path] | None = None


def maintains_project_dir(env: Mapping[str, str] | None = None) -> bool:
    """`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` açık mı?"""
    source = os.environ if env is None else env
    return source.get(MAINTAIN_ENV, "").strip().lower() in _TRUE


def within(path: Path, roots: Iterable[Path]) -> bool:
    """`path` köklerden birinin kendisi ya da altında mı (bağlar çözülerek)?"""
    try:
        target = path.resolve()
        bases = [root.resolve() for root in roots]
    except (OSError, RuntimeError):
        return False
    return any(target == base or base in target.parents for base in bases)


def current(holder: ShellCwd | None, root: Path, extra_roots: Iterable[Path] = ()) -> Path:
    """Sıradaki komutun başlayacağı dizin: geçerli kalıcı dizin, yoksa proje kökü."""
    path = holder.path if holder is not None else None
    if path is None or maintains_project_dir():
        return root
    if not within(path, (root, *extra_roots)) or not path.is_dir():
        return root
    return path


def new_marker() -> str:
    return f"{_MARK_PREFIX}{uuid.uuid4().hex}__"


def wrap(command: str, marker: str) -> str:
    """Komutu çalıştır, çıkış kodunu koru, sonra bitişteki dizini işaretle yaz."""
    return (
        f"{{ {command}\n}}\n__fusion_rc=$?\n"
        f"printf '\\n%s%s\\n' {shlex.quote(marker)} \"$PWD\"\nexit $__fusion_rc"
    )


def split_marker(stdout: str, marker: str) -> tuple[str, Path | None]:
    """Çıktıdan işaret satırını ayır: (komutun kendi çıktısı, bitişteki dizin)."""
    index = stdout.rfind("\n" + marker)
    if index < 0:
        return stdout, None
    tail = stdout[index + 1 + len(marker) :]
    line, _, rest = tail.partition("\n")
    if not line.strip():
        return stdout[:index] + rest, None
    return stdout[:index] + rest, Path(line)


def settle(
    holder: ShellCwd, reported: Path | None, root: Path, extra_roots: Iterable[Path] = ()
) -> str | None:
    """Komutun bıraktığı dizini kaydet; modele gidecek not (değiştiyse/sıfırlandıysa)."""
    if reported is None:
        return None
    extras = tuple(extra_roots)
    old = current(holder, root, extras)
    if maintains_project_dir():
        holder.path = None
        return None
    reset = not within(reported, (root, *extras))
    new = root if reset else reported
    holder.path = None if _same(new, root) else new
    if not _same(new, old):
        holder.changed = (old, new)
    elif not reset:
        return None
    return RESET_NOTE.format(root=root) if reset else MOVED_NOTE.format(path=new)


def _same(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except (OSError, RuntimeError):
        return left == right
