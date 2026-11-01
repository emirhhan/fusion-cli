"""Becerinin `allowed-tools` / `disallowed-tools` alanları: tur boyunca izin kuralı (#142, #180).

Claude Code (code.claude.com/docs/en/skills, Frontmatter reference): `allowed-tools`
"Tools Claude can use without asking permission when this skill is active" — listedeki araç
ya da `Bash(git *)` deseni beceri etkinken onaysız kullanılır, diğer araçlar KALDIRILMAZ ve
izin kurallarına göre davranır. Kullanıcının sonraki mesajında kalkar. `disallowed-tools`
ise yasaktır: belge yalnız "Tools removed from Claude's available pool" diyor; desenli girdi
(`Bash(rm *)`) aracın TAMAMINI yasaklar. Belge (sub-agents, `disallowedTools`) aynı alanın alt
ajan karşılığı için bunu açıkça söyler: "A disallowedTools entry with a specifier, such as
Bash(git push *), still removes the whole tool"; yalnız eşleşen komutu engellemek için
`permissions.deny` kuralı önerilir (#180).

Fusion'da tur sahibi turun başında `begin_turn` ile kullanıcının `/beceri` çağrısının
kurallarını `ToolContext.skill_grants`'a yazar; modelin `Skill` aracı aynı listeye ekler.
Araç kapısı (`loop._execute_call`) `with_grants` ile bunları izin kurallarına katar:
DENY > ASK > ALLOW sırası korunur (kullanıcının `deny` kuralı becerinin ön onayını yener).
"""

from __future__ import annotations

from collections.abc import Iterable

from ...config.permission_rules import (
    PermissionDecision,
    PermissionRule,
    PermissionRuleSet,
    parse_rule,
)
from ...core.tools import ToolContext

#: Becerinin izin kurallarının kaynak adı (kural açıklamalarında görünür).
SKILL_RULE_SOURCE = "beceri"

ALLOW = PermissionDecision.ALLOW.value
DENY = PermissionDecision.DENY.value


def entries(allowed: Iterable[str] = (), denied: Iterable[str] = ()) -> tuple[tuple[str, str], ...]:
    """Frontmatter listelerini `(karar, desen)` çiftlerine çevir; boşlar atılır."""
    pairs = [(ALLOW, item.strip()) for item in allowed if item.strip()]
    pairs += [(DENY, item.strip()) for item in denied if item.strip()]
    return tuple(pairs)


def begin_turn(context: ToolContext | None, grants: Iterable[tuple[str, str]] = ()) -> None:
    """Yeni kullanıcı mesajı: önceki becerinin kuralları kalkar, bu çağrınınkiler girer."""
    if context is None:
        return
    holder = getattr(context, "skill_grants", None)
    if holder is None:
        return
    holder.clear()
    holder.extend(grants)


def grant(context: ToolContext | None, grants: Iterable[tuple[str, str]]) -> None:
    """Tur içinde çağrılan becerinin kurallarını ekle (modelin `Skill` aracı)."""
    holder = getattr(context, "skill_grants", None) if context is not None else None
    if holder is None:
        return
    for pair in grants:
        if pair not in holder:
            holder.append(pair)


def rules_of(grants: Iterable[tuple[str, str]]) -> tuple[PermissionRule, ...]:
    """`(karar, desen)` çiftlerinden geçerli izin kuralları; bozuk desen atılır."""
    parsed: list[PermissionRule] = []
    for decision, pattern in grants:
        rule = parse_rule(pattern, PermissionDecision(decision), source=SKILL_RULE_SOURCE)
        if rule is not None:
            parsed.append(rule)
    return tuple(parsed)


def with_grants(
    rules: PermissionRuleSet | None, context: ToolContext | None
) -> PermissionRuleSet | None:
    """İzin kurallarına bu turun beceri kurallarını kat; beceri yoksa aynı nesne."""
    holder = getattr(context, "skill_grants", None) if context is not None else None
    if not holder:
        return rules
    extra = rules_of(tuple(holder))
    if not extra:
        return rules
    base = rules or PermissionRuleSet()
    return base.with_rules((*base.rules, *extra))
