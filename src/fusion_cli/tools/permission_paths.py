"""Read/Edit yol kalıpları: dayanak noktası, derinlik, symlink ve `!` olumsuzlama.

Claude Code belgesiyle birebir (code.claude.com/docs/en/permissions#read-and-edit):

    //yol        dosya sistemi kökü
    ~/yol        ev dizini
    /yol         AYAR KAYNAĞINA göre: kullanıcı ayarında `~/.claude/yol`, proje/yerel
                 ayarda, CLI bayrağında ve oturum kuralında birincil çalışma dizini (#45)
    yol, ./yol   geçerli dizin

Derinlik (gitignore): eğik çizgisiz kalıp (`.env`, `*.env`) her derinlikte eşleşir; tek
dizin bölümlü `secrets/**` deny/ask kuralında her derinlikteki `secrets` dizinini,
allow kuralında yalnız `<cwd>/secrets`i karşılar (#45). Symlink: allow kuralı istenen yol
da çözülen hedef de eşleşirse, deny/ask ikisinden biri eşleşirse uyar (#61).
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path, PurePosixPath

from ..config.flag_settings_anchor import FLAG_LAYER_SOURCES, flag_settings_dir
from ..config.permission_rules import LAYER_USER, PermissionDecision, PermissionRule

#: Kullanıcı ayarındaki `/yol` kalıbının dayanağı (`~/.claude`).
_USER_ANCHOR = Path(".claude")


def path_rule_matches(rule: PermissionRule, raw: object, root: Path | None) -> bool:
    """Kuralın yol belirteci hedef yolu karşılıyor mu (karar türüne göre symlink kuralı)?"""
    spec = rule.specifier
    if not spec or spec.startswith("!") or not isinstance(raw, str) or not raw.strip():
        return False
    targets = variants(absolute(raw, root))
    patterns = _patterns(rule, root)
    if rule.decision is PermissionDecision.ALLOW:
        resolved = _resolved_only(absolute(raw, root))
        lexical = PurePosixPath(os.path.normpath(absolute(raw, root))).as_posix()
        return all(any(p.fullmatch(t) for p in patterns) for t in {lexical, *resolved})
    return any(p.fullmatch(t) for p in patterns for t in targets)


def plain_path_matches(spec: str, raw: object, root: Path | None) -> bool:
    """Kaynaksız, derinlik kuralsız eşleme (ör. `Cd`: tüm dizin yoluna tutturulur)."""
    if not isinstance(raw, str) or not raw.strip():
        return False
    targets = variants(absolute(raw, root))
    patterns = {
        glob_regex(pattern)
        for base, rest in glob_base(spec, root)
        for pattern in variants(base, rest)
    }
    return any(p.fullmatch(t) for p in patterns for t in targets)


def negated(
    rule: PermissionRule, later: Sequence[PermissionRule], raw: object, root: Path | None
) -> bool:
    """Aynı kaynakta SONRA gelen `!kalıp` bu yolu kuraldan oyuyor mu (#79)?

    Yalnız `yol`/`./yol` kurallarından oyulur; `/`, `~/`, `//` dayanaklı kural ve dizini
    bütünüyle kapatan (`x/**`) kural oyulamaz. `!` kalıbı geçerli dizine göre okunur.
    """
    spec = rule.specifier or ""
    if spec.startswith(("/", "~")) or spec.endswith("/**"):
        return False
    for other in later:
        body = (other.specifier or "")[1:]
        if (
            other.specifier
            and other.specifier.startswith("!")
            and other.tool == rule.tool
            and other.decision is rule.decision
            and other.source == rule.source
            and body
        ):
            carve = PermissionRule(other.tool, body.lstrip("/~"), other.decision, other.source)
            if path_rule_matches(carve, raw, root):
                return True
    return False


def absolute(raw: str, root: Path | None) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (root or Path.cwd()) / path


def variants(base: Path, rest: str = "") -> set[str]:
    """Sözcüksel ve symlink'leri çözülmüş biçimleri (posix); çözülemeyen atlanır."""
    found = {PurePosixPath(os.path.normpath(base)).as_posix()}
    with contextlib.suppress(OSError, RuntimeError, ValueError):
        found.add(PurePosixPath(base.resolve()).as_posix())
    return {(PurePosixPath(item) / rest).as_posix() if rest else item for item in found}


def _resolved_only(path: Path) -> set[str]:
    with contextlib.suppress(OSError, RuntimeError, ValueError):
        return {PurePosixPath(path.resolve()).as_posix()}
    return set()


def glob_base(spec: str, root: Path | None, source: str = "") -> tuple[tuple[Path, str], ...]:
    """Belirteci (taban, kalan glob) çiftine çevir; `/x` ayar kaynağına bağlanır."""
    if spec.startswith("//"):
        return ((Path("/"), spec[2:]),)
    if spec.startswith("~"):
        return ((Path.home(), spec[1:].lstrip("/")),)
    if spec.startswith("/") and source == LAYER_USER:
        return ((Path.home() / _USER_ANCHOR, spec.lstrip("/")),)
    if spec.startswith("/") and source in FLAG_LAYER_SOURCES:
        # `--settings <dosya>` kuralı o dosyanın dizinine bağlanır (#45); satır içi JSON köke.
        anchor = flag_settings_dir()
        if anchor is not None:
            return ((anchor, spec.lstrip("/")),)
    return (((root or Path.cwd()), spec.lstrip("/")),)


def _patterns(rule: PermissionRule, root: Path | None) -> set[re.Pattern[str]]:
    spec = rule.specifier or ""
    found: set[re.Pattern[str]] = set()
    for base, rest in glob_base(spec, root, rule.source):
        for shape in _depth_shapes(spec, rest, rule.decision):
            found.update(glob_regex(pattern) for pattern in _pattern_variants(base, shape))
    return found


def _pattern_variants(base: Path, shape: str) -> set[str]:
    """Kalıbın globsuz önekini de çöz: `//tmp/*.log` macOS'ta `/private/tmp/*.log`ı da kapsar."""
    segments = shape.split("/")
    literal: list[str] = []
    for segment in segments:
        if any(char in segment for char in "*?["):
            break
        literal.append(segment)
    remainder = "/".join(segments[len(literal) :])
    head = base.joinpath(*[s for s in literal if s]) if literal else base
    return variants(head, remainder) | variants(base, shape)


def _depth_shapes(spec: str, rest: str, decision: PermissionDecision) -> tuple[str, ...]:
    """gitignore derinliği: eğik çizgisiz ad her derinlikte; tek bölümlü dizin deny/ask'te."""
    if spec.startswith(("/", "~", "./")) or rest.startswith("**"):
        return (rest,)
    if "/" not in rest:
        return (rest, f"**/{rest}")
    head, _, tail = rest.partition("/")
    if tail == "**" and decision is not PermissionDecision.ALLOW and "*" not in head:
        return (rest, f"**/{rest}")
    return (rest,)


@lru_cache(maxsize=1024)
def glob_regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if pattern.startswith("**", index):
            # `**/` ve `/**` sıfır ya da daha çok dizini kapsar; sondaki `dizin/**`
            # dizinin KENDİSİNİ de kapsar (listelemek içini okumaktır).
            index += 2
            if index < len(pattern) and pattern[index] == "/":
                index += 1
                parts.append("(?:.*/)?")
            elif index == len(pattern) and parts and parts[-1] == "/":
                parts[-1] = "(?:/.*)?"
            else:
                parts.append(".*")
            continue
        if char == "*":
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    return re.compile("".join(parts))
