"""acceptEdits kipinde sormadan çalışan kabuk komutları (#53).

Claude Code (permission-modes#auto-approve-file-edits-with-acceptedits-mode):
dosya düzenlemelerine ek olarak yalnız `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, `sed`
çalışma dizinleri (ve `additionalDirectories`) içindeki yollarda sormadan çalışır. `touch`
dışındakiler güvenli env ataması ya da `timeout`/`nice`/`nohup` önekiyle de geçer; `touch`
yalnız düz dosya yollarıyla. Yerleşik salt okunur küme dışındaki her öteki komut sorulur.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .auto_policy import command_words, is_read_only_command
from .command_paths import escapes_project
from .permission_match import writes_files

#: acceptEdits'in onayladığı dosya sistemi komutları.
FILESYSTEM_COMMANDS = frozenset({"mkdir", "touch", "rm", "rmdir", "mv", "cp", "sed"})
_GLOB_CHARS = frozenset("*?[")


def accept_edits_allows(command: str, root: Path | None, extra_roots: Iterable[Path] = ()) -> bool:
    """Komut acceptEdits'te sorulmadan çalışabilir mi?"""
    if root is None or not command.strip():
        return False
    if is_read_only_command(command):
        return True
    roots = (root, *extra_roots)
    if any(_outside(target, roots) for target in writes_files(command)):
        return False
    if "$(" in command or "`" in command or _unsafe_assignment(command):
        return False
    return all(_segment_ok(words, command, roots) for words in command_words(command))


def _segment_ok(words: list[str], command: str, roots: tuple[Path, ...]) -> bool:
    words = _strip_wrappers(words)
    if not words:
        return False
    if is_read_only_command(" ".join(words)):
        return True
    if words[0] not in FILESYSTEM_COMMANDS:
        return False
    operands = [w for w in words[1:] if not w.startswith("-")]
    if words[0] == "touch" and (
        len(operands) != len(words) - 1
        or any(_GLOB_CHARS & set(w) for w in operands)
        or _BARE_TOUCH.search(command) is None
    ):
        return False
    return not any(_outside(operand, roots) for operand in operands)


#: `touch` önek/atama olmadan, parçanın başında yazılmış mı (`timeout 5 touch x` sorulur).
_BARE_TOUCH = re.compile(r"(?:^|[;&|]\s*)touch\s")
#: Soyulan süreç sarmalayıcıları ve değer alan seçenekleri.
_WRAPPERS = {"timeout": 1, "nice": 0, "nohup": 0, "stdbuf": 0}


def _strip_wrappers(words: list[str]) -> list[str]:
    while words and words[0] in _WRAPPERS:
        rest = words[1:]
        while rest and rest[0].startswith("-"):
            rest = rest[2:] if rest[0] in {"-n", "-k", "-s"} else rest[1:]
        words = rest[_WRAPPERS[words[0]] :]
    return words


#: Önekte sormadan geçen ortam değişkenleri (ötekiyle atama soruya düşer).
SAFE_ENV_NAMES = frozenset(
    {"LANG", "LANGUAGE", "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "NO_COLOR", "FORCE_COLOR", "TZ",
     "TERM", "COLUMNS", "LINES", "CI"}
)  # fmt: skip
_ASSIGNMENT = re.compile(r"(?:^|[;&|(]\s*|\s)([A-Za-z_][A-Za-z0-9_]*)=")


def _unsafe_assignment(command: str) -> bool:
    """Komut başında güvenli listede olmayan bir env ataması var mı?"""
    heads = re.split(r"[;&|\n]+", command)
    for head in heads:
        for name in _ASSIGNMENT.findall(head.split(" -", 1)[0]):
            if name not in SAFE_ENV_NAMES and not name.startswith("LC_"):
                return True
    return False


def _outside(raw: str, roots: tuple[Path, ...]) -> bool:
    return all(escapes_project("cp", [raw], base) for base in roots)
