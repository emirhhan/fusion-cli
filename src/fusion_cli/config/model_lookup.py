"""Etkin yapılandırmadaki model kimliğine ait doğrulanmış kaydı bulma."""

from __future__ import annotations

from collections.abc import Sequence

from ..core.types import ModelSpec
from .models import Config


def configured_model_specs(config: Config) -> tuple[ModelSpec, ...]:
    """Rol ve kademe kayıtlarını öncelik sırasıyla taşı; ağ/katalog erişimi yapma."""
    specs = [config.agent, config.judge, *config.candidates]
    specs.extend(spec for spec in (config.vision, config.teacher) if spec is not None)
    for tier in config.tiers:
        specs.extend((tier.agent, tier.judge, *tier.candidates))
    return tuple(specs)


def model_spec_for(model: str, specs: Sequence[ModelSpec]) -> ModelSpec | None:
    """Yalnız tam kimlik eşleşmesini kabul et; başka modelden kanıt aktarma."""
    return next((spec for spec in specs if spec.model == model), None)
