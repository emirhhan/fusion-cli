"""`/skill-doctor`: her becerinin bağlam maliyeti ve kullanım sıklığı (Claude Code #177).

Belge (code.claude.com/docs/en/commands, `/skill-doctor`): komut her becerinin bağlama
kattığı maliyeti ve ne sıklıkla çağrıldığını gösterir; böylece az kullanılıp çok yer kaplayan
beceriler `skillOverrides` ile `name-only`/`off` yapılabilir. Fusion'da:

- liste maliyeti: beceri listesinde her tur giden satır (ad + açıklama; `name-only` yalnız
  ad, modelin çağıramadığı beceri hiç yer kaplamaz),
- gövde maliyeti: beceri çağrılınca bağlama giren SKILL.md içeriği,
- kullanım: `skill_usage` sayacı (kullanıcının `/ad`'ı ve modelin `Skill` aracı).

Belirteçler `CHARS_PER_TOKEN_ESTIMATE` karakter/belirteç tahminidir (ağ ya da sağlayıcı yok).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import skill_usage
from .context_budget import CHARS_PER_TOKEN_ESTIMATE
from .skill_index import DESCRIPTION_CHARS, _line, _summary

if TYPE_CHECKING:
    from ...tools.capabilities import Capability, CapabilityRegistry

#: Raporda tek tek gösterilen en çok satır (gerisi toplamda).
REPORT_ROWS = 40


@dataclass(frozen=True, slots=True)
class SkillCost:
    name: str
    source: str
    listing_tokens: int
    body_tokens: int
    uses: int


def _tokens(chars: int) -> int:
    return (chars + CHARS_PER_TOKEN_ESTIMATE - 1) // CHARS_PER_TOKEN_ESTIMATE if chars else 0


def _body_chars(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _listing_chars(item: Capability) -> int:
    if not item.model_invocable:
        return 0
    summary = _summary(item.description, DESCRIPTION_CHARS) if item.describe_in_index else ""
    return len(_line(item.name, summary)) + 1


def skill_costs(registry: CapabilityRegistry, memory_dir: Path | None) -> tuple[SkillCost, ...]:
    """Becerileri liste maliyetine göre (büyükten küçüğe) sırala."""
    counts = skill_usage.load_counts(memory_dir)
    costs = [
        SkillCost(
            item.name,
            item.source,
            _tokens(_listing_chars(item)),
            _tokens(_body_chars(item.path)),
            counts.get(item.name.lower(), 0),
        )
        for item in registry.skills()
    ]
    return tuple(sorted(costs, key=lambda c: (-c.listing_tokens, -c.body_tokens, c.name)))


def render_cost_report(costs: tuple[SkillCost, ...]) -> str:
    """Terminal/masaüstü metni: toplam, satırlar, hiç çağrılmayanlar için öneri."""
    if not costs:
        return "Beceri maliyeti: beceri yok."
    total = sum(c.listing_tokens for c in costs)
    lines = [
        f"Beceri maliyeti ve kullanımı ({len(costs)} beceri; liste her tur ~{total} belirteç, "
        f"tahmin ~{CHARS_PER_TOKEN_ESTIMATE} karakter/belirteç):"
    ]
    for cost in costs[:REPORT_ROWS]:
        liste = f"liste ~{cost.listing_tokens}" if cost.listing_tokens else "listede yok"
        lines.append(
            f"· {cost.name} [{cost.source}] — {liste}, gövde ~{cost.body_tokens} belirteç "
            f"(çağrılınca), {cost.uses} çağrı"
        )
    if len(costs) > REPORT_ROWS:
        lines.append(f"… {len(costs) - REPORT_ROWS} beceri daha")
    unused = [c.name for c in costs if c.uses == 0 and c.listing_tokens]
    if unused:
        lines.append(
            "Hiç çağrılmamış ama listede yer kaplayanlar: "
            + ", ".join(unused[:10])
            + (" …" if len(unused) > 10 else "")
            + " — settings.json skillOverrides ile name-only ya da off yapılabilir."
        )
    return "\n".join(lines)
