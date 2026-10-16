"""Bağlantı kurulması ile kaynak güvenini birbirinden ayır."""

from __future__ import annotations

import hashlib
import json
import re
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
    if config.transport is McpTransport.STREAMABLE_HTTP:
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


def effective_trust(config: McpServerConfig) -> McpTrust:
    """Kaynak değişimi eski güven kaydını sessizce geçersiz kılar."""
    if config.trust is McpTrust.REVOKED:
        return McpTrust.REVOKED
    fingerprint = review_identity(config)
    if config.trust is McpTrust.TRUSTED and fingerprint and fingerprint == config.reviewed_source:
        return McpTrust.TRUSTED
    return McpTrust.UNREVIEWED


def trusted_effect(config: McpServerConfig, effect: ToolEffect | None) -> ToolEffect | None:
    """İncelenmemiş sunucunun salt-okuma iddiası onayı atlayamaz."""
    if effect is ToolEffect.REMOTE_READ and effective_trust(config) is not McpTrust.TRUSTED:
        return ToolEffect.REMOTE_WRITE
    return effect
