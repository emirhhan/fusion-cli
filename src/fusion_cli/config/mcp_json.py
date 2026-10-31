"""Proje kapsamlı MCP kaydı: kök dizindeki `.mcp.json` (Claude Code ile ortak biçim; P-049).

    {"mcpServers": {"github": {"command": "npx", "args": ["-y", "server-github"],
                               "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}},
                    "linear": {"type": "http", "url": "https://mcp.linear.app/mcp"}}}

Bir depo Claude Code için yazdığı `.mcp.json` ile Fusion'da da aynı sunucuları alır.
Dosya proje dosyasıdır: indirilen bir depo bununla stdio süreci başlatabilirdi, bu yüzden
yalnız `fusion trust` ile güvenilen (ya da Fusion'ın bizzat yazıp onayladığı) dosya
yüklenir — `config.yaml` için geçerli kuralın aynısı (`config/trust.py`).

`${VAR}` başvuruları burada ÇÖZÜLMEZ; kayıt başvuruyu taşır, bağlantı anında
`mcp_bridge/transport.py` çözer. Böylece sır ne config nesnesine ne de yazılan dosyaya
girer.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from ..core.errors import ConfigError
from . import trust
from .models import McpScope, McpServerConfig, McpTransport

_LOG = logging.getLogger(__name__)

#: Proje kökündeki dosya adı (Claude Code ile aynı).
PROJECT_MCP_FILE = ".mcp.json"
_ROOT_KEY = "mcpServers"
#: Claude Code `type` değerleri → Fusion taşıması. `sse` eski taşımadır; desteklenmez.
_TRANSPORTS: Mapping[str, McpTransport] = {
    "stdio": McpTransport.STDIO,
    "http": McpTransport.STREAMABLE_HTTP,
    "streamable_http": McpTransport.STREAMABLE_HTTP,
    "streamable-http": McpTransport.STREAMABLE_HTTP,
}
_KNOWN_KEYS = frozenset({"type", "transport", "command", "args", "env", "url", "headers"})


def project_mcp_path(root: Path) -> Path:
    return root / PROJECT_MCP_FILE


def read_project_mcp_servers(root: Path) -> tuple[McpServerConfig, ...]:
    """Kökteki `.mcp.json`'ı oku; dosya yoksa boş. Bozuk dosya `ConfigError` (dosya adıyla)."""
    path = project_mcp_path(root)
    if not path.is_file():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"{PROJECT_MCP_FILE} okunamadı: {error}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"{PROJECT_MCP_FILE} geçerli JSON değil: {error}") from error
    return parse_project_mcp(raw)


def parse_project_mcp(raw: object) -> tuple[McpServerConfig, ...]:
    """Claude Code `.mcp.json` içeriğini sunucu kayıtlarına çevir."""
    if not isinstance(raw, dict):
        raise ConfigError(f"{PROJECT_MCP_FILE}: kök bir nesne olmalı")
    servers = raw.get(_ROOT_KEY, {})
    if not isinstance(servers, dict):
        raise ConfigError(f"{PROJECT_MCP_FILE}: '{_ROOT_KEY}' bir nesne olmalı")
    return tuple(_parse_server(str(name), entry) for name, entry in servers.items())


def _parse_server(name: str, entry: object) -> McpServerConfig:
    where = f"{PROJECT_MCP_FILE}: {_ROOT_KEY}.{name}"
    if not isinstance(entry, dict):
        raise ConfigError(f"{where}: nesne bekleniyordu")
    unknown = sorted(set(entry) - _KNOWN_KEYS)
    if unknown:
        raise ConfigError(f"{where}: bilinmeyen alan(lar): {', '.join(unknown)}")
    kind = str(entry.get("type") or entry.get("transport") or "").strip().lower()
    url = _text(entry.get("url"), f"{where}.url")
    command = _text(entry.get("command"), f"{where}.command")
    if not kind:
        kind = "http" if url and not command else "stdio"
    transport = _TRANSPORTS.get(kind)
    if transport is None:
        raise ConfigError(
            f"{where}.type: '{kind}' desteklenmiyor. Geçerli: stdio, http"
            + (" (sse eski taşımadır; sunucunun http adresini kullan)" if kind == "sse" else "")
        )
    if transport is McpTransport.STDIO and not command:
        raise ConfigError(f"{where}: stdio sunucusu için 'command' gerekli")
    if transport is McpTransport.STREAMABLE_HTTP and not url:
        raise ConfigError(f"{where}: http sunucusu için 'url' gerekli")
    if entry.get("headers"):
        # Fusion başlık sözlüğü tutmaz; bearer için `token_env` vardır. Sessizce düşürmek
        # kimliksiz istek üretirdi.
        raise ConfigError(
            f"{where}.headers: desteklenmiyor. Bearer token için Fusion'da "
            f"`fusion mcp add --token-env <DEĞİŞKEN>` kullan."
        )
    return McpServerConfig(
        name=name,
        command=command,
        args=_texts(entry.get("args"), f"{where}.args"),
        transport=transport,
        url=url,
        env_literals=_env_pairs(entry.get("env"), f"{where}.env"),
        scope=McpScope.PROJECT,
    )


