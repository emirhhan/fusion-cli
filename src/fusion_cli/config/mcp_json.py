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
from pathlib import Path

from ..core.errors import ConfigError
from . import trust
from .mcp_entry import McpEntryError, parse_entry, to_entry
from .models import McpScope, McpServerConfig

_LOG = logging.getLogger(__name__)

#: Proje kökündeki dosya adı (Claude Code ile aynı).
PROJECT_MCP_FILE = ".mcp.json"
_ROOT_KEY = "mcpServers"


def project_mcp_path(root: Path) -> Path:
    return root / PROJECT_MCP_FILE


def read_project_mcp_servers(root: Path) -> tuple[McpServerConfig, ...]:
    """Kökteki `.mcp.json`'ı oku; dosya yoksa boş. Bozuk JSON `ConfigError` (dosya adıyla).

    Hatalı tek girdi dosyayı düşürmez: Claude Code gibi o sunucu atlanır, uyarı yazılır
    ve geçerli girdiler yüklenir (#238).
    """
    servers, problems = read_project_mcp_report(root)
    for problem in problems:
        _LOG.warning("%s", problem)
    return servers


def read_project_mcp_report(root: Path) -> tuple[tuple[McpServerConfig, ...], tuple[str, ...]]:
    """`.mcp.json` sunucuları ve atlanan girdilerin uyarıları (`fusion mcp list` gösterir)."""
    path = project_mcp_path(root)
    if not path.is_file():
        return (), ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"{PROJECT_MCP_FILE} okunamadı: {error}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"{PROJECT_MCP_FILE} geçerli JSON değil: {error}") from error
    return parse_mcp_servers_report(raw, scope=McpScope.PROJECT, where=PROJECT_MCP_FILE)


def parse_mcp_servers_report(
    raw: object, *, scope: McpScope, where: str
) -> tuple[tuple[McpServerConfig, ...], tuple[str, ...]]:
    """`{"mcpServers": {...}}` → (geçerli kayıtlar, atlanan girdi uyarıları)."""
    entries = _entries(raw, where)
    servers: list[McpServerConfig] = []
    problems: list[str] = []
    for name, entry in entries.items():
        try:
            servers.append(
                parse_entry(str(name), entry, scope=scope, where=f"{where}: {_ROOT_KEY}")
            )
        except McpEntryError as error:
            problems.append(f"{where}: {error}")
    return tuple(servers), tuple(problems)


def parse_project_mcp(raw: object) -> tuple[McpServerConfig, ...]:
    """Claude Code `mcpServers` içeriğini kayıtlara çevir; geçersiz girdi `ConfigError`.

    Tek girdi doğrulayan çağıranlar (add-json, eklenti, ajan frontmatter'ı) için katı yol;
    dosya yükleme `parse_mcp_servers_report` ile hatalı girdiyi atlar.
    """
    entries = _entries(raw, PROJECT_MCP_FILE)
    return tuple(
        parse_entry(
            str(name), entry, scope=McpScope.PROJECT, where=f"{PROJECT_MCP_FILE}: {_ROOT_KEY}"
        )
        for name, entry in entries.items()
    )


def _entries(raw: object, where: str) -> dict[object, object]:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: kök bir nesne olmalı")
    servers = raw.get(_ROOT_KEY, {})
    if not isinstance(servers, dict):
        raise ConfigError(f"{where}: '{_ROOT_KEY}' bir nesne olmalı")
    return servers


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
    user_servers: tuple[McpServerConfig, ...],
    project_servers: tuple[McpServerConfig, ...],
    local_servers: tuple[McpServerConfig, ...] = (),
) -> tuple[McpServerConfig, ...]:
    """Kayıtları birleştir; aynı adda öncelik local > project > user (Claude Code, #236).

    Alanlar kapsamlar arasında birleştirilmez: kazanan kaydın tamamı kullanılır.
    """
    local_names = {server.name for server in local_servers}
    project = tuple(server for server in project_servers if server.name not in local_names)
    taken = local_names | {server.name for server in project}
    return (
        *(server for server in user_servers if server.name not in taken),
        *project,
        *local_servers,
    )


UNTRUSTED_WRITE_MESSAGE = (
    f"{PROJECT_MCP_FILE} bu projede güvenilir değil; üzerine yazılmadı. İçeriğini incele, "
    "güveniyorsan `fusion trust` de, sonra yeniden dene."
)


def write_project_mcp_servers(root: Path, servers: tuple[McpServerConfig, ...]) -> Path:
    """Proje kapsamlı kayıtların TÜMÜNÜ `.mcp.json`'a yaz; dosyadaki diğer anahtarlar korunur.

    Tek kayıt eklemek/silmek için `upsert_project_mcp_server` / `remove_project_mcp_server`
    kullan: onlar dosyadaki mevcut girdilere dokunmaz. Fusion'ın yazdığı içerik güven kaydına
    işlenir: kullanıcı eklediği sunucu için ayrıca `fusion trust` demek zorunda kalmaz; dosya
    elle değişirse güven düşer. Güvenilmeyen mevcut dosya üzerine YAZILMAZ (`ConfigError`).
    """
    path = project_mcp_path(root)
    existing = _writable_raw(root, path)
    existing[_ROOT_KEY] = {server.name: to_entry(server) for server in servers}
    return _commit(root, path, existing)


def upsert_project_mcp_server(root: Path, server: McpServerConfig) -> Path:
    """Tek kaydı `.mcp.json`'a ekle ya da aynı adlıyı değiştir; diğer girdiler olduğu gibi kalır.

    Ölçüldü (31 Ekim): `mcpServers` yalnız yüklü (güvenilen) kayıtlardan yeniden kuruluyordu;
    güvenilmeyen bir depoda `--scope project` ekleme takım sunucularını siliyor ve sonucu
    otomatik güvene alıyordu. Artık güvenilmeyen dosya reddedilir, güvenilen dosyada yalnız
    ilgili ad değişir.
    """
    path = project_mcp_path(root)
    existing = _writable_raw(root, path)
    servers = existing.get(_ROOT_KEY)
    entries: dict[str, object] = dict(servers) if isinstance(servers, dict) else {}
    entries[server.name] = to_entry(server)
    existing[_ROOT_KEY] = entries
    return _commit(root, path, existing)


def remove_project_mcp_server(root: Path, name: str) -> Path:
    """Tek kaydı `.mcp.json`'dan sil; ad yoksa `ConfigError`."""
    path = project_mcp_path(root)
    existing = _writable_raw(root, path)
    servers = existing.get(_ROOT_KEY)
    entries: dict[str, object] = dict(servers) if isinstance(servers, dict) else {}
    if name not in entries:
        raise ConfigError(f"{PROJECT_MCP_FILE}: '{name}' adlı sunucu yok")
    del entries[name]
    existing[_ROOT_KEY] = entries
    return _commit(root, path, existing)


def _writable_raw(root: Path, path: Path) -> dict[str, object]:
    """Dosyanın ham içeriği (yoksa boş). Var olan dosya güvenilmiyor ya da bozuksa yazılmaz."""
    if not path.is_file():
        return {}
    if not trust.is_file_trusted(root, path):
        raise ConfigError(UNTRUSTED_WRITE_MESSAGE)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"{PROJECT_MCP_FILE} okunamadı: {error}") from error
    if not isinstance(loaded, dict):
        raise ConfigError(f"{PROJECT_MCP_FILE}: kök bir nesne olmalı; üzerine yazılmadı")
    return loaded


def _commit(root: Path, path: Path, data: dict[str, object]) -> Path:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    trust.approve_file(root, path)
    return path


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
