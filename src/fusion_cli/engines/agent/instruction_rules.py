"""`.claude/rules/` kural dosyaları: yol kapsamlı (`paths:`) ve genel kurallar.

Claude Code `.claude/rules/**/*.md` dosyalarını özyinelemeli yükler; `paths:` frontmatter'ı
olanlar yalnız eşleşen dosyaya dokunulduğunda devreye girer; `~/.claude/rules` kullanıcı
kurallarıdır. Fusion aynı kökleri okur ve iki anda bağlama ekler:

- `paths:` olmayan kurallar TUR BAŞINDA (`unscoped_rules_block`, bütçe `MAX_RULES_CHARS`);
- `paths:` olanlar model eşleşen dosyaya ERİŞİNCE bir kez (`scoped_rules_for`, iç içe
  talimat kancasıyla aynı yol — bkz. `project_instructions.load_nested_instructions`).

Ölçüldü (31 Ekim): `.claude/rules` hiç taranmıyordu. Güven: kullanıcı kökü güvenilir
(`<kullanici_kurali>`), proje kökleri depo içeriğidir (`<proje_kurali>`); kök dışına çıkan
sembolik bağ hiç açılmaz.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .instruction_layers import (
    TRIM_NOTE,
    InstructionFile,
    InstructionLoad,
    instruction_files_mode,
    read_text_limited,
)

#: Claude Code (#154): kökte yüklenen kurallarda karakter bütçesi yok; dosya 4 MiB'a kadar.
MAX_RULES_CHARS = 4 * 1024 * 1024

#: Kural dosyası başına okunacak en fazla karakter (başlangıç kuralı: 4 MiB).
MAX_RULE_FILE_CHARS = 4 * 1024 * 1024

#: Diagnostic-only reads share the existing file cap and stop between bounded chunks.
RULE_MEASUREMENT_SECONDS = 0.05

#: İsteğe bağlı (`paths:`) kural dosyası başına sınır (Claude Code: 200K pencerede 40.000).
MAX_SCOPED_RULE_CHARS = 40_000

#: Kural dosyası uzantısı (Claude Code yalnız `.md`; #156).
RULE_SUFFIXES: frozenset[str] = frozenset({".md"})

#: Proje kökleri (köke göreli). `.fusion/rules` kullanımdan kalktı: bir sürüm okunur, uyarılır.
PROJECT_RULE_DIRS: tuple[str, ...] = (".claude/rules", ".fusion/rules")
DEPRECATED_RULE_DIRS = frozenset({".fusion/rules"})

#: `paths` brace açılımı bütçesi (kural başına): 1.000 desen.
MAX_BRACE_PATTERNS = 1_000

#: Kullanıcı kökü (ev dizinine göreli).
USER_RULE_DIRS: tuple[str, ...] = (".claude/rules",)

#: Aranmayan dizin adları (bağımlılık ağaçları üçüncü tarafın kuralını taşıyabilir).
_SKIP_DIRS = frozenset({"node_modules", "vendor", "dist", "build", "__pycache__"})

_LOG = logging.getLogger(__name__)

_FRONTMATTER = re.compile(r"\A\s*---\n(.*?)\n---\n?", re.DOTALL)


@dataclass(frozen=True, slots=True)
class RuleFile:
    """Keşfedilen tek bir kural dosyası."""

    #: Gösterilen ad: `~/.claude/rules/x.md` ya da köke göreli `.claude/rules/x.md`.
    label: str
    path: Path
    #: `paths:` desenleri; boşsa kural her zaman geçerlidir ve tur başında yüklenir.
    paths: tuple[str, ...]
    trusted: bool

    @property
    def is_scoped(self) -> bool:
        return bool(self.paths)


def discover_rules(root: Path, home: Path | None) -> tuple[RuleFile, ...]:
    """Kullanıcı (önce) ve proje kural dosyalarını keşfet; `paths:` alanını ayrıştır.

    `claudeMdExcludes` kural dosyalarına da uygulanır (#152). Kök dışını gösteren proje
    kuralı sembolik bağı, dış import onayı verilmişse yüklenir (#155).
    """
    from ...config import claude_settings
    from .claude_md_imports import external_import_decision

    if instruction_files_mode(root, home) == "managed-only":
        return ()
    found: list[RuleFile] = []
    if home is not None:
        for rel in USER_RULE_DIRS:
            found.extend(_scan(home / rel, base=home, prefix="~/", trusted=True))
    kok = root.resolve()
    external_ok = external_import_decision(kok) is True
    for rel in PROJECT_RULE_DIRS:
        if rel in DEPRECATED_RULE_DIRS and (kok / rel).is_dir():
            _LOG.warning("%s kullanımdan kalktı; kuralları .claude/rules altına taşı", kok / rel)
        found.extend(_scan(kok / rel, base=kok, prefix="", trusted=False, external_ok=external_ok))
    excludes = claude_settings.merged_list(kok, home, "claudeMdExcludes")
    return tuple(rule for rule in found if not _excluded(rule.path, excludes))


def _excluded(path: Path, patterns: tuple[str, ...]) -> bool:
    import fnmatch

    try:
        text = str(path.resolve())
    except OSError:
        text = str(path)
    return any(fnmatch.fnmatch(text, pattern) for pattern in patterns)


def _scan(
    folder: Path, *, base: Path, prefix: str, trusted: bool, external_ok: bool = False
) -> list[RuleFile]:
    if not folder.is_dir():
        return []
    bound = base.resolve()
    rules: list[RuleFile] = []
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in RULE_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in path.relative_to(folder).parts):
            continue
        try:
            resolved = path.resolve()
            if not resolved.is_file():
                continue
        except OSError:
            continue
        # Kök dışına çıkan sembolik bağ dış import gibidir: proje başına onay gerekir (#155).
        if not trusted and not external_ok and not resolved.is_relative_to(bound):
            continue
        label = prefix + path.relative_to(base).as_posix()
        rules.append(RuleFile(label, path, _rule_paths(path), trusted))
    return rules


def _rule_paths(path: Path) -> tuple[str, ...]:
    """Frontmatter'daki `paths:` desenleri: liste bloğu, `[a, b]` ya da tek dize."""
    try:
        head = read_text_limited(path, 2_000)
    except OSError:
        return ()
    match = _FRONTMATTER.match(head)
    if match is None:
        return ()
    lines = match.group(1).splitlines()
    for index, line in enumerate(lines):
        key, sep, value = line.partition(":")
        name = key.strip().lower()
        if not sep or name not in ("paths", "yollar"):
            continue
        if name == "yollar":
            _LOG.warning("kural frontmatter 'yollar' kullanımdan kalktı; 'paths' yaz (%s)", path)
        value = value.strip()
        if value:
            inner = value[1:-1] if value.startswith("[") and value.endswith("]") else value
            return tuple(p for p in (_clean(part) for part in _split_commas(inner)) if p)
        items: list[str] = []
        for rest in lines[index + 1 :]:
            if not rest.lstrip().startswith("-"):
                break
            cleaned = _clean(rest.lstrip()[1:])
            if cleaned:
                items.append(cleaned)
        return tuple(items)
    return ()


def _split_commas(text: str) -> list[str]:
    """Süslü ayraç dışındaki virgüllerde böl (`src/*.{ts,tsx}` tek desen)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        depth += char == "{"
        depth -= char == "}" and depth > 0
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def _clean(value: str) -> str:
    return value.split(" #", 1)[0].strip().strip("'\"")


# --- Eşleşme -------------------------------------------------------------------- #


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Klasik glob → düzenli ifade: `**` dizin aşar, `*` aşmaz, `{a,b}` seçenektir."""
    text = pattern.strip().replace("\\", "/")
    while text.startswith("./"):  # `./src/**` ile `src/**` aynı desen
        text = text[2:]
    if text.endswith("/"):
        text += "**"
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if text.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
            continue
        if text.startswith("**", index):
            out.append(".*")
            index += 2
            continue
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[" and (end := text.find("]", index + 2)) != -1:
            # Köşeli ayraç ifadesi (`[abc]`, `[!x]`) geçerlidir (#154).
            body = text[index + 1 : end]
            negate = body[:1] in ("!", "^")
            body = body[1:] if negate else body
            out.append("[" + ("^" if negate else "") + body.replace("\\", "\\\\") + "]")
            index = end
        elif char == "{":
            end = text.find("}", index)
            if end == -1:
                out.append(re.escape(char))
            else:
                options = text[index + 1 : end].split(",")
                out.append("(?:" + "|".join(re.escape(o.strip()) for o in options) + ")")
                index = end
        else:
            out.append(re.escape(char))
        index += 1
    return re.compile("^" + "".join(out) + "$")


def matches_paths(patterns: tuple[str, ...], relative: str) -> bool:
    """Köke göreli yol desenlerden birine uyuyor mu?

    Claude Code (#154): desen kuralın taban dizinine görelidir; `*.md` yalnız kökteki `.md`
    dosyalarıdır (dizinsiz desen her yerdeki dosya adına uygulanmaz).
    """
    # Yalnız `./` öneki atılır: `lstrip("./")` baştaki noktayı da siliyor, `.github/**` ve
    # `.*rc` desenleri hiç eşleşmiyordu (ölçüldü 31 Ekim).
    rel = relative.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    rel = rel.lstrip("/")
    return any(_glob_to_regex(pattern).match(rel) for pattern in _bounded(patterns))


def _bounded(patterns: tuple[str, ...]) -> tuple[str, ...]:
    """Brace açılımı bütçesi: tüm liste 1.000 açılmış desen; aşan desen hiç eşleşmez."""
    total = 0
    kept: list[str] = []
    for pattern in patterns:
        count = 1
        for group in re.findall(r"\{([^{}]*)\}", pattern):
            count *= max(1, len(group.split(",")))
        if "{" in pattern:
            total += count
            if total > MAX_BRACE_PATTERNS:
                continue  # Claude Code: açılmadan kullanılır, düz ayraç hiçbir dosyaya uymaz
        kept.append(pattern)
    return tuple(kept)


def scoped_rules_for(rules: tuple[RuleFile, ...], relative: str) -> tuple[RuleFile, ...]:
    """Erişilen dosyaya uyan `paths:` kuralları (keşif sırasıyla)."""
    return tuple(r for r in rules if r.is_scoped and matches_paths(r.paths, relative))


# --- Bloklar -------------------------------------------------------------------- #


def _measure_rule_sample(handle: TextIO, prefix: str) -> tuple[str, bool]:
    """Sample at most the existing file cap plus one character; never chase EOF."""
    parts = [prefix]
    consumed = len(prefix)
    cap = MAX_RULE_FILE_CHARS + 1
    deadline = time.monotonic() + RULE_MEASUREMENT_SECONDS
    while consumed < cap and time.monotonic() < deadline:
        chunk = handle.read(min(65_536, cap - consumed))
        if not chunk:
            return "".join(parts), True
        parts.append(chunk)
        consumed += len(chunk)
    return "".join(parts), False


def _rule_content_span(sample: str) -> tuple[int, int, bool]:
    """Locate the sampled body; an unfinished header cannot give a body lower bound."""
    text = sample.lstrip()
    start = len(sample) - len(text)
    frontmatter = _FRONTMATTER.match(text)
    unfinished_header = text.startswith("---\n") and frontmatter is None
    if frontmatter is not None:
        start += frontmatter.end()
        text = text[frontmatter.end() :]
    start += len(text) - len(text.lstrip())
    return start, len(text.strip()), unfinished_header


def _rule_block(rule: RuleFile, limit: int, *, measure: bool = False) -> tuple[str, int, int, bool]:
    """Preserve rendering; measure omissions within a fixed I/O and work budget."""
    content_span: tuple[int, int, bool] | None = None
    exact = True
    try:
        with rule.path.open(encoding="utf-8", errors="replace") as handle:
            prefix = handle.read(limit + 1)
            if measure and len(prefix) > limit:
                sample, exact = _measure_rule_sample(handle, prefix)
                content_span = _rule_content_span(sample)
        text = prefix.strip()
    except OSError:
        return "", 0, 0, True
    frontmatter = _FRONTMATTER.match(text)
    start = len(prefix) - len(prefix.lstrip())
    if frontmatter is not None:
        start += frontmatter.end()
        text = text[frontmatter.end() :]
    start += len(text) - len(text.lstrip())
    text = text.strip()
    if not text:
        return "", 0, 0, True
    trimmed = len(text) > limit
    text = text[:limit]
    ek = TRIM_NOTE if trimmed else ""
    desc = (
        "user's private global instructions for all projects"
        if rule.trusted
        else "project instructions, checked into the codebase"
    )
    block = f"Contents of {rule.path} ({desc}):\n\n{text}{ek}"
    omitted = 0
    if content_span is not None:
        body_start, total, unfinished_header = content_span
        if exact or not unfinished_header:
            included = max(0, min(body_start + total, start + len(text)) - max(body_start, start))
            omitted = total - included
    return block, len(text), omitted, exact


def rule_block(rule: RuleFile, limit: int = MAX_RULE_FILE_CHARS) -> tuple[str, int]:
    """Tek kuralın bağlam bloğu ve eklenen karakter; okunamıyorsa boş."""
    block, used, _, _ = _rule_block(rule, limit)
    return block, used


def load_unscoped_rules(
    rules: tuple[RuleFile, ...], budget: int = MAX_RULES_CHARS
) -> InstructionLoad:
    """Return the exact startup rule text and the files actually included."""
    blocks: list[str] = []
    files: list[InstructionFile] = []
    notes: list[str] = []
    remaining = budget
    skipped: list[str] = []
    for rule in rules:
        if rule.is_scoped:
            continue
        if remaining <= 0:
            skipped.append(rule.label)
            continue
        block, used, trimmed, exact = _rule_block(
            rule, min(MAX_RULE_FILE_CHARS, remaining), measure=True
        )
        if not block:
            continue
        blocks.append(block)
        files.append(
            InstructionFile(
                rule.label, rule.path, "kural", used, trimmed, rule.trusted, trimmed_exact=exact
            )
        )
        if not exact:
            count = f"en az {trimmed}" if trimmed else "bilinmiyor"
            notes.append(
                f"{rule.label}: kırpılan karakter sayısı {count}; kesin ölçüm okuma/süre "
                "sınırında durdu. Talimatın yüklenen bölümü değişmedi."
            )
        remaining -= used
    if skipped:
        blocks.append(
            "[…kural bütçesi doldu; okunmayan kurallar: "
            + ", ".join(skipped)
            + " — tamamı için read_file kullan…]"
        )
    return InstructionLoad("\n".join(blocks), tuple(files), tuple(notes))


def unscoped_rules_block(rules: tuple[RuleFile, ...], budget: int = MAX_RULES_CHARS) -> str:
    """`paths:` olmayan kuralların tur başı bloğu; bütçe aşımı açıkça bildirilir."""
    return load_unscoped_rules(rules, budget).text
