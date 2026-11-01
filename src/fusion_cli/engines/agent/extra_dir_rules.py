"""`--add-dir` dizininin `paths` alanlı kuralları dosya erişiminde etkinleşir (Claude Code #170).

Claude Code (code.claude.com/docs/en/memory, "Load from additional directories"):
`CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` iken ek dizinin CLAUDE.md, `.claude/CLAUDE.md`,
`.claude/rules/*.md` ve CLAUDE.local.md dosyaları yüklenir. `paths:` alanlı kural, kök
projedeki gibi, eşleşen bir dosyaya erişilince bağlama girer; desenler o ek dizine göredir.

`paths`'siz kurallar tur başında `instruction_layers` ile gelir; burası yalnız koşullu
kuralları ve onların `InstructionsLoaded(path_glob_match)` olayını üretir.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from ...core.types import Message
from .instruction_layers import ADDITIONAL_DIRS_ENV
from .instruction_rules import RuleFile, _scan, rule_block, scoped_rules_for
from .instructions_hook import payload
from .project_instructions import NESTED_NOTE_HEADER, nested_marker


@dataclass(frozen=True, slots=True)
class ExtraRuleHit:
    """Bağlama girecek tek koşullu kural."""

    label: str
    block: str
    event: dict[str, object]


def enabled() -> bool:
    return os.environ.get(ADDITIONAL_DIRS_ENV, "").strip() in ("1", "true")


def _scoped(extra: Path) -> tuple[RuleFile, ...]:
    rules = _scan(extra / ".claude" / "rules", base=extra, prefix="", trusted=False)
    return tuple(rule for rule in rules if rule.is_scoped)


def _relative(target: Path, extra: Path) -> str | None:
    try:
        return target.resolve().relative_to(extra.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def hits_for(
    extra_roots: Iterable[Path],
    target: Path,
    *,
    loaded: set[str],
    present: Callable[[str], bool],
) -> list[ExtraRuleHit]:
    """Erişilen dosyayı kapsayan ek dizinin eşleşen kuralları (bir kez; `loaded` güncellenir)."""
    if not enabled():
        return []
    hits: list[ExtraRuleHit] = []
    for extra in extra_roots:
        rel = _relative(target, Path(extra))
        if rel is None:
            continue
        for rule in scoped_rules_for(_scoped(Path(extra)), rel):
            label = str(rule.path)
            if label in loaded:
                continue
            loaded.add(label)
            if present(label):
                continue
            block, _ = rule_block(rule)
            if not block:
                continue
            event = {
                **payload(
                    str(rule.path), "ek-dizin", "path_glob_match", trigger_file_path=str(target)
                ),
                "globs": list(rule.paths),
            }
            hits.append(
                ExtraRuleHit(label, f"{nested_marker(label)}\n{block}\n</alt_talimat>", event)
            )
    return hits


def note_for(hits: list[ExtraRuleHit]) -> Message | None:
    """Eşleşen kuralların tek bağlam notu (iç içe talimatlarla aynı biçim)."""
    if not hits:
        return None
    text = "\n".join([NESTED_NOTE_HEADER, *(hit.block for hit in hits)])
    return Message("user", text, harness_note=True)
