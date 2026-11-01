"""Kritik yol `rm`/`rmdir` silmeleri: hiçbir kipin (bypass dahil) sormadan geçirmediği (#42).

Claude Code (code.claude.com/docs/en/permission-modes#critical-paths): hedef şunlardan biriyse
kritik yol silmesidir:

* dosya sistemi kökü ve kökün doğrudan alt dizinleri (`/usr`, `/etc`, `/data`);
* bağlı sürücü kökleri (`/Volumes/<ad>`, `/mnt/<ad>`, `/media/[<kullanıcı>/]<ad>`,
  `/run/media/<kullanıcı>/<ad>`) ve Windows sürücü kökü (`C:\\`);
* ev dizini;
* çalışma dizini ve üst dizinleri;
* ek çalışma dizinleri ve üst dizinleri, YALNIZ silme bunların altında bir glob ise
  (`rm -rf <dizin>/*`);
* kabuk değişkeninin hemen altındaki glob ya da sondaki eğik çizgi (`"$DIR"/*`);
* hedefi yalnız komut ikamesi çıktısı olan özyinelemeli `rm` (`rm -rf "$(pwd)"`);
* yalnız ters bölülerden oluşan hedef.

`CLAUDE_CODE_EVEN_MORE_DANGEROUSLY_SKIP_PERMISSIONS=1` başlangıç ortamındaysa bypass kipinde
bu istem kapanır (yalnız bypass kipinin kendisinde).
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Iterable, Mapping
from pathlib import Path

#: Bypass kipinde kritik yol istemini kapatan başlangıç ortamı değişkeni (Claude adı).
SKIP_CRITICAL_PROMPT_ENV = "CLAUDE_CODE_EVEN_MORE_DANGEROUSLY_SKIP_PERMISSIONS"
CRITICAL_REASON = "Kritik yolda tehlikeli rm işlemi: {yol}"
_REMOVERS = frozenset({"rm", "rmdir"})
_VAR_GLOB = re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/\*?$")
#: Yalnız komut ikamesi: `shell_segments` `$(` önekini `(`e indirir, ikisi de tanınır.
_DRIVE_ROOT = re.compile(r"^[A-Za-z]:[\\/]*$")
#: Bağlı sürücülerin üst dizinleri ve sürücü köküne kadar en çok derinlik.
_MOUNT_PARENTS: tuple[tuple[Path, int], ...] = (
    (Path("/Volumes"), 1),
    (Path("/mnt"), 1),
    (Path("/media"), 2),
    (Path("/run/media"), 2),
)
_SUBSTITUTION_ONLY = re.compile(r"^(?:\$?\(.*\)|`.*`)$", re.DOTALL)


def skip_critical_prompt(environ: Mapping[str, str] | None = None) -> bool:
    """Bypass'ta kritik yol istemi başlangıç ortamıyla kapatıldı mı?"""
    return (environ if environ is not None else os.environ).get(SKIP_CRITICAL_PROMPT_ENV) == "1"


def critical_rm_reason(
    command: str, root: Path | None, extra_roots: Iterable[Path] = (), home: Path | None = None
) -> str | None:
    """Komut tanınan bir kritik yol silmesi içeriyorsa gerekçesi; yoksa `None`."""
    from .permission_match import shell_segments

    home = home or Path.home()
    extras = tuple(extra_roots)
    for segment in shell_segments(command):
        words = _raw_words(segment)
        if not words or words[0].rsplit("/", 1)[-1] not in _REMOVERS:
            continue
        flags = [w for w in words[1:] if w.startswith("-") and w != "-"]
        recursive = any(f in {"-r", "-R", "--recursive"} or _short_has(f, "rR") for f in flags)
        for target in (w for w in words[1:] if not w.startswith("-")):
            if _is_critical(target, recursive, root, extras, home):
                return CRITICAL_REASON.format(yol=target)
    return None


def _raw_words(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=False)
    except ValueError:
        return segment.split()


def _short_has(flag: str, letters: str) -> bool:
    return not flag.startswith("--") and any(letter in flag[1:] for letter in letters)


def _is_critical(
    raw: str, recursive: bool, root: Path | None, extras: tuple[Path, ...], home: Path
) -> bool:
    text = raw.strip("'\"") if not raw.startswith('"$') else raw.replace('"', "")
    if text and set(text) == {"\\"}:
        return True
    if _VAR_GLOB.match(text):
        return True
    if recursive and _SUBSTITUTION_ONLY.match(text):
        return True
    if "$" in text or "`" in text or text.startswith("("):
        return False
    if _DRIVE_ROOT.match(text.rstrip("*")):
        return True
    is_glob = text.endswith("*")
    base_text = text.rstrip("*").rstrip("/") if is_glob else text
    target = _absolute(base_text or ("/" if text.startswith("/") else "."), root, home)
    if target == Path("/") or target.parent == Path("/") or target == home:
        return True
    if _is_mount_root(target):
        return True
    if root is not None and _is_self_or_parent(target, root):
        return True
    return is_glob and any(_is_self_or_parent(target, extra) for extra in extras)


def _is_mount_root(target: Path) -> bool:
    """Bağlı sürücü kökü mü (`/Volumes/USB`, `/media/ali/USB`)?"""
    for parent, depth in _MOUNT_PARENTS:
        if parent in target.parents and len(target.relative_to(parent).parts) <= depth:
            return True
    return False


def _absolute(text: str, root: Path | None, home: Path) -> Path:
    if text == "~" or text.startswith("~/"):
        text = str(home) + text[1:]
    path = Path(text)
    if not path.is_absolute():
        path = (root or Path.cwd()) / path
    return Path(os.path.normpath(path))


def _is_self_or_parent(target: Path, directory: Path) -> bool:
    directory = Path(os.path.normpath(directory))
    return target == directory or target in directory.parents
