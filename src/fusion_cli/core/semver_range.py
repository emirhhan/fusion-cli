"""npm semver aralıkları (Claude Code eklenti `dependencies[].version`, #389). Yalnız stdlib.

Desteklenen: `1.2.3`, `=1.2.3`, `v1.2.3`, `>`, `>=`, `<`, `<=`, `^`, `~`, `*`/`x`/`X`, `1.x`,
`1.2.*`, kısmi `1`/`1.2`, tire aralığı `1.2.3 - 2.3.4`, boşlukla VE, `||` ile VEYA. Ön sürüm
(`1.0.0-beta.1`) yalnız aralıkta aynı `major.minor.patch`'li bir ön sürüm karşılaştırıcısı varsa
eşleşir (npm kuralı). `intersect` Claude'un bağımlı eklentilerin aralıklarını birleştirmesi gibi
VE'ler; hiçbir sürüm hepsini karşılamazsa `None`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_VERSION = re.compile(
    r"^\s*[=v]*\s*(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?\s*$"
)
_PARTIAL = re.compile(
    r"^[=v]*(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?(?:-([0-9A-Za-z.-]+))?$"
)
_OPERATOR = re.compile(r"^(<=|>=|<|>|=|\^|~>?)?\s*(.*)$")


@dataclass(frozen=True, slots=True, order=True)
class Version:
    major: int
    minor: int
    patch: int
    pre: tuple[tuple[int, int | str], ...] = ()

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def key(self) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
        # Ön sürümsüz sürüm aynı çekirdekli ön sürümden büyüktür.
        return (*self.core, 0 if self.pre else 1, self.pre)

    def __str__(self) -> str:
        text = ".".join(str(n) for n in self.core)
        return text + ("-" + ".".join(str(p[1]) for p in self.pre) if self.pre else "")


def _pre(text: str | None) -> tuple[tuple[int, int | str], ...]:
    if not text:
        return ()
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in text.split("."))


def parse_version(text: str) -> Version | None:
    """`1.2.3`, `v1.2.3-rc.1` → `Version`; geçersizse `None` (npm `semver.clean`)."""
    match = _VERSION.match(text)
    if not match:
        return None
    major, minor, patch, pre = match.groups()
    return Version(int(major), int(minor), int(patch), _pre(pre))


Comparator = tuple[str, Version]


def _lower(parts: list[int | None], pre: str | None) -> Version:
    nums = [p or 0 for p in parts]
    return Version(nums[0], nums[1], nums[2], _pre(pre))


def _bump(parts: list[int | None]) -> Version:
    """Kısmi sürümün bir üstü: `1` → `2.0.0`, `1.2` → `1.3.0`."""
    if parts[1] is None:
        return Version((parts[0] or 0) + 1, 0, 0, ((0, 0),))
    return Version(parts[0] or 0, parts[1] + 1, 0, ((0, 0),))


def _parts(text: str) -> tuple[list[int | None], str | None] | None:
    match = _PARTIAL.match(text)
    if not match:
        return None
    raw = match.groups()[:3]
    parts: list[int | None] = []
    for value in raw:
        if value is None or value in {"x", "X", "*"}:
            parts.append(None)
        else:
            parts.append(int(value))
    for index in range(1, 3):  # `1.x.3` → `1.x.x`
        if parts[index - 1] is None:
            parts[index] = None
    return parts, match.group(4)


def _caret(parts: list[int | None], pre: str | None) -> list[Comparator]:
    low = _lower(parts, pre)
    if parts[1] is None:
        return [(">=", low), ("<", Version(low.major + 1, 0, 0, ((0, 0),)))]
    if low.major > 0:
        high = Version(low.major + 1, 0, 0, ((0, 0),))
    elif parts[2] is None or low.minor > 0:
        high = Version(0, low.minor + 1, 0, ((0, 0),))
    else:
        high = Version(0, 0, low.patch + 1, ((0, 0),))
    return [(">=", low), ("<", high)]


def _comparators(token: str) -> list[Comparator] | None:
    match = _OPERATOR.match(token)
    if match is None:
        return None
    op, rest = match.group(1) or "", match.group(2).strip()
    empty: tuple[list[int | None], str | None] = ([None, None, None], None)
    parsed = _parts(rest) if rest else empty
    if parsed is None:
        return None
    parts, pre = parsed
    if parts[0] is None:
        return [("<", Version(0, 0, 0, ((0, 0),)))] if op in {"<", ">"} else []
    full = parts[2] is not None
    if op == "^":
        return _caret(parts, pre)
    if op in {"~", "~>"}:
        high = _bump(parts if parts[1] is None else [parts[0], parts[1], None])
        return [(">=", _lower(parts, pre)), ("<", high)]
    if full:
        return [(op or "=", _lower(parts, pre))]
    if op in {"", "="}:
        return [(">=", _lower(parts, pre)), ("<", _bump(parts))]
    if op == ">":
        return [(">=", _bump(parts))]
    if op == "<=":
        return [("<", _bump(parts))]
    return [(op, _lower(parts, pre))]  # `>=1.2`, `<1.2`


def _set(text: str) -> list[Comparator] | None:
    text = re.sub(r"(<=|>=|<|>|=|\^|~>?)\s+", r"\1", text.strip())
    hyphen = re.match(r"^(\S+)\s+-\s+(\S+)$", text)
    if hyphen:
        low = _comparators(">=" + hyphen.group(1))
        high = _parts(hyphen.group(2).lstrip("=v"))
        if low is None or high is None:
            return None
        parts, pre = high
        top = [("<=", _lower(parts, pre))] if parts[2] is not None else [("<", _bump(parts))]
        return [*low, *(top if parts[0] is not None else [])]
    found: list[Comparator] = []
    for token in text.split():
        parsed = _comparators(token)
        if parsed is None:
            return None
        found.extend(parsed)
    return found


def parse_range(text: str) -> list[list[Comparator]] | None:
    """`||` ile ayrılmış VE kümeleri; geçersizse `None`."""
    sets = [_set(part) for part in (text or "*").split("||")]
    if any(s is None for s in sets):
        return None
    return [s for s in sets if s is not None]


def _test(op: str, have: Version, want: Version) -> bool:
    left, right = have.key(), want.key()
    return {
        "=": left == right,
        ">": left > right,
        ">=": left >= right,
        "<": left < right,
        "<=": left <= right,
    }[op]


def _set_ok(comparators: list[Comparator], version: Version) -> bool:
    if not all(_test(op, version, want) for op, want in comparators):
        return False
    if not version.pre:
        return True
    return any(want.pre and want.core == version.core for _, want in comparators)


def satisfies(version: str | Version, text: str) -> bool:
    found = parse_version(version) if isinstance(version, str) else version
    sets = parse_range(text)
    if found is None or sets is None:
        return False
    return any(_set_ok(s, found) for s in sets)


def max_satisfying(versions: Iterable[str], text: str) -> str | None:
    ok = [(v, parsed) for v in versions if (parsed := parse_version(v)) and satisfies(parsed, text)]
    return max(ok, key=lambda pair: pair[1].key())[0] if ok else None


def is_valid_range(text: str) -> bool:
    return parse_range(text) is not None


def intersect(ranges: Iterable[str]) -> str | None:
    """Aralıkların VE'si (`^1.2 ^1.4` → `>=1.4.0 <2.0.0-0` eşdeğeri metin); çelişirse `None`."""
    items = [r.strip() for r in ranges if r.strip() and r.strip() != "*"]
    if not items:
        return "*"
    conjuncts = [""]
    for item in items:
        options = [p.strip() for p in item.split("||")]
        conjuncts = [f"{c} {o}".strip() for c in conjuncts for o in options]
    alive = [c for c in conjuncts if _lowest(c) is not None]
    return " || ".join(alive) if alive else None


def _lowest(text: str) -> Version | None:
    """Kümenin en küçük olası sürümü (yoksa `None`): çelişki denetimi."""
    sets = parse_range(text)
    if not sets:
        return None
    (comparators,) = sets[:1]
    low = Version(0, 0, 0)
    for op, want in comparators:
        if op in {">=", "="} and want.key() > low.key():
            low = want
        elif op == ">" and want.key() >= low.key():
            low = Version(want.major, want.minor, want.patch + 1)
    return low if _set_ok(comparators, low) or _set_ok(comparators, _strip(low)) else None


def _strip(version: Version) -> Version:
    return Version(*version.core)


__all__ = ["Version", "intersect", "is_valid_range", "max_satisfying", "parse_version", "satisfies"]
