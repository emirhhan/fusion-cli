"""Kuruluş MCP denetimi Claude Code gibi (#274): managed-mcp.json, managedMcpServers,
allowedMcpServers / deniedMcpServers, allowManagedMcpServersOnly.

Belge: code.claude.com/docs/en/managed-mcp.

- `managed-mcp.json` (sistem yolu) varsa ve okunabiliyorsa YALNIZ onun sunucuları ile
  `managedMcpServers` yüklenir (tekel); kullanıcı/proje/yerel/eklenti/`--mcp-config` düşer.
- `managedMcpServers` yalnız yönetilen ayar dosyasından okunur; yalnız https `http`/`sse`
  girdileri, `command`/`args`/`env`/`headersHelper` ve `${VAR}` içermeyenler kabul edilir;
  aynı adlı kullanıcı/proje kaydını geçer.
- Ret listesi her kaynaktan birleşir ve her sunucuya uygulanır; ret her şeyi geçer.
- İzin listesi tanımsızsa herkes geçer; `[]` hiçbirini geçirmez. Uzak sunucu `serverUrl`,
  stdio `serverCommand` ile eşleşmeli; `serverName` yalnız o türün girdisi yoksa sayılır.
  Kuruluşun kendi sunucuları (`managedMcpServers`, `${VAR}`'sız managed-mcp.json) atlanır.
- Kuruluş sunucuları `managed` kapsamındadır: kullanıcı dosyasına yazılmaz, kaldırılamaz;
  REPL `/mcp` onları "Managed MCPs" grubunda gösterir.
- Barındırmalı connector'lar (Claude'daki claude.ai connector'larının Fusion karşılığı:
  web sağlayıcısının connector ekranından bağlananlar) tekel varken düşer; yalnız yönetilen
  ayardaki `allowAllClaudeAiMcps: true` onları geri getirir. Ret/izin listesi onlara da uygulanır.
- Politikanın gizlediği kullanıcı kayıtları `Config.mcp_policy_hidden` ile işaretlenir;
  yazıcı onları config.yaml'da korur (politika kullanıcı verisini silmez).

Güvenlik: bu katman yalnız SIKILAŞTIRIR (sunucu düşürür); hiçbir onayı gevşetmez.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from .models import Config, HostedConnectorConfig, McpScope, McpServerConfig, McpTransport

_LOG = logging.getLogger(__name__)

MANAGED_MCP_FILE = "managed-mcp.json"
MANAGED_SETTINGS_FILE = "managed-settings.json"
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_DEFAULT_PORTS = {"https": 443, "http": 80}


def managed_dir() -> Path:
    """Claude Code'un sistem yönetim dizini (platforma göre)."""
    platform = str(sys.platform)  # mypy platform daraltması dalları erişilmez saymasın
    if platform == "darwin":
        return Path("/Library/Application Support/ClaudeCode")
    if platform.startswith("win"):
        return Path(r"C:\Program Files\ClaudeCode")
    return Path("/etc/claude-code")


@dataclass(frozen=True, slots=True)
class McpPolicy:
    exclusive: tuple[McpServerConfig, ...] | None = None
    provided: tuple[McpServerConfig, ...] = ()
    allowed: tuple[Mapping[str, object], ...] | None = None
    denied: tuple[Mapping[str, object], ...] = ()
    #: `allowAllClaudeAiMcps` (yalnız yönetilen ayar): tekel varken connector'lar kalır.
    allow_claude_ai: bool = False

    @property
    def is_empty(self) -> bool:
        unset = self.exclusive is None and self.allowed is None
        return unset and not self.provided and not self.denied


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        _LOG.warning("%s okunamadı: %s", path, error)
        return None
    return raw if isinstance(raw, dict) else None


