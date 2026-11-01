"""acceptEdits kipinde sormadan çalışan kabuk komutları (#53).

Claude Code (permission-modes#auto-approve-file-edits-with-acceptedits-mode):
dosya düzenlemelerine ek olarak yalnız `mkdir`, `touch`, `rm`, `rmdir`, `mv`, `cp`, `sed`
çalışma dizinleri (ve `additionalDirectories`) içindeki yollarda sormadan çalışır. `touch`
dışındakiler güvenli env ataması ya da `timeout`/`nice`/`nohup` önekiyle de geçer; `touch`
yalnız düz dosya yollarıyla. Yerleşik salt okunur küme dışındaki her öteki komut sorulur.

Yol denetimi seçenek değerlerini de kapsar (`--target-directory=/etc`, `-t/etc`); `sed`
betiği yerinde düzenleme dışında salt okunur olmalıdır: `e`/`w`/`r` komutları, `s///e`,
`s///w` ve `-f` betik dosyası sorulur (inceleme, 1 Kasım: bunlar sorulmadan geçiyordu).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .auto_policy import command_words, is_read_only_command
from .command_paths import escapes_project
from .command_semantics import sed_reads_only
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
    if words[0] == "sed" and not sed_edit_safe(words[1:]):
        return False
    operands = [w for w in words[1:] if not w.startswith("-")]
    if words[0] == "touch" and (
        len(operands) != len(words) - 1
        or any(_GLOB_CHARS & set(w) for w in operands)
        or _BARE_TOUCH.search(command) is None
    ):
        return False
    return not any(_outside(path, roots) for path in _path_words(words))


def _path_words(words: list[str]) -> list[str]:
    """Yol olabilecek her sözcük: işlenenler, `--x=değer` değerleri, `cp/mv -tDİZİN`."""
    found: list[str] = []
    for word in words[1:]:
        if word.startswith("--"):
            if "=" in word:
                found.append(word.split("=", 1)[1])
        elif word.startswith("-") and len(word) > 1:
            body = word[1:]
            if words[0] in {"cp", "mv"} and "t" in body and body.index("t") < len(body) - 1:
                found.append(body[body.index("t") + 1 :])
            elif words[0] == "sed" and body.startswith("i") and "/" in body:
                # GNU: `/` içeren yedek eki bir yol şablonudur (`-ibak/*`).
                found.append(body[1:].replace("*", "x"))
        else:
            found.append(word)
    return found


def sed_edit_safe(arguments: list[str]) -> bool:
    """Yerinde düzenleme (`-i`, `-i.bak`, `-i ''`, `--in-place`) dışında sed salt okunur mu?"""
    stripped: list[str] = []
    drop_empty = False
    for argument in arguments:
        if drop_empty:
            drop_empty = False
            if argument == "":
                continue
        if argument == "--in-place" or argument.startswith("--in-place="):
            continue
        index = _in_place_index(argument)
        if index is None:
            stripped.append(argument)
            continue
        drop_empty = index == len(argument) - 1
        if index > 1:
            stripped.append(argument[:index])
    return sed_reads_only(stripped)


def _in_place_index(argument: str) -> int | None:
    """Kısa bayrak kümesinde `i`nin konumu (`-Ei` → 2); `e`/`f` önce gelirse değer sayılır."""
    if not argument.startswith("-") or argument.startswith("--") or len(argument) < 2:
        return None
    for index, char in enumerate(argument[1:], start=1):
        if char in "ef":
            return None
        if char == "i":
            return index
    return None


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
