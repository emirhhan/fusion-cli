"""Yerel (`local`) kapsamlı MCP kayıtları — Claude Code'un varsayılan kapsamı (#236).

Claude Code yerel sunucuyu `~/.claude.json` içinde o projenin yolu altında tutar:
yalnız o projede yüklenir ve kimseyle paylaşılmaz. Fusion aynı biçimi kullanıcının
yapılandırma dizinindeki `mcp-local.json` dosyasında tutar:

    {"projects": {"/yol/proje": {"mcpServers": {"stripe": {"type": "http", "url": "…"}}}}}

Dosya kullanıcının kendi dizinindedir (proje dosyası değildir); bu yüzden güven onayı
istemez — `config.yaml`'daki kullanıcı kayıtlarıyla aynı konumdadır.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from ..core.errors import ConfigError
from .mcp_entry import to_entry
from .models import McpScope, McpServerConfig
from .paths import user_config_dir
from .writer import config_lock

_LOG = logging.getLogger(__name__)

LOCAL_MCP_FILE = "mcp-local.json"
_PROJECTS = "projects"
_ROOT_KEY = "mcpServers"


def local_mcp_path() -> Path:
    return user_config_dir() / LOCAL_MCP_FILE


def _project_key(root: Path) -> str:
    return str(root.resolve())


def read_local_mcp_servers(root: Path) -> tuple[McpServerConfig, ...]:
    """Bu projenin yerel kayıtları; dosya ya da proje yoksa boş. Hatalı girdi atlanır."""
    servers, problems = read_local_mcp_report(root)
    for problem in problems:
        _LOG.warning("%s", problem)
    return servers


def read_local_mcp_report(root: Path) -> tuple[tuple[McpServerConfig, ...], tuple[str, ...]]:
    from .mcp_json import parse_mcp_servers_report

    project = _read(local_mcp_path()).get(_PROJECTS, {})
    entry = project.get(_project_key(root)) if isinstance(project, dict) else None
    if not isinstance(entry, dict):
        return (), ()
    return parse_mcp_servers_report(entry, scope=McpScope.LOCAL, where=LOCAL_MCP_FILE)


def upsert_local_mcp_server(root: Path, server: McpServerConfig) -> Path:
    """Tek kaydı bu projenin yerel listesine ekle ya da aynı adlıyı değiştir."""
    return _update(root, lambda entries: {**entries, server.name: to_entry(server)})


def remove_local_mcp_server(root: Path, name: str) -> Path:
    """Tek kaydı bu projenin yerel listesinden sil; yoksa `ConfigError`."""

    def _drop(entries: dict[str, object]) -> dict[str, object]:
        if name not in entries:
            raise ConfigError(f"{LOCAL_MCP_FILE}: bu projede '{name}' adlı sunucu yok")
        return {key: value for key, value in entries.items() if key != name}

    return _update(root, _drop)


def _update(root: Path, change: Callable[[dict[str, object]], dict[str, object]]) -> Path:
    path = local_mcp_path()
    with config_lock(path):
        data = _read(path)
        projects = data.get(_PROJECTS)
        projects = dict(projects) if isinstance(projects, dict) else {}
        key = _project_key(root)
        project = projects.get(key)
        project = dict(project) if isinstance(project, dict) else {}
        servers = project.get(_ROOT_KEY)
        current: dict[str, object] = dict(servers) if isinstance(servers, dict) else {}
        project[_ROOT_KEY] = change(current)
        projects[key] = project
        _atomic_write(path, {**data, _PROJECTS: projects})
    return path


def _read(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"{LOCAL_MCP_FILE} okunamadı: {error}") from error
    if not isinstance(loaded, dict):
        raise ConfigError(f"{LOCAL_MCP_FILE}: kök bir nesne olmalı")
    return loaded


def _atomic_write(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temp_path.chmod(0o600)
        temp_path.replace(path)
    except OSError as error:
        temp_path.unlink(missing_ok=True)
        raise ConfigError(f"{LOCAL_MCP_FILE} yazılamadı: {error}") from error


_DISABLED = "disabledMcpServers"


def disabled_mcp_servers(root: Path) -> frozenset[str]:
    """`/mcp` aç/kapa ile bu projede kapatılan sunucu adları (Claude `disabledMcpServers`)."""
    try:
        projects = _read(local_mcp_path()).get(_PROJECTS, {})
    except ConfigError as error:
        _LOG.warning("%s", error)
        return frozenset()
    entry = projects.get(_project_key(root)) if isinstance(projects, dict) else None
    names = entry.get(_DISABLED) if isinstance(entry, dict) else None
    return frozenset(str(name) for name in names) if isinstance(names, list) else frozenset()


def set_mcp_server_enabled(root: Path, name: str, *, enabled: bool) -> Path:
    """Sunucuyu bu proje için aç ya da kapat; kayıt kapsamından silinmez."""
    path = local_mcp_path()
    with config_lock(path):
        data = _read(path)
        projects = data.get(_PROJECTS)
        projects = dict(projects) if isinstance(projects, dict) else {}
        project = projects.get(_project_key(root))
        project = dict(project) if isinstance(project, dict) else {}
        current = set(disabled_mcp_servers(root))
        current = current - {name} if enabled else current | {name}
        project[_DISABLED] = sorted(current)
        projects[_project_key(root)] = project
        _atomic_write(path, {**data, _PROJECTS: projects})
    return path