def settings_layers(root: Path, home: Path) -> tuple[dict[str, object], ...]:
    """Kullanıcı, proje ve yerel Claude ayar dosyaları (yönetilen hariç)."""
    paths = (
        home / ".claude" / "settings.json",
        root / ".claude" / "settings.json",
        root / ".claude" / "settings.local.json",
    )
    return tuple(data for data in (_read_json(path) for path in paths) if data is not None)


def _entries(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping) and len(item) == 1)


def _provided(raw: object) -> tuple[McpServerConfig, ...]:
    from .mcp_json import parse_mcp_servers_report

    if not isinstance(raw, Mapping):
        if raw is not None:
            _LOG.warning("managedMcpServers nesne olmalı; yok sayıldı")
        return ()
    kept: dict[str, object] = {}
    for name, entry in raw.items():
        problem = _provided_problem(str(name), entry)
        if problem:
            _LOG.warning("managedMcpServers.%s atlandı: %s", name, problem)
        else:
            kept[str(name)] = entry
    servers, problems = parse_mcp_servers_report(
        {"mcpServers": kept}, scope=McpScope.MANAGED, where="managedMcpServers"
    )
    for problem in problems:
        _LOG.warning("%s", problem)
    return servers


def _provided_problem(name: str, entry: object) -> str:
    if not _SAFE_NAME.match(name):
        return "ad yalnız harf, rakam, - ve _ içerebilir"
    if not isinstance(entry, Mapping):
        return "girdi nesne olmalı"
    if str(entry.get("type", "")) not in ("http", "sse", "streamable-http"):
        return "type http ya da sse olmalı"
    if not str(entry.get("url", "")).startswith("https://"):
        return "url https:// olmalı"
    if any(key in entry for key in ("command", "args", "env", "headersHelper")):
        return "command/args/env/headersHelper kabul edilmez"
    if "${" in json.dumps(entry):
        return "${VAR} başvurusu kabul edilmez"
    return ""


def load_policy(
    root: Path, *, home: Path | None = None, directory: Path | None = None
) -> McpPolicy:
    """Diskteki yönetilen dosyalardan ve ayar katmanlarından politikayı kur."""
    from .mcp_json import parse_mcp_servers_report

    base = directory or managed_dir()
    managed = _read_json(base / MANAGED_SETTINGS_FILE) or {}
    exclusive_raw = _read_json(base / MANAGED_MCP_FILE)
    exclusive = None
    if exclusive_raw is not None:
        servers, problems = parse_mcp_servers_report(
            exclusive_raw, scope=McpScope.MANAGED, where=MANAGED_MCP_FILE
        )
        for problem in problems:
            _LOG.warning("%s", problem)
        exclusive = servers
    layers = settings_layers(root, home or Path.home())
    allowed_lists = [managed.get("allowedMcpServers")]
    if managed.get("allowManagedMcpServersOnly") is not True:
        allowed_lists.extend(layer.get("allowedMcpServers") for layer in layers)
    defined = [value for value in allowed_lists if isinstance(value, list)]
    allowed = tuple(item for value in defined for item in _entries(value)) if defined else None
    denied = tuple(
        item for layer in (managed, *layers) for item in _entries(layer.get("deniedMcpServers"))
    )
    provided = _provided(managed.get("managedMcpServers"))
    allow_claude_ai = managed.get("allowAllClaudeAiMcps") is True
    return McpPolicy(exclusive, provided, allowed, denied, allow_claude_ai)


def _expand(text: str, environ: Mapping[str, str]) -> str:
    return _VAR.sub(lambda m: environ.get(m.group(1)) or (m.group(2) or ""), text)


_PATTERN = re.compile(
    r"^(?P<scheme>[^:/]+)://(?P<host>\[[^\]]*\]|[^/:]+)(?::(?P<port>[^/]*))?(?P<path>/.*)?$"
)


