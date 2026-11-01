"""Kabuk komutunun adını verdiği dosyalar: Read/Edit kurallarının kabuğa uygulanması (#44, #59).

Claude Code (code.claude.com/docs/en/permissions#what-read-and-edit-rules-cover): Read ve
Edit deny kuralları tanınan dosya komutlarına (`cat`, `head`, `tail`, `sed`, `tee`…) ve
yönlendirme hedeflerine de uygulanır: `> x`, `>> x`, `2> x` ve `tee x` Edit, `< x` Read
kurallarıyla denetlenir. Dosyayı ADIYLA anmayan komut (`grep -r x .`) ya da dosyayı kendi
açan betik kapsanmaz; o güvence sandbox'tadır.

Değer alan seçenekler komut başınadır (`head -n 5` değer, `cat -n` değil). `$HOME`/`${HOME}`
öneki `~` olarak çözülür; başka değişkenli ya da komut ikameli hedef çözülemez (`dynamic`):
Read/Edit kısıtı varken bu komut sorulur (inceleme, 1 Kasım: `cat -n ~/.ssh/id_rsa`,
`tail -f .env`, `cat $HOME/.ssh/id_rsa` deny kuralını aşıyordu).
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
#: Komut başına değer alan seçenekler (değeri dosya sanılmasın); listede olmayan değersizdir.
_VALUE_FLAGS: dict[str, frozenset[str]] = {
    "head": frozenset({"-n", "-c", "--lines", "--bytes"}),
    "tail": frozenset({"-n", "-c", "-s", "--lines", "--bytes", "--pid", "--sleep-interval"}),
    "sort": frozenset(
        {"-k", "-t", "-o", "-S", "-T", "--key", "--field-separator", "--output",
         "--buffer-size", "--temporary-directory", "--parallel", "--batch-size"}
    ),
    "uniq": frozenset({"-f", "-s", "-w", "--skip-fields", "--skip-chars", "--check-chars"}),
    "nl": frozenset({"-b", "-d", "-f", "-h", "-i", "-l", "-n", "-s", "-v", "-w"}),
    "strings": frozenset({"-n", "-t", "-e", "--bytes", "--radix", "--encoding"}),
    "xxd": frozenset({"-c", "-g", "-l", "-o", "-s", "-n", "-cols", "-len", "-seek"}),
    "less": frozenset({"-b", "-h", "-j", "-k", "-o", "-O", "-p", "-P", "-t", "-T", "-x", "-y", "-z"}),
    "bat": frozenset(
        {"-l", "--language", "-H", "--highlight-line", "-r", "--line-range", "--style",
         "--theme", "-m", "--map-syntax", "--tabs", "--wrap", "--terminal-width", "--color",
         "--paging", "--pager", "--decorations", "--italic-text", "--file-name"}
    ),
}  # fmt: skip
_NO_VALUE_FLAGS: frozenset[str] = frozenset()
#: Çözülebilen tek değişken: ev dizini.
_HOME_PREFIX = re.compile(r"^(?:\$HOME|\$\{HOME\})(?=/|$)")


@dataclass(frozen=True, slots=True)
class ShellFileTargets:
    """Komutun okuduğu ve yazdığı (adıyla andığı) dosyalar."""

    reads: tuple[str, ...]
    writes: tuple[str, ...]
    #: Değişkenli ya da komut ikameli, çözülemeyen bir hedef var mı?
    dynamic: bool = False


def shell_file_targets(command: str) -> ShellFileTargets:
    reads: list[str] = list(_INPUT_REDIRECT.findall(_strip_quotes(command)))
    writes: list[str] = list(written_files(command))
    file_command = False
    for parts in command_words(command):
        name = parts[0].rsplit("/", 1)[-1]
        operands = _operands(parts[1:], _VALUE_FLAGS.get(name, _NO_VALUE_FLAGS))
        if name in _READERS:
            file_command = True
            reads.extend(operands)
        elif name == "sed":
            file_command = True
            in_place = any(p.startswith(("-i", "--in-place")) for p in parts[1:])
            (writes if in_place else reads).extend(_sed_files(parts[1:]))
    substituted = file_command and ("$(" in command or "`" in command)
    clean_reads, clean_writes = _clean(reads), _clean(writes)
    dynamic = substituted or any(_dynamic(t) for t in (*clean_reads, *clean_writes))
    return ShellFileTargets(
        tuple(t for t in clean_reads if not _dynamic(t)),
        tuple(t for t in clean_writes if not _dynamic(t)),
        dynamic,
    )


def _operands(arguments: list[str], value_flags: frozenset[str]) -> list[str]:
    found: list[str] = []
    skip = False
    for index, argument in enumerate(arguments):
        if skip:
            skip = False
            continue
        if argument == "--":
            found.extend(arguments[index + 1 :])
            break
        if argument in value_flags or _REDIRECT_OPERATOR.fullmatch(argument):
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
    cleaned = (_HOME_PREFIX.sub("~", t.strip("'\"")) for t in targets)
    return tuple(dict.fromkeys(t for t in cleaned if t and t not in _NO_FILE))


def _dynamic(target: str) -> bool:
    """Hedef kabuk açılımına bağlı mı (`$X`, `` `…` ``, ikameden kalan `(…)`)?"""
    return "$" in target or "`" in target or target.startswith("(")


def _strip_quotes(command: str) -> str:
    return re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", " ", command)
