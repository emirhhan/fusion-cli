"""Beceri listesi: Claude Code'un beceri listeleme kuralları birebir (#164, #181).

Claude Code her istekte modele beceri listesini verir (progressive disclosure: gövde yalnız
kullanımda yüklenir):

- Listede HER beceri adı her zaman bulunur.
- Bütçe model penceresinin %1'idir (`skillListingBudgetFraction`, settings.json); aşılınca
  açıklamalar düşer. Ortam değişkeni `SLASH_COMMAND_TOOL_CHAR_BUDGET` bütçeyi karakter olarak
  sabitler.
- Giriş başına açıklama (`description` + `when_to_use`) 1.536 karakterde kesilir
  (`skillListingMaxDescChars`).
- Tek düz listedir; proje becerileri ayrı etiketle ya da güvenilmezlik notuyla işaretlenmez.

Fusion farkı: Claude az çağrılan becerinin açıklamasını önce düşürür; Fusion'da çağrı sayısı
tutulmadığından açıklama keşif önceliğinin sonundan (en düşük öncelikli kaynak) başlayarak
düşer. `disable-model-invocation` olan beceriler listeye girmez. `runtime.skill_index_chars: 0`
listeyi kapatır (eski Fusion ayarı).
"""

from __future__ import annotations

import os
from pathlib import Path

from ...config import claude_settings
from ...config.models import Config
from ...tools.capabilities import Capability, CapabilityRegistry
from .context_budget import CHARS_PER_TOKEN_ESTIMATE, context_budget

#: Pencere bilinmediğinde kullanılan bütçe (karakter); `runtime.skill_index_chars`.
SKILL_INDEX_CHARS = 4_000

#: Claude Code varsayılanı: pencerenin %1'i.
DEFAULT_BUDGET_FRACTION = 0.01

#: Giriş başına açıklama sınırı (Claude Code: 1.536 karakter).
DESCRIPTION_CHARS = 1_536

BUDGET_ENV = "SLASH_COMMAND_TOOL_CHAR_BUDGET"

#: Geri uyum: eski adlar (ayrı depo bloğu kaldırıldı, #181).
INDEX_WINDOW_SHARE = DEFAULT_BUDGET_FRACTION
INDEX_MIN_CHARS = 0
REPO_SOURCES = frozenset({"proje", "ek-kok", "kurulu", "claude-plugin", "eklenti"})

HEADER = (
    "BECERİ DİZİNİ (ad — ne işe yarar). Görev bunlardan birine uyuyorsa ÖNCE "
    "Skill(skill='<ad>', args='…') ile çağır, dönen yönergeleri uygula; listede yoksa "
    "find_skill ile ara."
)


def index_budget_for(config: Config, *, root: Path | None = None, home: Path | None = None) -> int:
    """Turun dizin bütçesi (karakter): ortam değişkeni > pencere × oran > yapılandırma."""
    runtime = getattr(config, "runtime", None)
    configured = int(getattr(runtime, "skill_index_chars", SKILL_INDEX_CHARS))
    if configured <= 0:
        return 0
    fixed = os.environ.get(BUDGET_ENV, "").strip()
    if fixed.isdigit():
        return int(fixed)
    fraction = DEFAULT_BUDGET_FRACTION
    if root is not None:
        fraction = claude_settings.effective_float(
            root, home, "skillListingBudgetFraction", DEFAULT_BUDGET_FRACTION
        )
    try:
        window = context_budget(config, config.agent).window_tokens
    except (AttributeError, TypeError, ValueError):
        return configured
    if not window:
        return configured
    return max(0, int(window * CHARS_PER_TOKEN_ESTIMATE * fraction))


def description_limit(root: Path | None, home: Path | None) -> int:
    if root is None:
        return DESCRIPTION_CHARS
    value = claude_settings.effective_int(root, home, "skillListingMaxDescChars", DESCRIPTION_CHARS)
    return value if value > 0 else DESCRIPTION_CHARS


def _summary(description: str, limit: int) -> str:
    summary = " ".join(description.split())
    if len(summary) > limit:
        summary = summary[: limit - 1].rstrip() + "…"
    return summary


def _line(name: str, summary: str) -> str:
    return f"- {name} — {summary}" if summary else f"- {name}"


def is_repo_sourced(skill: Capability) -> bool:
    """Beceri yalnız depo kaynaklarından mı geliyor (geri uyum yardımcısı)?"""
    return set(skill.source.split("+")) <= REPO_SOURCES


def skill_index_block(
    registry: CapabilityRegistry | None,
    budget: int = SKILL_INDEX_CHARS,
    *,
    max_description: int = DESCRIPTION_CHARS,
) -> str:
    """Tek düz liste: her ad her zaman; bütçe aşılırsa sondan başlayarak açıklama düşer."""
    if registry is None or budget <= 0:
        return ""
    skills = [item for item in registry.skills() if item.model_invocable]
    if not skills:
        return ""
    summaries = [
        _summary(item.description, max_description) if item.describe_in_index else ""
        for item in skills
    ]
    lines = [_line(item.name, text) for item, text in zip(skills, summaries, strict=True)]
    total = len(HEADER) + sum(len(line) + 1 for line in lines)
    for index in range(len(skills) - 1, -1, -1):
        if total <= budget:
            break
        if summaries[index]:
            short = _line(skills[index].name, "")
            total -= len(lines[index]) - len(short)
            lines[index] = short
    return "\n".join([HEADER, *lines])
