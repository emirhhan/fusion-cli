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
    """Becerinin etkin görünürlüğü; listede yoksa `on`. `skillOverrides` eklentiye uymaz."""
    if not set(item.source.split("+")) & _PLUGIN_SOURCES:
        from_settings = overrides.get(SETTINGS_PREFIX + item.name)
        if from_settings is not None:
            return from_settings
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


#: Claude Code: "Plugin skills are not affected by `skillOverrides`."
_PLUGIN_SOURCES = frozenset({"claude-plugin", "eklenti"})


def settings_overrides(root: Path, home: Path | None) -> dict[str, SkillVisibility]:
    """`settings.json` `skillOverrides` (#176): katmanlar birleşir, özel olan kazanır.

    Geçersiz değer yok sayılır. Anahtar beceri adıdır; eklenti becerileri etkilenmez
    (`apply_overrides` kaynağa bakar).
    """
    from ..config import claude_settings

    result: dict[str, SkillVisibility] = {}
    for name, value in claude_settings.merged_mapping(root, home, "skillOverrides").items():
        try:
            result[name] = SkillVisibility(str(value).strip().lower())
        except ValueError:
            continue
    return result


def effective_overrides(
    config: Config, root: Path, home: Path | None
) -> dict[str, SkillVisibility]:
    """`config.yaml` `capabilities.overrides` + `settings.json` `skillOverrides` (ayar kazanır)."""
    return {
        **overrides_from(config),
        **{f"{SETTINGS_PREFIX}{k}": v for k, v in settings_overrides(root, home).items()},
    }


#: `skillOverrides` kaynaklı anahtarların işareti: eklenti becerisine uygulanmaz.
SETTINGS_PREFIX = "\x00settings:"


#: `disabled_builtin_agents` içinde bütün yerleşik (`fusion`) ajanları kaldıran işaret.
ALL_BUILTIN_AGENTS = frozenset({"*"})


def registry_from_config(
    config: Config,
    home: Path,
    root: Path,
    *,
    extra_roots: tuple[Path, ...] = (),
    session_disabled_skills: frozenset[str] = frozenset(),
    session_disabled_agents: frozenset[str] = frozenset(),
    session_agents: tuple[Capability, ...] = (),
    working_directory: Path | None = None,
    headless: bool = False,
) -> CapabilityRegistry:
    """Kalıcı `capabilities.disabled` + `overrides` uygulanmış katalog (tüm yüzeyler aynı)."""
    from ..core.proposal_invocation import (
        ProposalPolicy,  # döngüsel: `capabilities` bu modülü kullanır
    )
    from .capabilities import CapabilityRegistry

    disabled = frozenset(getattr(getattr(config, "capabilities", None), "disabled", ()) or ())
    launch = getattr(config, "agent_launch", None)
    builtin_off = (
        frozenset({"explore", "plan"})
        if getattr(launch, "disable_explore_plan_agents", False)
        else frozenset()
    )
    # Claude Code: SDK değişkeni yalnız etkileşimsiz kipte ve SDK'da okunur; hepsi kalkar.
    if headless and getattr(launch, "disable_builtin_agents", False):
        builtin_off = ALL_BUILTIN_AGENTS
    return CapabilityRegistry(
        home,
        root,
        disabled_skills=disabled | session_disabled_skills,
        disabled_agents=disabled | session_disabled_agents,
        extra_roots=extra_roots,
        proposal_policy=ProposalPolicy(enabled=config.runtime.verified_skill_proposals),
        overrides=effective_overrides(config, root, home),
        managed_roots=tuple(Path(path) for path in config.agent_launch.managed_agent_roots),
        session_agents=session_agents,
        working_directory=working_directory if working_directory is not None else root,
        disabled_builtin_agents=builtin_off,
        extra_agent_sources=getattr(launch, "extra_agent_sources", True),
    )
