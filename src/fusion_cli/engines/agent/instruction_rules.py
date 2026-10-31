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

import re
from dataclasses import dataclass
from pathlib import Path

from .instruction_layers import (
    TRIM_NOTE,
    TRUSTED_NOTE,
    UNTRUSTED_NOTE,
    neutralize,
    read_text_limited,
)

#: Tur başında bağlama giren genel kuralların toplam bütçesi (karakter).
MAX_RULES_CHARS = 8_000

#: Kural dosyası başına okunacak en fazla karakter.
MAX_RULE_FILE_CHARS = 4_000

#: Kural dosyası uzantıları (Cursor `.mdc` de kabul edilir).
RULE_SUFFIXES: frozenset[str] = frozenset({".md", ".mdc"})

#: Proje kökleri (köke göreli) — Claude Code ve Fusion adlandırması.
PROJECT_RULE_DIRS: tuple[str, ...] = (".claude/rules", ".fusion/rules")

#: Kullanıcı kökü (ev dizinine göreli).
USER_RULE_DIRS: tuple[str, ...] = (".claude/rules",)

#: Aranmayan dizin adları (bağımlılık ağaçları üçüncü tarafın kuralını taşıyabilir).
_SKIP_DIRS = frozenset({"node_modules", "vendor", "dist", "build", "__pycache__"})

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
    """Kullanıcı (önce) ve proje kural dosyalarını keşfet; `paths:` alanını ayrıştır."""
    found: list[RuleFile] = []
    if home is not None:
        for rel in USER_RULE_DIRS:
            found.extend(_scan(home / rel, base=home, prefix="~/", trusted=True))
    kok = root.resolve()
    for rel in PROJECT_RULE_DIRS:
        found.extend(_scan(kok / rel, base=kok, prefix="", trusted=False))
    return tuple(found)


def _scan(folder: Path, *, base: Path, prefix: str, trusted: bool) -> list[RuleFile]:
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
        # Sembolik bağ kök dışına çıkıyorsa HİÇ açılmaz (üçüncü taraf depo sızdırma yolu).
        if not trusted and not resolved.is_relative_to(bound):
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
        if not sep or key.strip().lower() not in ("paths", "yollar", "globs"):
            continue
        value = value.strip()
        if value:
            inner = value[1:-1] if value.startswith("[") and value.endswith("]") else value
            return tuple(p for p in (_clean(part) for part in inner.split(",")) if p)
        items: list[str] = []
        for rest in lines[index + 1 :]:
            if not rest.lstrip().startswith("-"):
                break
            cleaned = _clean(rest.lstrip()[1:])
            if cleaned:
                items.append(cleaned)
        return tuple(items)
    return ()


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
    """Köke göreli yol desenlerden birine uyuyor mu? Dizinsiz desen dosya adına da bakar."""
    # Yalnız `./` öneki atılır: `lstrip("./")` baştaki noktayı da siliyor, `.github/**` ve
    # `.*rc` desenleri hiç eşleşmiyordu (ölçüldü 31 Ekim).
    rel = relative.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    rel = rel.lstrip("/")
    name = rel.rsplit("/", 1)[-1]
    for pattern in patterns:
        regex = _glob_to_regex(pattern)
        if regex.match(rel) or ("/" not in pattern.rstrip("/") and regex.match(name)):
            return True
    return False


def scoped_rules_for(rules: tuple[RuleFile, ...], relative: str) -> tuple[RuleFile, ...]:
    """Erişilen dosyaya uyan `paths:` kuralları (keşif sırasıyla)."""
    return tuple(r for r in rules if r.is_scoped and matches_paths(r.paths, relative))


# --- Bloklar -------------------------------------------------------------------- #


def rule_block(rule: RuleFile, limit: int = MAX_RULE_FILE_CHARS) -> tuple[str, int]:
    """Tek kuralın bağlam bloğu ve eklenen karakter; okunamıyorsa boş."""
    try:
        text = read_text_limited(rule.path, limit)
    except OSError:
        return "", 0
    text = _FRONTMATTER.sub("", text, count=1).strip()
    if not text:
        return "", 0
    trimmed = len(text) > limit
    text = neutralize(text[:limit])
    tag = "kullanici_kurali" if rule.trusted else "proje_kurali"
    note = TRUSTED_NOTE if rule.trusted else UNTRUSTED_NOTE
    ek = TRIM_NOTE if trimmed else ""
    return f'<{tag} kaynak="{rule.label}">\n{note}\n{text}{ek}\n</{tag}>', len(text)


def unscoped_rules_block(rules: tuple[RuleFile, ...], budget: int = MAX_RULES_CHARS) -> str:
    """`paths:` olmayan kuralların tur başı bloğu; bütçe aşımı açıkça bildirilir."""
    blocks: list[str] = []
    remaining = budget
    skipped: list[str] = []
    for rule in rules:
        if rule.is_scoped:
            continue
        if remaining <= 0:
            skipped.append(rule.label)
            continue
        block, used = rule_block(rule, min(MAX_RULE_FILE_CHARS, remaining))
        if not block:
            continue
        blocks.append(block)
        remaining -= used
    if skipped:
        blocks.append(
            "[…kural bütçesi doldu; okunmayan kurallar: "
            + ", ".join(skipped)
            + " — tamamı için read_file kullan…]"
        )
    return "\n".join(blocks)
