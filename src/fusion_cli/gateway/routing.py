"""Gateway'e gelen `model` alanını Fusion `ModelSpec`'ine çöz.

Kullanıcı `model` olarak üç şey yazabilir:
- Bir PROFİL adı (`auto`, `low`, `medium`, `high`, `max`) → o profilin baş modeli +
  yedek zinciri (yani tam router davranışı: fallback + health devrede).
- Ham bir MODEL kimliği (`openai/gpt-4o`, `openrouter/…:free`) → doğrudan o model.
- Tanınmayan bir şey → güvenli varsayılan (`agent` rolü).
"""

from __future__ import annotations

from ..config.models import Config
from ..config.profile import resolve_tier_name
from ..core.types import ModelSpec


def resolve_spec(config: Config, model: str) -> ModelSpec:
    """`model` alanını çalıştırılacak `ModelSpec`'e çevir."""
    wanted = model.strip().lower()
    if wanted in ("auto", ""):
        return config.agent
    tier_name = resolve_tier_name(config, wanted)
    if tier_name is not None:
        tier = config.tier_by_name(tier_name)
        if tier is not None:
            return tier.agent
    if "/" in model:
        # Ham LiteLLM model kimliği: doğrudan çalıştırılır (fallback yok, tek model).
        return ModelSpec(name=model, model=model)
    return config.agent


def available_models(config: Config) -> list[str]:
    """`/v1/models` için sunulacak kimlikler: profiller + tanımlı aday modelleri."""
    profiles = ["auto", *(tier.name for tier in config.tiers)]
    candidates = [spec.model for spec in config.candidates]
    # Sıra korunur, tekrar atılır.
    return list(dict.fromkeys([*profiles, *candidates]))
