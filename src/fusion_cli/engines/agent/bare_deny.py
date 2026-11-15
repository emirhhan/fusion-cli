"""Yalın deny kuralı aracı modelin bağlamından çıkarır — Claude Code ile birebir (#63).

Kaynak: code.claude.com/docs/en/permissions#manage-permissions: `Bash` gibi yalın ad (ya da
`Bash(*)`) deny listesindeyse araç modelin bağlamından tamamen çıkar; model onu hiç görmez.
Belirteçli kural (`Bash(rm *)`) aracı bırakır, eşleşen çağrıyı engeller.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...config.permission_rules import PermissionDecision, PermissionRule, PermissionRuleSet
from ...tools.permission_match import matches


def is_bare_deny(rule: PermissionRule) -> bool:
    """Aracın tamamını yasaklayan deny kuralı mı (`Bash`, `Bash(*)`, `mcp__s`)?"""
    return rule.decision is PermissionDecision.DENY and rule.specifier in {None, "*"}


def bare_denied_tools(rules: PermissionRuleSet | None, names: Iterable[str]) -> frozenset[str]:
    """Yalın deny kuralının kapsadığı araç adları."""
    if rules is None or not rules.rules:
        return frozenset()
    bare = [
        PermissionRule(rule.tool, None, rule.decision, rule.source)
        for rule in rules.rules
        if is_bare_deny(rule)
    ]
    if not bare:
        return frozenset()
    return frozenset(name for name in names if any(matches(r, name, {}, None) for r in bare))


def surface_denied(deps: object, names: Iterable[str]) -> frozenset[str]:
    """Şema yüzeyinden düşecek adlar: `--disallowed-tools` + yalın deny kuralları."""
    denied = frozenset(getattr(deps, "denied_tools", ()) or ())
    return denied | bare_denied_tools(getattr(deps, "permission_rules", None), names)
