"""`/profiles` — çalışma profillerini (kademeleri) görüntüle ve düzenle.

Master prompt §9.4: kullanıcı bir profilin BAŞ modelini değiştirebilmeli ve seçim
ekranı yalnızca o profile UYGUN modelleri göstermeli (uyumsuzlar istenirse gerekçesiyle).
Bu, Faz 2b'de ertelenen "hedef-profile göre hard filtre + uyumsuzları göster" işini
tamamlar: artık filtrenin bir yüzeyi (profil editörü) var.

Düzenleme, kademenin baş (agent) modelini kendi aday havuzundan seçer, sonra kademeyi
uygular (anında etkili) ve kalıcılaştırır — mevcut `apply_tier`/`applied_result`
çekirdeğini kullanır (ikinci yol değildir).
"""

from __future__ import annotations

from dataclasses import replace

from ...config import model_select
from ...config.eligibility import capability_from_spec, eligible_profiles, is_eligible
from ...config.models import Config, ProfileEligibility, TierSpec
from ...core.types import ModelSpec
from ...ui import messages
from ...ui.picker import Choice, pick
from .model_flows import FlowResult, Picker


def list_profiles(config: Config) -> str:
    """Tüm profilleri (kademeleri) baş modeli ve uygunluk özetiyle listele."""
    if not config.tiers:
        return messages.PROFILES_EMPTY
    rows = [messages.PROFILES_HEADER]
    for tier in config.tiers:
        rows.append(messages.PROFILES_ROW.format(name=tier.name, model=tier.agent.model))
    return "\n".join(rows)


def _requirement(config: Config, tier_name: str) -> ProfileEligibility | None:
    """Kademenin uygunluk eşiği; kanonik profil değilse (ör. ultra) eşik yoktur."""
    return config.profile_eligibility.get(tier_name)


def _candidate_choice(
    spec: ModelSpec,
    requirement: ProfileEligibility | None,
    config: Config,
) -> tuple[Choice | None, Choice | None]:
    """Bir adayı uygun/uygunsuz seçeneğe çevir.

    Dönüş: (uygun_choice, uyumsuz_choice) — biri None. Uygunsuz seçenekte red
    gerekçesi açıklamada yazar.
    """
    capability = capability_from_spec(spec)
    badge = "·".join(eligible_profiles(capability, config.profile_eligibility)) or "—"
    if requirement is None:
        return Choice(spec.name, spec.name, f"{spec.model}  ·  profiller: {badge}"), None
    verdict = is_eligible(capability, requirement)
    if verdict.ok:
        return Choice(spec.name, spec.name, f"{spec.model}  ·  profiller: {badge}"), None
    return None, Choice(
        spec.name, spec.name, messages.PROFILES_INCOMPATIBLE.format(reason=verdict.reason)
    )


def edit_profile_primary(
    config: Config,
    tier_name: str,
    *,
    picker: Picker = pick,
    show_incompatible: bool = False,
) -> FlowResult:
    """Bir profilin baş (agent) modelini, uygunluk-filtreli seçim ekranından değiştir."""
    wanted = tier_name.strip().lower()
    tier = config.tier_by_name(wanted)
    if tier is None:
        known = ", ".join(item.name for item in config.tiers)
        return FlowResult(config, messages.PROFILES_UNKNOWN.format(name=tier_name, known=known))

    requirement = _requirement(config, tier.name)
    uygun: list[Choice] = []
    uyumsuz: list[Choice] = []
    for spec in tier.candidates:
        ok_choice, bad_choice = _candidate_choice(spec, requirement, config)
        if ok_choice is not None:
            uygun.append(ok_choice)
        elif bad_choice is not None:
            uyumsuz.append(bad_choice)

    secenekler = tuple(uygun) + (tuple(uyumsuz) if show_incompatible else ())
    if not secenekler:
        return FlowResult(config, messages.PROFILES_NO_ELIGIBLE.format(name=tier.name))

    picked = picker(
        secenekler,
        title=messages.PROFILES_EDIT_TITLE.format(name=tier.name),
    )
    if picked is None:
        return FlowResult(config, messages.PICKER_CANCELLED)

    chosen = next((spec for spec in tier.candidates if spec.name == picked), None)
    if chosen is None:
        return FlowResult(config, messages.PICKER_CANCELLED)

    updated = _with_primary(config, tier, chosen)
    applied = model_select.apply_tier(updated, tier.name)
    return FlowResult(applied, _saved_message(applied, tier.name, chosen))


def _with_primary(config: Config, tier: TierSpec, chosen: ModelSpec) -> Config:
    """Kademenin agent (baş) modelini `chosen` yap; diğer kademeler değişmez."""
    new_tier = replace(tier, agent=chosen)
    new_tiers = tuple(new_tier if item.name == tier.name else item for item in config.tiers)
    return replace(config, tiers=new_tiers)


def _saved_message(config: Config, tier_name: str, chosen: ModelSpec) -> str:
    from ...config import writer
    from ...core.errors import ConfigError

    try:
        path = writer.write_model_section(config)
        saved = messages.LEVEL_SAVED.format(path=path)
    except ConfigError as error:
        saved = messages.LEVEL_SAVE_FAILED.format(error=error)
    applied = messages.PROFILES_APPLIED.format(name=tier_name, model=chosen.model)
    return f"{applied}\n{saved}"