def url_matches(pattern: str, url: str) -> bool:
    """`serverUrl` eşleşmesi: `*` joker, ana makine harf duyarsız, port kuralı belgedeki gibi."""
    want = _PATTERN.match(pattern.strip())
    try:
        got = urlsplit(url)
        got_port = got.port or _DEFAULT_PORTS.get(got.scheme.lower())
    except ValueError:
        return False
    if want is None:
        return False
    scheme, host = want["scheme"].lower(), want["host"].lower().rstrip(".")
    if not _glob(scheme, got.scheme.lower()):
        return False
    if not _glob(host, (got.hostname or "").lower().rstrip(".")):
        return False
    port = want["port"]
    if port == "*" or (port is None and "*" in host):
        pass
    elif port is not None:
        if not port.isdigit() or int(port) != got_port:
            return False
    elif got_port != _DEFAULT_PORTS.get(got.scheme.lower()):
        return False
    path = want["path"]
    return not path or _glob(path, got.path or "/")


def _glob(pattern: str, text: str) -> bool:
    regex = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.fullmatch(regex, text) is not None


def _matches(entry: Mapping[str, object], server: McpServerConfig, env: Mapping[str, str]) -> bool:
    if "serverName" in entry:
        return entry["serverName"] == server.name
    if "serverUrl" in entry and server.url:
        return url_matches(_expand(str(entry["serverUrl"]), env), _expand(server.url, env))
    command = entry.get("serverCommand")
    if isinstance(command, list) and server.command:
        wanted = [_expand(str(part), env) for part in command]
        return wanted == [_expand(part, env) for part in (server.command, *server.args)]
    return False


def is_denied(server: McpServerConfig, policy: McpPolicy, env: Mapping[str, str]) -> bool:
    return any(_matches(entry, server, env) for entry in policy.denied)


def is_allowed(server: McpServerConfig, policy: McpPolicy, env: Mapping[str, str]) -> bool:
    """İzin listesi denetimi (ret ayrı). Tanımsız liste herkesi geçirir."""
    if policy.allowed is None:
        return True
    remote = server.transport is not McpTransport.STDIO
    strict_key = "serverUrl" if remote else "serverCommand"
    has_strict = any(strict_key in entry for entry in policy.allowed)
    for entry in policy.allowed:
        if "serverName" in entry and has_strict:
            continue
        if (strict_key in entry or "serverName" in entry) and _matches(entry, server, env):
            return True
    return False


def _org_owned(server: McpServerConfig, policy: McpPolicy) -> bool:
    if server.scope is McpScope.MANAGED and policy.exclusive is None:
        return True  # managedMcpServers (yalnız https, ${VAR}'sız) — tekelde aşağıdaki kural
    if any(item.name == server.name for item in policy.provided):
        return True
    owned = policy.exclusive or ()
    values = (server.command, *server.args, server.url)
    return any(item.name == server.name for item in owned) and not any(
        "${" in value for value in values
    )


def filter_servers(
    servers: Sequence[McpServerConfig], policy: McpPolicy, env: Mapping[str, str]
) -> tuple[McpServerConfig, ...]:
    """Politikayı uygula: tekel/sağlanan sunucular, ret ve izin listesi."""
    if policy.exclusive is not None:
        candidates: Iterable[McpServerConfig] = _merge(policy.exclusive, policy.provided)
    else:
        provided = {item.name for item in policy.provided}
        rest = tuple(item for item in servers if item.name not in provided)
        candidates = (*rest, *policy.provided)
    kept: list[McpServerConfig] = []
    for server in candidates:
        if is_denied(server, policy, env):
            _LOG.info("MCP sunucusu ret listesinde: %s", server.name)
        elif not _org_owned(server, policy) and not is_allowed(server, policy, env):
            _LOG.info("MCP sunucusu izin listesinde değil: %s", server.name)
        else:
            kept.append(server)
    return tuple(kept)


def _merge(
    first: Sequence[McpServerConfig], second: Sequence[McpServerConfig]
) -> tuple[McpServerConfig, ...]:
    names = {item.name for item in first}
    return (*first, *(item for item in second if item.name not in names))


