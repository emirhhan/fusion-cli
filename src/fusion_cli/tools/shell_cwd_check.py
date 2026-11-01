"""Kalıcı kabuk dizini (#126) güvenlik denetimlerine nasıl yansır.

Onay, korumalı yol, otomatik kip riski, sandbox ve silme önizlemesi göreli yolları
proje köküne göre çözer. Kabuk dizini kökten farklıyken denetim, komutun o dizinde
çalıştığını bilen bir eşdeğeri üzerinde yapılır:

- sade `rm` (çöpe taşınan silme): hedefler köke göre yeniden yazılır, böylece silme
  önizlemesi ve dikkat denetimi doğru yolu görür (`rm x` → `rm alt/x`);
- öteki her komut: `cd <dizin> && <komut>` — bütün denetimler `cd X && …` zincirini zaten
  tanır (`protected_paths`, `auto_policy`).

Çalıştırılan ve kancaya/onay kartına giden komut değişmez; yalnız denetlenen metin budur.
"""

from __future__ import annotations

import os
import posixpath
import shlex
from pathlib import Path

from ..core.shell_cwd import current
from ..core.tools import ToolContext
from .safe_delete import simple_rm_targets


def context_cwd(context: ToolContext | None) -> Path | None:
    """Bağlamın şu anki kabuk dizini (`None`: bağlam yok)."""
    if context is None:
        return None
    holder = getattr(context, "shell_cwd", None)
    return current(holder, context.root, tuple(getattr(context, "extra_roots", ()) or ()))


def checked_command(command: str, cwd: Path | None, root: Path | None) -> str:
    """Denetimlerin köke göre değerlendireceği eşdeğer komut (dizin kökse aynısı)."""
    if cwd is None or root is None or _same(cwd, root):
        return command
    cwd, root = _resolved(cwd), _resolved(root)
    if simple_rm_targets(command) is not None:
        rebased = _rebased_rm(command, cwd, root)
        if rebased is not None:
            return rebased
    return f"cd {shlex.quote(_relative(cwd, root))} && {command}"


def _rebased_rm(command: str, cwd: Path, root: Path) -> str | None:
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    rebased = [parts[0]]
    options_done = False
    for part in parts[1:]:
        if not options_done and part == "--":
            options_done = True
            rebased.append(part)
        elif _kept_as_is(part, options_done):
            rebased.append(part)
        else:
            absolute = posixpath.normpath(str(cwd / part))
            rebased.append(_relative(Path(absolute), root))
    return shlex.join(rebased)


def _kept_as_is(part: str, options_done: bool) -> bool:
    """Seçenek ya da mutlak/`~` yol: yeniden yazılmaz."""
    is_option = not options_done and part.startswith("-") and len(part) > 1
    return is_option or part.startswith(("/", "~"))


def _relative(path: Path, root: Path) -> str:
    """Köke göreli yol; kökün dışındaysa (ek dizin) mutlak yol."""
    relative = os.path.relpath(os.path.normpath(path), os.path.normpath(root))
    return str(path) if relative.startswith("..") else relative


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def _same(left: Path, right: Path) -> bool:
    return _resolved(left) == _resolved(right)
