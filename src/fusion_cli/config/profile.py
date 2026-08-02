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
