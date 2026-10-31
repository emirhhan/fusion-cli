"""Beceri görünürlük geçersiz kılmaları: `capabilities.overrides` (P-051).

Claude Code `skillOverrides` ayarının karşılığı. Beceri adı (ya da nitelikli kimlik
`ad@kaynak:kimlik`) bir görünürlüğe eşlenir:

- `on`: olağan davranış.
- `name-only`: beceri dizinine yalnız adı girer; açıklama bağlam harcamaz.
- `user-invocable-only`: model dizinde görmez, kendiliğinden yüklemez; kullanıcı `/ad` ile çağırır.
- `off`: hiç sunulmaz (`capabilities.disabled` ile aynı).

Nitelikli kimlik düz addan önce gelir: aynı adlı iki beceriden yalnız birini kapatmak mümkün.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.models import Config, SkillVisibility

if TYPE_CHECKING:
    from .capabilities import Capability, CapabilityRegistry


def visibility_of(item: Capability, overrides: Mapping[str, SkillVisibility]) -> SkillVisibility:
    """Becerinin etkin görünürlüğü; listede yoksa `on`."""
    return overrides.get(item.qualified_name) or overrides.get(item.name) or SkillVisibility.ON


def apply_overrides(
    items: tuple[Capability, ...], overrides: Mapping[str, SkillVisibility]
) -> tuple[Capability, ...]:
    """Görünürlüğü uygulanmış beceriler: `off` düşer, diğerleri bayrakla işaretlenir."""
    if not overrides:
        return items
    result: list[Capability] = []
    for item in items:
        visibility = visibility_of(item, overrides)
        if visibility is SkillVisibility.OFF:
            continue
        if visibility is SkillVisibility.NAME_ONLY:
            item = dataclasses.replace(item, describe_in_index=False)
        elif visibility is SkillVisibility.USER_INVOCABLE_ONLY:
            item = dataclasses.replace(item, model_invocable=False, user_invocable=True)
        result.append(item)
    return tuple(result)


def overrides_from(config: Config) -> dict[str, SkillVisibility]:
    """Yapılandırmadaki geçersiz kılmalar; eski (alanı olmayan) yapılandırmada boş."""
    capabilities = getattr(config, "capabilities", None)
    return dict(getattr(capabilities, "overrides", None) or {})


def registry_from_config(
    config: Config,
    home: Path,
    root: Path,
    *,
    extra_roots: tuple[Path, ...] = (),
    session_disabled_skills: frozenset[str] = frozenset(),
    session_disabled_agents: frozenset[str] = frozenset(),
) -> CapabilityRegistry:
    """Kalıcı `capabilities.disabled` + `overrides` uygulanmış katalog (tüm yüzeyler aynı)."""
    from .capabilities import CapabilityRegistry  # döngüsel: `capabilities` bu modülü kullanır

    disabled = frozenset(getattr(getattr(config, "capabilities", None), "disabled", ()) or ())
    return CapabilityRegistry(
        home,
        root,
        disabled_skills=disabled | session_disabled_skills,
        disabled_agents=disabled | session_disabled_agents,
        extra_roots=extra_roots,
        overrides=overrides_from(config),
    )
