"""Proje kapsamlı eklentinin MCP sunucularına proje onayı (#419).

Claude Code (https://code.claude.com/docs/en/plugins/loading.md "Trust check and component
limits for repository plugins"): depodan (`.claude/settings.json` `enabledPlugins`) açılan
eklentinin MCP sunucuları projenin `.mcp.json`'ıyla aynı sunucu başına onaydan geçer; kullanıcı
kapsamında kurulan eklentininkiler ek onaysız yüklenir.

Fusion'da projenin `.mcp.json` onayı `fusion trust`'tır ve içeriğe bağlıdır. Burada da öyle:
`fusion trust` o anda açık proje eklentilerinin sunucu tanımlarını (sunucu başına SHA-256)
kaydeder; tanım sonradan değişirse (depo eklenti dosyasını güncellerse) sunucu yeniden
onaylanana dek başlatılmaz ve günlüğe yazılır. Kayıt eklenti deposunda, proje köküne göre tutulur.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.atomic_file import atomic_replace_text
from .models import McpServerConfig
from .plugin_scopes import SCOPE_PROJECT, resolve_enabled

if TYPE_CHECKING:
    from .plugin_store import InstalledPlugin, PluginState

_LOG = logging.getLogger(__name__)

APPROVALS_NAME = "proje-mcp-onaylari.json"
WARN_UNAPPROVED = (
    "proje eklentisi '{plugin}' MCP sunucusu '{server}' onaylanmadı ya da tanımı değişti; "
    "yüklenmedi. İnceleyip güveniyorsan: fusion trust"
)


def _file(base: Path | None) -> Path:
    from .plugin_store import plugins_dir

    return (base or plugins_dir()) / APPROVALS_NAME


def _load(base: Path | None) -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(_file(base).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(k): {str(a): str(b) for a, b in v.items()}
        for k, v in raw.items()
        if isinstance(v, dict)
    }


def server_digest(server: McpServerConfig) -> str:
    payload = json.dumps(dataclasses.asdict(server), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_project_scope(item: InstalledPlugin, state: PluginState, project: Path) -> bool:
    """Eklentiyi yalnız proje (`.claude/settings.json`) mi açıyor? Kullanıcı açtıysa değil."""
    from .plugin_store import plugin_id

    record = item.record
    if record.kind == "inline":
        return False
    raw = state.plugin(record.store_key)
    if raw is not None and raw.enabled:
        return False
    decision = resolve_enabled(plugin_id(record), record.name, False, project)
    return decision.enabled and decision.scope == SCOPE_PROJECT


def _key(item: InstalledPlugin, server: McpServerConfig) -> str:
    return f"{item.record.name}/{server.name}"


def approved_servers(
    item: InstalledPlugin,
    servers: tuple[McpServerConfig, ...],
    state: PluginState,
    project: Path,
    base: Path | None = None,
) -> tuple[McpServerConfig, ...]:
    """Proje kapsamlı eklentide yalnız onaylı tanımlar; ötekilerde hepsi."""
    if not servers or not is_project_scope(item, state, project):
        return servers
    approvals = _load(base).get(str(project.resolve()), {})
    kept: list[McpServerConfig] = []
    for server in servers:
        if approvals.get(_key(item, server)) == server_digest(server):
            kept.append(server)
        else:
            _LOG.warning(WARN_UNAPPROVED.format(plugin=item.record.name, server=server.name))
    return tuple(kept)


def approve_project(project: Path, base: Path | None = None) -> None:
    """`fusion trust`: projede şu an açık proje eklentilerinin sunucu tanımlarını onayla."""
    from ..core.plugins import PluginError
    from .plugin_layout import mcp_servers
    from .plugin_store import active_plugins, load_state

    state = load_state(base)
    record: dict[str, str] = {}
    for item in active_plugins(base, project):
        if item.layout is None or not is_project_scope(item, state, project):
            continue
        try:
            found = mcp_servers(item.layout)
        except PluginError:
            continue
        record.update({_key(item, server): server_digest(server) for server in found})
    _write(str(project.resolve()), record, base)


def forget_project(project: Path, base: Path | None = None) -> None:
    _write(str(project.resolve()), {}, base)


def _write(key: str, record: dict[str, str], base: Path | None) -> None:
    from .writer import config_lock

    path = _file(base)
    with config_lock(path):
        current = _load(base)
        if not record and key not in current:
            return
        updated = {k: v for k, v in current.items() if k != key}
        if record:
            updated[key] = record
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace_text(path, json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
