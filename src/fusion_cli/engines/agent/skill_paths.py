"""Becerinin `paths` alanı: yalnız eşleşen dosyalarla çalışırken etkinleşme (#161).

Belge (code.claude.com/docs/en/skills, Frontmatter reference): "When set, Claude loads the
skill automatically only when working with files matching the patterns. Patterns are relative
to Claude's current working directory, and files outside that directory don't match." Glob
biçimi yola özel kurallarla aynıdır (`instruction_rules.matches_paths`).

Fusion: `paths` alanı olan beceri, model eşleşen bir dosyaya erişene kadar beceri listesine
girmez; erişimde etkinleşir, listeye katılır ve o anda kısa bir duyuru eklenir. Etkinleşme
oturum (katalog nesnesi) boyunca kalır.
"""

from __future__ import annotations

import weakref
from pathlib import Path

from ...core.types import Message
from ...tools.capabilities import Capability, CapabilityRegistry
from .instruction_rules import matches_paths

NOTE_HEADER = "[Çalışılan dosyalarla ilgili beceriler etkinleşti; Skill aracıyla çağırabilirsin:]"

_ACTIVE: weakref.WeakKeyDictionary[CapabilityRegistry, frozenset[str]] = weakref.WeakKeyDictionary()


def is_conditional(skill: Capability) -> bool:
    """`paths` alanı olan beceri koşulludur."""
    return bool(skill.paths)


def activated(registry: CapabilityRegistry | None) -> frozenset[str]:
    """Bu katalogda etkinleşmiş koşullu becerilerin nitelikli adları."""
    if registry is None:
        return frozenset()
    return _ACTIVE.get(registry, frozenset())


def visible_in_listing(registry: CapabilityRegistry | None, skill: Capability) -> bool:
    """Beceri listesine girer mi: koşulsuz ya da etkinleşmiş."""
    return not is_conditional(skill) or skill.qualified_name in activated(registry)


def _relative(root: Path, target: Path) -> str | None:
    try:
        return target.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def activate_for(
    registry: CapabilityRegistry | None, root: Path, targets: tuple[Path, ...]
) -> Message | None:
    """Erişilen dosyalara uyan koşullu becerileri etkinleştir; yeni etkinleşen varsa duyuru."""
    if registry is None or not targets:
        return None
    relatives = [rel for rel in (_relative(root, item) for item in targets) if rel is not None]
    if not relatives:
        return None
    current = activated(registry)
    fresh = [
        skill
        for skill in registry.skills()
        if is_conditional(skill)
        and skill.model_invocable
        and skill.qualified_name not in current
        and any(matches_paths(skill.paths, rel) for rel in relatives)
    ]
    if not fresh:
        return None
    _ACTIVE[registry] = current | {skill.qualified_name for skill in fresh}
    lines = [NOTE_HEADER]
    for skill in fresh:
        summary = " ".join(skill.description.split())[:200]
        lines.append(f"- {skill.name}" + (f" — {summary}" if summary else ""))
    return Message("user", "\n".join(lines), harness_note=True)
