"""Bağlantı kurulması ile kaynak güvenini birbirinden ayır."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import PurePath
from urllib.parse import urlsplit

from ..config.models import McpServerConfig, McpTransport, McpTrust
from ..core.redaction import contains_sensitive
from ..core.tools import ToolEffect

_PINNED_PACKAGE = re.compile(
    r"(?:@[a-z0-9._-]+/)?[a-z0-9._-]+@[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?", re.I
)
_INSTALL_FLAGS = frozenset({"-y", "--yes"})


def review_identity(config: McpServerConfig) -> str | None:
    """Yalnız sır içermeyen, sürümü incelenebilir kaynağın parmak izini üret."""
    source: tuple[object, ...]
    if contains_sensitive(config.client_id):
        return None
    if config.is_remote:
        try:
            url = urlsplit(config.url)
            if url.username or url.password or url.query or url.fragment or not url.hostname:
                return None
            if url.scheme != "https" and not (
                url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
            ):
                return None
            if contains_sensitive(url.path):
                return None
            source = (url.scheme.lower(), url.hostname.lower(), url.port, url.path.rstrip("/"))
        except ValueError:
            return None
    else:
        packages = tuple(argument for argument in config.args if argument not in _INSTALL_FLAGS)
        if PurePath(config.command).name != "npx" or len(packages) != 1:
            return None
        if not _PINNED_PACKAGE.fullmatch(packages[0]):
            return None
        source = (config.command, packages[0])
    identity = (
        source,
        config.client_id,
        config.token_env,
        sorted(config.env_names),
        sorted(config.scopes),
    )
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def _plain(value: object) -> object:
    """SDK nesnesini (pydantic) ya da sözlüğü sıralanabilir düz veriye çevir."""
    dump = getattr(value, "model_dump", None)
    return dump(exclude_none=True) if callable(dump) else value


def tools_digest(tools: Iterable[object]) -> str:
    """Araç tanımlarının (ad, açıklama, şema, ipuçları) sıradan bağımsız parmak izi.

    Ölçüldü (30 Ekim): güven yalnız kaynak adresine/paketine bağlıydı; incelemeden sonra
    sunucunun araç açıklaması, şeması ya da `readOnlyHint`i değişse bile güven sürüyordu.
    """
    rows = sorted(
        json.dumps(
            [
                getattr(tool, "name", ""),
                getattr(tool, "description", None) or "",
                _plain(getattr(tool, "inputSchema", None)) or {},
                _plain(getattr(tool, "annotations", None)) or {},
            ],
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        for tool in tools
    )
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def effective_trust(config: McpServerConfig, observed_tools: str | None = None) -> McpTrust:
    """Kaynak ya da (kayıtlıysa) araç tanımı değişimi eski güven kaydını sessizce geçersiz kılar.

    `observed_tools` sunucudan en son keşfedilen araç özetidir; henüz keşfedilmediyse `None`
    verilir ve yalnız kaynak denetlenir.
    """
    if config.trust is McpTrust.REVOKED:
        return McpTrust.REVOKED
    fingerprint = review_identity(config)
    if config.trust is McpTrust.TRUSTED and fingerprint and fingerprint == config.reviewed_source:
        if config.reviewed_tools and observed_tools and observed_tools != config.reviewed_tools:
            return McpTrust.UNREVIEWED
        return McpTrust.TRUSTED
    return McpTrust.UNREVIEWED


def trusted_effect(
    config: McpServerConfig, effect: ToolEffect | None, observed_tools: str | None = None
) -> ToolEffect | None:
    """İncelenmemiş sunucunun salt-okuma iddiası onayı atlayamaz."""
    trust = effective_trust(config, observed_tools)
    if effect is ToolEffect.REMOTE_READ and trust is not McpTrust.TRUSTED:
        return ToolEffect.REMOTE_WRITE
    return effect
