"""Bash allow kuralının zincire uygulanması — Claude Code ile birebir (#58, #72).

Kaynak: code.claude.com/docs/en/permissions (Compound commands, Wrappers, Exec wrappers
and `find` actions, What a Bash rule doesn't match).

    Zincir          `&&`, `||`, `;`, `|`, `|&`, `&` ve satır sonundan bölünür; her alt komut
                    bir allow kuralına uymalı ya da yerleşik salt okunur komut olmalıdır.
                    Sonunda boş `&&`/`||` kalan komut ayrıştırılamaz sayılır, onaylanmaz.
    Sarmalayıcı     `timeout`, `time`, `nice`, `nohup`, `stdbuf`, `command` (`-v` hariç),
                    `builtin`, `noglob` ve bayraksız `xargs` soyulur: `Bash(npm test *)`
                    `timeout 30 npm test` komutunu karşılar. Sarmalayıcı ayrı parça değildir.
    Env ataması     Yalnız bilinen güvenli değişkenin baştaki ataması soyulur
                    (`NODE_ENV=test npm test`); başka atamanın ötesine allow geçmez.
    Biçim farkı     Allow tarafında `sh -c '…'`, `sudo …`, `/bin/rm` açılmaz: kural yazılan
                    metni karşılar. (Deny/ask tarafında Fusion bunları AÇAR — Claude'dan sıkı,
                    belgelenmiş Fusion eki; `permission_match.shell_segments`.)
    Exec/find       `watch`, `setsid`, `ionice`, `flock` ve komut çalıştıran/silen/yazan
                    `find` eylemi (`-exec`, `-delete`, `-fprint`, `-files0-from`…) yalnız
                    `*` içermeyen birebir kuralla onaylanır.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable

from ..config.permission_rules import PermissionDecision, PermissionRule
from .auto_policy import is_read_only_command, raw_segments
from .permission_patterns import bash_pattern_matches

#: Soyulan süreç sarmalayıcıları → değer alan seçenekleri ve atlanacak konumsal sayısı.
_WRAPPERS: dict[str, tuple[frozenset[str], int]] = {
    "timeout": (frozenset({"-s", "-k", "--signal", "--kill-after"}), 1),
    "time": (frozenset(), 0),
    "nice": (frozenset({"-n", "--adjustment"}), 0),
    "nohup": (frozenset(), 0),
    "stdbuf": (frozenset({"-i", "-o", "-e", "--input", "--output", "--error"}), 0),
    "builtin": (frozenset(), 0),
    "noglob": (frozenset(), 0),
}
#: Komut çalıştıran sarmalayıcılar: önek kuralı onaylamaz (#72).
EXEC_WRAPPERS = frozenset({"watch", "setsid", "ionice", "flock"})
#: Komut çalıştıran, silen ya da yazan `find` eylemleri (#72).
FIND_ACTIONS = frozenset(
    {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-rm", "-fprint", "-fprint0",
     "-fprintf", "-fls", "-files0-from"}
)  # fmt: skip
#: Baştaki ataması soyulan, bilinen güvenli ortam değişkenleri.
SAFE_ENV_NAMES = frozenset(
    {"NODE_ENV", "RAILS_ENV", "RACK_ENV", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE",
     "NO_COLOR", "FORCE_COLOR", "CI", "TZ", "LANG", "LANGUAGE", "TERM", "COLUMNS", "LINES",
     "DEBUG", "RUST_BACKTRACE", "RUST_LOG", "GOOS", "GOARCH", "CGO_ENABLED"}
)  # fmt: skip
_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
#: Ayrıştırıcının parça başında bıraktığı denetim akışı sözcükleri.
_FLOW_WORDS = frozenset({"then", "do", "else", "!", "{"})
_UNPARSEABLE_TAIL = re.compile(r"(?:&&|\|\|)\s*$")
#: Çöpe/hataya yönlendirme yazma değildir; bölmeden önce atılır (`2>&1` `&`ten bölünmesin).
_NULL_REDIRECTS = re.compile(r"\d?>\s*/dev/null|2>&1|&>\s*/dev/null")


def allow_segments(command: str) -> list[str] | None:
    """Allow kuralına karşı denenecek alt komutlar; ayrıştırılamıyorsa `None`."""
    if _UNPARSEABLE_TAIL.search(command):
        return None
    found = [" ".join(words) for words in _segment_words(command)]
    return found or None


def needs_exact_rule(segment: str) -> bool:
    """Alt komut yalnız `*`'sız birebir kuralla onaylanabilir mi (#72)?"""
    words = _split(segment)
    if not words:
        return False
    if words[0] in EXEC_WRAPPERS:
        return True
    return words[0] == "find" and any(word in FIND_ACTIONS for word in words[1:])


def allow_rule_for(rules: Iterable[PermissionRule], segment: str) -> PermissionRule | None:
    """Alt komutu onaylayan ilk allow kuralı (belirteçsiz `Bash` her şeyi onaylar)."""
    exact_only = needs_exact_rule(segment)
    for rule in rules:
        if rule.decision is not PermissionDecision.ALLOW:
            continue
        if rule.specifier is None:
            if not exact_only:
                return rule
            continue
        if exact_only:
            if "*" not in rule.specifier and rule.specifier == segment:
                return rule
            continue
        if bash_pattern_matches(rule.specifier, segment):
            return rule
    return None


def allowing_rule(rules: Iterable[PermissionRule], command: str) -> PermissionRule | None:
    """Zinciri bütünüyle onaylayan kural: her alt komut kurala uyar ya da salt okunurdur.

    Hiçbir alt komut kurala uymuyorsa (hepsi salt okunur) `None`: karar kipe kalır.
    """
    segments = allow_segments(command)
    if segments is None:
        return None
    rules = tuple(rules)
    first: PermissionRule | None = None
    for segment in segments:
        rule = allow_rule_for(rules, segment)
        if rule is None:
            if needs_exact_rule(segment) or not is_read_only_command(segment):
                return None
            continue
        first = first or rule
    return first


def _segment_words(command: str) -> list[list[str]]:
    found = []
    for segment in raw_segments(_NULL_REDIRECTS.sub("", command)):
        words = _strip(_split(segment))
        if words:
            found.append(words)
    return found


def _split(segment: str) -> list[str]:
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def _strip(words: list[str]) -> list[str]:
    """Güvenli env atamalarını ve sabit sarmalayıcıları baştan soy (değişmeyene dek)."""
    while words:
        head = words[0]
        assignment = _ASSIGNMENT.match(head)
        if head in _FLOW_WORDS:
            words = words[1:]
        elif assignment is not None:
            if assignment.group(1) not in SAFE_ENV_NAMES or len(words) == 1:
                return words
            words = words[1:]
        elif head == "command" and len(words) > 1 and words[1] not in {"-v", "-V"}:
            words = words[2:] if words[1] == "-p" else words[1:]
        elif head == "xargs" and len(words) > 1 and not words[1].startswith("-"):
            words = words[1:]
        elif head in _WRAPPERS and len(words) > 1:
            words = _drop_wrapper(head, words[1:])
        else:
            return words
    return words


def _drop_wrapper(name: str, rest: list[str]) -> list[str]:
    value_flags, skip = _WRAPPERS[name]
    while rest and rest[0].startswith("-") and len(rest[0]) > 1:
        rest = rest[2:] if rest[0] in value_flags else rest[1:]
    return rest[skip:]

