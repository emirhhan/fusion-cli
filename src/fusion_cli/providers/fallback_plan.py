"""Gerçekten çalışabilecek yedek zinciri.

Yapılandırmadaki yedek, anahtarı olmayan bir sağlayıcıya (ör. NIM anahtarı yok)
işaret edebilir: birincil düşünce zincir ölü bir modele geçip aynı hatayı alıyordu.
Burada (1) anahtarı/oturumu olmayan yedekler ayıklanır, (2) girişi doğrulanmış ve
araç ölçümünü geçmiş web oturumları son çare olarak eklenir (`runtime.auto_web_fallback`).
"""

from __future__ import annotations

from dataclasses import replace

from ..config.keys import detect
from ..config.models import Config
from ..config.tool_policy import mutation_policy_for_model
from ..core.types import ModelSpec
from .registry import ProviderKind, provider_for_model


def _usable(config: Config, model: str) -> bool:
    """Bu model kimliği şu an bir cevap üretebilecek durumda mı?"""
    web = next((item for item in config.web_sessions if item.model == model), None)
    if web is not None:
        return web.enabled and web.login_verified
    definition = provider_for_model(model)
    if definition is None:
        return True
    if definition.kind is ProviderKind.LOCAL:
        return True
    if definition.kind is ProviderKind.BROWSER_BACKED:
        return False
    keys = detect()
    if definition.id == "nvidia_nim":
        return bool(keys.nim)
    if definition.id == "openrouter":
        return bool(keys.openrouter)
    return True


def _web_fallbacks(config: Config) -> tuple[str, ...]:
    return tuple(
        item.model
        for item in config.web_sessions
        if item.enabled and item.login_verified and mutation_policy_for_model(config, item.model).ok
    )


def live_fallbacks(spec: ModelSpec, config: Config) -> ModelSpec:
    """`spec`'in yedek zincirini çalışabilir olanlara indir, web yedeğini ekle."""
    chain = [model for model in spec.fallback if _usable(config, model)]
    if config.runtime.auto_web_fallback:
        chain.extend(model for model in _web_fallbacks(config) if model != spec.model)
    unique = tuple(dict.fromkeys(model for model in chain if model != spec.model))
    return spec if unique == spec.fallback else replace(spec, fallback=unique)