def apply_mcp_policy(config: Config, root: Path, *, policy: McpPolicy | None = None) -> Config:
    """`load_config` sonu: yönetilen MCP politikasını yapılandırmaya uygula."""
    active = policy if policy is not None else load_policy(root)
    if active.is_empty:
        return config
    servers = filter_servers(config.mcp_servers, active, os.environ)
    kept = {id(item) for item in servers}
    hidden = {
        item.name
        for item in config.mcp_servers
        if item.scope is McpScope.USER and id(item) not in kept
    }
    previous = tuple(getattr(config, "mcp_policy_hidden", None) or ())
    merged = (*previous, *sorted(hidden - set(previous)))
    return replace(config, mcp_servers=servers, mcp_policy_hidden=merged)


def filter_hosted_connectors(
    connectors: Sequence[HostedConnectorConfig], policy: McpPolicy, env: Mapping[str, str]
) -> tuple[HostedConnectorConfig, ...]:
    """Barındırmalı connector'lara politika (Claude'da claude.ai connector'ları).

    Tekel (`managed-mcp.json`) varken hepsi düşer; yönetilen `allowAllClaudeAiMcps: true`
    tekel yokmuş gibi yükler. Ret ve izin listesi her durumda `serverName`/`serverUrl` ile
    uygulanır.
    """
    if policy.is_empty:
        return tuple(connectors)
    if policy.exclusive is not None and not policy.allow_claude_ai:
        return ()
    kept: list[HostedConnectorConfig] = []
    for connector in connectors:
        probe = McpServerConfig(
            name=connector.name, transport=McpTransport.STREAMABLE_HTTP, url=connector.url
        )
        if is_denied(probe, policy, env) or not is_allowed(probe, policy, env):
            _LOG.info("Barındırmalı connector politika gereği yüklenmedi: %s", connector.name)
        else:
            kept.append(connector)
    return tuple(kept)


#: Claude Code: managed-mcp.json varken `--mcp-config` açılışta bu iletiyle çıkar.
DYNAMIC_CONFIG_REFUSAL = (
    "You cannot dynamically configure MCP servers when an enterprise MCP config is present."
)


def mcp_config_refusal(
    root: Path, *, policy: McpPolicy | None = None, directory: Path | None = None
) -> str | None:
    """`--mcp-config` verilmişken managed-mcp.json tekeli varsa çıkış iletisi."""
    active = policy if policy is not None else load_policy(root, directory=directory)
    return DYNAMIC_CONFIG_REFUSAL if active.exclusive is not None else None


def remove_refusal(
    server: McpServerConfig, root: Path, *, policy: McpPolicy | None = None
) -> str | None:
    """`mcp remove`: kuruluşun sağladığı sunucu kaldırılamaz (Claude Code iletisi)."""
    active = policy if policy is not None else load_policy(root)
    if server.scope is not McpScope.MANAGED and not _org_owned(server, active):
        return None
    return (
        f'Cannot remove MCP server "{server.name}": it is provided by your organization '
        "(kuruluşunuzun sağladığı sunucu düzenlenemez ya da kaldırılamaz)."
    )


def add_refusal(server: McpServerConfig, root: Path, *, policy: McpPolicy | None = None) -> str:
    """`fusion mcp add` reddi (Claude Code iletileri); izinliyse boş."""
    active = policy if policy is not None else load_policy(root)
    if active.exclusive is not None:
        return (
            "Cannot add MCP server: enterprise MCP configuration is active and has exclusive "
            "control over MCP servers"
        )
    if is_denied(server, active, os.environ):
        return (
            f'Cannot add MCP server "{server.name}": server is explicitly blocked by '
            "enterprise policy"
        )
    if not is_allowed(server, active, os.environ):
        return f'Cannot add MCP server "{server.name}": not allowed by enterprise policy'
    return ""
