"""Salt okunur kabuk komutunun çalışma dizinleri dışını okuması (#56).

Claude Code'da çalışma dizini içindeki okuma sorulmaz; dışarıyı okuyan çağrı Manuel,
acceptEdits ve plan kipinde sorulur (dontAsk reddeder, auto/bypass sormaz). Kabukta bu
`cat ~/.ssh/config`, `ls /etc`, `head ../komsu/x` gibi salt okunur komutlardır: Fusion onları
okuma aracı gibi değerlendirir. Yalnız yol gibi görünen sözcüklere bakılır (`/`, `~` ile
başlayan ya da `..` içeren); göreli yalın ad çalışma dizinindedir. `$HOME`/`${HOME}` öneki ev
dizinine çözülür; başka değişkenli ya da ikameli sözcük çözülemez ve dışarıda sayılır
(inceleme, 1 Kasım: `cat $HOME/.ssh/id_rsa` 'içeride' sayılıp sorulmuyordu).
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable
from pathlib import Path

from .auto_policy import is_read_only_command

_HOME_PREFIX = re.compile(r"^(?:\$HOME|\$\{HOME\})(?=/|$)")


def shell_outside_read_target(
    command: str, root: Path | None, extra_roots: Iterable[Path] = ()
) -> str | None:
    """Salt okunur komut çalışma dizinleri dışında bir yol okuyorsa o yol; değilse `None`."""
    if root is None or not command.strip() or not is_read_only_command(command):
        return None
    from .permission_match import shell_segments

    try:
        allowed = [root.resolve(), *(Path(extra).resolve() for extra in extra_roots)]
    except (OSError, RuntimeError):
        return None
    for segment in shell_segments(command):
        for word in _words(segment)[1:]:
            target = _outside(word, root, allowed)
            if target is not None:
                return target
    return None


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _outside(word: str, root: Path, allowed: list[Path]) -> str | None:
    if word.startswith("-"):
        return None
    word = _HOME_PREFIX.sub("~", word)
    if "$" in word or "`" in word:
        return word
    if not (word.startswith(("/", "~")) or ".." in Path(word).parts):
        return None
    try:
        path = Path(word).expanduser()
        target = (path if path.is_absolute() else root / path).resolve()
    except (OSError, RuntimeError, ValueError):
        return word
    if any(target == base or base in target.parents for base in allowed):
        return None
    return str(target)
