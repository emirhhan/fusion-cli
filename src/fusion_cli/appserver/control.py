"""Native kontrol paneli için güvenli durum ve kimlik bilgisi işlemleri."""

from __future__ import annotations

import os
from typing import Any, Protocol

from ..config.keys import environ_snapshot
from ..config.models import Config
from ..providers.registry import BUILTIN_PROVIDERS, ProviderDefinition


class SecretStore(Protocol):
    @property
    def available(self) -> bool: ...

    def list_names(self) -> tuple[str, ...]: ...
    def set(self, env_name: str, value: str) -> None: ...
    def delete(self, env_name: str) -> bool: ...


def _provider(provider_id: str) -> ProviderDefinition | None:
    return next(
        (
            item
            for item in BUILTIN_PROVIDERS
            if item.id == provider_id and item.implemented and item.auth_env is not None
        ),
        None,
    )


def provider_rows(store: SecretStore) -> list[dict[str, Any]]:
    """Yalnız metadata döndür; sır değeri hiçbir zaman bu sınıra geçmez."""
    try:
        stored = set(store.list_names()) if store.available else set()
    except Exception:
        stored = set()
    environment = environ_snapshot()
    return [
        {
            "id": provider.id,
            "ad": provider.name,
            "ortam": provider.auth_env,
            "kurulu": provider.auth_env in stored
            or bool(environment.get(provider.auth_env or "", "").strip()),
        }
        for provider in BUILTIN_PROVIDERS
        if provider.implemented and provider.auth_env is not None
    ]


def snapshot(
    config: Config,
    store: SecretStore,
    *,
    root: str,
    approval: str,
    engine: str,
    gateway: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ok": True,
        "kok": root,
        "model": {
            "agent": config.agent.model,
            "hakem": config.judge.model,
            "adaylar": [candidate.model for candidate in config.candidates],
            "saglayici": config.runtime.provider,
            "yogunluk": config.runtime.reasoning_effort.value,
        },
        "izin": {
            "mod": approval,
            "kokle_sinirli": config.runtime.restrict_to_root,
        },
        "mcp": [{"ad": server.name, "komut": server.command} for server in config.mcp_servers],
        "saglayicilar": provider_rows(store),
        "sir_deposu_hazir": store.available,
        "gateway": gateway,
    }


def save_secret(store: SecretStore, provider_id: str, value: object) -> dict[str, Any]:
    definition = _provider(provider_id)
    secret = value.strip() if isinstance(value, str) else ""
    if definition is None:
        return {"ok": False, "metin": "Sağlayıcı bulunamadı veya anahtar kabul etmiyor."}
    if not secret or len(secret) > 65_536:
        return {"ok": False, "metin": "Anahtar boş ya da izin verilen boyuttan büyük."}
    if not store.available:
        return {"ok": False, "metin": "Sistem anahtarlığı kullanılamıyor."}
    store.set(definition.auth_env or "", secret)
    # Çalışan oturum yeni anahtarı hemen kullanabilsin; değer yanıta/loga girmez.
    os.environ[definition.auth_env or ""] = secret
    return {"ok": True, "saglayici": definition.id, "kurulu": True}


def delete_secret(store: SecretStore, provider_id: str) -> dict[str, Any]:
    definition = _provider(provider_id)
    if definition is None:
        return {"ok": False, "metin": "Sağlayıcı bulunamadı veya anahtar kabul etmiyor."}
    if store.available:
        store.delete(definition.auth_env or "")
    os.environ.pop(definition.auth_env or "", None)
    return {"ok": True, "saglayici": definition.id, "kurulu": False}
