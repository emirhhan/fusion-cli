"""Execution profile ↔ kademe çözümlemesi.

Kullanıcıya görünen profil adları (`low`, `medium`, `high`, `max`) ile içerdeki
kademe adları (`config.tiers`) aynıdır — TEK istisna `max`'tir: master prompt
`max` ister ama mevcut en üst kademenin adı `premium`'dur. İkinci bir kademe
sistemi kurmak yerine (RULES.md "aynı işi yapan ikinci yol açılmaz") `max` yalnızca
kabul edilen bir ALIAS'tır: `premium` kademesine çözülür. Görünen adlar
değiştirilmez, böylece `premium`'u bilen kullanıcı şaşırmaz.
"""

from __future__ import annotations

from .models import Config

#: Kabul edilen profil adları → kademe adı. Kademe adı zaten geçerli bir profildir;
#: burada yalnızca kademe adı OLMAYAN eş anlamlılar tutulur. Tek doğruluk kaynağı.
PROFILE_ALIASES: dict[str, str] = {"max": "premium"}


def resolve_tier_name(config: Config, name: str) -> str | None:
    """Bir profil/kademe adını yapılandırmadaki gerçek kademe adına çevir.

    Büyük/küçük harf duyarsızdır ve alias uygular. Karşılığı yoksa `None` döner:
    çağıran taraf anlaşılır bir hata gösterebilsin, sessizce yanlış kademe seçilmesin.
    """
    wanted = name.strip().casefold()
    if not wanted:
        return None
    resolved = PROFILE_ALIASES.get(wanted, wanted)
    for tier in config.tiers:
        if tier.name.casefold() == resolved:
            return tier.name
    return None


def auto_turn_config(config: Config, task: str) -> tuple[Config, str | None]:
    """Choose the shared auto profile without changing session state or preferences.

    Missing tiers preserve the current model, as in the CLI. The returned reason
    belongs to this turn; callers decide how to display it on their surface.
    """
    from ..engines.agent.auto_profile import auto_profile
    from ..ui import messages
    from .model_select import apply_tier

    choice = auto_profile(task)
    tier_name = resolve_tier_name(config, choice.profile)
    if tier_name is None:
        return config, None
    return apply_tier(config, tier_name), messages.MODE_AUTO_SELECTED.format(
        profile=tier_name, reason=choice.reason
    )
