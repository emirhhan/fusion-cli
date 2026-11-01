"""Kabuk komutunun adını verdiği dosyalar: Read/Edit kurallarının kabuğa uygulanması (#44, #59).

Claude Code (code.claude.com/docs/en/permissions#what-read-and-edit-rules-cover): Read ve
Edit deny kuralları tanınan dosya komutlarına (`cat`, `head`, `tail`, `sed`, `tee`…) ve
yönlendirme hedeflerine de uygulanır: `> x`, `>> x`, `2> x` ve `tee x` Edit, `< x` Read
kurallarıyla denetlenir. Dosyayı ADIYLA anmayan komut (`grep -r x .`) ya da dosyayı kendi
açan betik kapsanmaz; o güvence sandbox'tadır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .auto_policy import command_words, written_files

#: Argümanlarını OKUYAN tanınan dosya komutları.
_READERS = frozenset(
    {"cat", "head", "tail", "less", "more", "bat", "nl", "wc", "sort", "uniq", "strings", "xxd"}
)
#: Girdi yönlendirmesi: `< x` (`<<` here-doc, `<<<` here-string, `<&3` sayılmaz).
_INPUT_REDIRECT = re.compile(r"(?<![<\d])<(?![<&(])\s*([^\s;&|<>()]+)")
#: Dosyası olmayan hedefler.
_NO_FILE = frozenset({"/dev/null", "/dev/stdin", "/dev/stdout", "/dev/stderr", "-"})
#: Ayrı sözcük olarak yazılmış yönlendirme işleci (`>`, `>>`, `2>`, `<`): sonraki sözcük hedeftir.
_REDIRECT_OPERATOR = re.compile(r"(?:\d|&)?(?:>{1,2}|<)")
#: Değer alan seçenekler (değeri dosya sanılmasın).
_VALUE_FLAGS = frozenset({"-n", "-c", "-e", "-f", "--lines", "--bytes"})


@dataclass(frozen=True, slots=True)
class ShellFileTargets:
    """Komutun okuduğu ve yazdığı (adıyla andığı) dosyalar."""

    reads: tuple[str, ...]
    writes: tuple[str, ...]


def shell_file_targets(command: str) -> ShellFileTargets:
    reads: list[str] = list(_INPUT_REDIRECT.findall(_strip_quotes(command)))
    writes: list[str] = list(written_files(command))
    for parts in command_words(command):
        name = parts[0].rsplit("/", 1)[-1]
        operands = _operands(parts[1:])
        if name in _READERS:
            reads.extend(operands)
        elif name == "sed":
            in_place = any(p.startswith(("-i", "--in-place")) for p in parts[1:])
            (writes if in_place else reads).extend(_sed_files(parts[1:]))
    return ShellFileTargets(_clean(reads), _clean(writes))


def _operands(arguments: list[str]) -> list[str]:
    found: list[str] = []
    skip = False
    for argument in arguments:
        if skip:
            skip = False
            continue
        if argument in _VALUE_FLAGS or _REDIRECT_OPERATOR.fullmatch(argument):
            skip = True
            continue
        if argument.startswith("-") or argument[:1] in {">", "<"} or argument[:2] in {"2>", "1>"}:
            continue
        found.append(argument)
    return found


def _sed_files(arguments: list[str]) -> list[str]:
    """`sed [-e betik | betik] dosya…`: betik dosya sayılmaz."""
    operands: list[str] = []
    has_script = False
    skip = False
    for argument in arguments:
        if skip:
            skip = False
        elif argument in {"-e", "-f", "--expression", "--file"}:
            has_script = skip = True
        elif not argument.startswith("-"):
            operands.append(argument)
    return operands if has_script else operands[1:]


def _clean(targets: list[str]) -> tuple[str, ...]:
    cleaned = (t.strip("'\"") for t in targets)
    return tuple(dict.fromkeys(t for t in cleaned if t and t not in _NO_FILE and "$" not in t))


def _strip_quotes(command: str) -> str:
    return re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", " ", command)