def _text(value: object, where: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ConfigError(f"{where}: metin bekleniyordu")
    return value.strip()


def _texts(value: object, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where}: metin listesi bekleniyordu")
    return tuple(value)


def _env_pairs(value: object, where: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: nesne bekleniyordu")
    pairs: list[tuple[str, str]] = []
    for key, item in value.items():
        if not isinstance(item, str):
            raise ConfigError(f"{where}.{key}: metin bekleniyordu")
        pairs.append((str(key), item))
    return tuple(pairs)


def trusted_project_mcp_servers(root: Path) -> tuple[McpServerConfig, ...]:
    """Güvenilen projenin `.mcp.json` sunucuları; güven yoksa boş ve tek satır uyarı."""
    path = project_mcp_path(root)
    if not path.is_file():
        return ()
    # Güvenilmeyen dosya HİÇ ayrıştırılmaz: indirilen deponun bozuk `.mcp.json`'ı
    # Fusion'ın açılışını engellemesin.
    if not trust.is_file_trusted(root, path):
        _LOG.warning(
            "%s güvenilir değil; içindeki MCP sunucuları yüklenmedi. Güveniyorsan: fusion trust",
            path,
        )
        return ()
    return read_project_mcp_servers(root)


def merge_mcp_servers(
    user_servers: tuple[McpServerConfig, ...], project_servers: tuple[McpServerConfig, ...]
) -> tuple[McpServerConfig, ...]:
    """Kullanıcı + proje kayıtlarını birleştir; aynı adda proje kazanır (Claude Code sırası)."""
    project_names = {server.name for server in project_servers}
    return (
        *(server for server in user_servers if server.name not in project_names),
        *project_servers,
    )


def write_project_mcp_servers(root: Path, servers: tuple[McpServerConfig, ...]) -> Path:
    """Proje kapsamlı kayıtları `.mcp.json`'a yaz; dosyadaki diğer anahtarlar korunur.

    Fusion'ın yazdığı içerik güven kaydına işlenir: kullanıcı eklediği sunucu için ayrıca
    `fusion trust` demek zorunda kalmaz; dosya elle değişirse güven düşer.
    """
    path = project_mcp_path(root)
    existing: dict[str, object] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigError(f"{PROJECT_MCP_FILE} okunamadı: {error}") from error
        if isinstance(loaded, dict):
            existing = loaded
    existing[_ROOT_KEY] = {server.name: _to_entry(server) for server in servers}
    _atomic_write(path, json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
    trust.approve_file(root, path)
    return path


def _to_entry(server: McpServerConfig) -> dict[str, object]:
    entry: dict[str, object] = {}
    if server.transport is McpTransport.STREAMABLE_HTTP:
        entry["type"] = "http"
        entry["url"] = server.url
    else:
        entry["command"] = server.command
        if server.args:
            entry["args"] = list(server.args)
    env: dict[str, str] = dict(server.env_literals)
    # Şifreli depodan gelen sırlar `.mcp.json`'da Claude Code biçimiyle başvuru olur.
    for name in server.env_names:
        env.setdefault(name, f"${{{name}}}")
    if env:
        entry["env"] = env
    return entry


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        temp_path.replace(path)
    except OSError as error:
        temp_path.unlink(missing_ok=True)
        raise ConfigError(f"{PROJECT_MCP_FILE} yazılamadı: {error}") from error
