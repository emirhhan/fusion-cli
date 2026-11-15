"""Alt dizin talimatlarının Claude Code kuralları (#150).

Belge (code.claude.com/docs/en/memory, "How CLAUDE.md files load"): alt dizindeki CLAUDE.md,
CLAUDE.local.md ve o dizinin `.claude/rules/` dosyaları Claude o dizinde bir dosyayı
okuyunca/yazınca/düzenleyince yüklenir; kabukla tek dosya okuma (`cat`, `head`…) da sayılır.
Dosya başı sınır 200K pencerede 40.000, 1M pencerede 150.000 karakterdir.

Bu modül: (1) alt dizinin `.claude/rules` dosyalarını bulur (`paths` deseni o dizine
göreli), (2) `run_shell` komutundan tek dosyalı okuma hedefini çıkarır, (3) pencereye göre
dosya başı sınırı verir.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .instruction_rules import RuleFile, _scan, matches_paths

#: 200K pencere: dosya başı 40.000; 1M pencere: 150.000 karakter.
NESTED_MAX_CHARS = 40_000
NESTED_MAX_CHARS_1M = 150_000
LARGE_WINDOW_TOKENS = 1_000_000

#: Tek dosya okuma sayılan kabuk komutları.
SHELL_READERS = frozenset({"cat", "head", "tail", "less", "more", "bat", "nl", "wc"})

#: Alt dizin taramasında atlanan dizinler (bağımlılık/üretim ağaçları ve `.git`).
SKIP_DIRS = frozenset(
    {"node_modules", "vendor", "site-packages", "dist", "build", "target", "__pycache__", ".git"}
)


def max_chars_for_window(window_tokens: int | None) -> int:
    """Pencereye göre iç içe talimat dosyası başı sınır."""
    if window_tokens and window_tokens >= LARGE_WINDOW_TOKENS:
        return NESTED_MAX_CHARS_1M
    return NESTED_MAX_CHARS


def shell_read_target(command: str) -> str | None:
    """`cat a/b.md`, `head -n 20 x.py` gibi tek dosyalı okumanın hedefi; değilse `None`."""
    if any(mark in command for mark in ("|", ";", "&&", "||", ">", "<", "`", "$(")):
        return None
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if not parts or Path(parts[0]).name not in SHELL_READERS:
        return None
    operands: list[str] = []
    skip_next = False
    for part in parts[1:]:
        if skip_next:
            skip_next = False
            continue
        if part in ("-n", "-c", "--lines", "--bytes"):
            skip_next = True
            continue
        if part.startswith("-"):
            continue
        operands.append(part)
    return operands[0] if len(operands) == 1 else None


def nested_rule_files(root: Path, target: Path) -> tuple[RuleFile, ...]:
    """Hedefin klasöründen köke (kök HARİÇ) her dizinin `.claude/rules` dosyaları, dış → iç."""
    kok = root.resolve()
    try:
        gercek = target.resolve()
    except (OSError, RuntimeError):
        return ()
    if not gercek.is_relative_to(kok):
        return ()
    klasor = gercek if gercek.is_dir() else gercek.parent
    parcalar = klasor.relative_to(kok).parts
    if any(part in SKIP_DIRS for part in parcalar):
        return ()
    found: list[RuleFile] = []
    for derinlik in range(1, len(parcalar) + 1):
        dizin = kok.joinpath(*parcalar[:derinlik])
        found.extend(_scan(dizin / ".claude" / "rules", base=kok, prefix="", trusted=False))
    return tuple(found)


def applies(rule: RuleFile, root: Path, target: Path) -> bool:
    """Alt dizin kuralı bu erişimde geçerli mi: `paths` yoksa her zaman, varsa o dizine göreli."""
    if not rule.is_scoped:
        return True
    base = rule.path.parent
    while base.name != "rules" and base != base.parent:
        base = base.parent
    owner = base.parent.parent  # <dizin>/.claude/rules → <dizin>
    try:
        rel = target.resolve().relative_to(owner.resolve()).as_posix()
    except (OSError, ValueError):
        return False
    del root
    return matches_paths(rule.paths, rel)
