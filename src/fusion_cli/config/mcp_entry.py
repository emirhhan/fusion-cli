"""Claude Code MCP sunucu girdisi (`mcpServers.<ad>`) ↔ `McpServerConfig`.

`.mcp.json`, yerel kapsam kaydı (`mcp_local.py`), `fusion mcp add-json` ve Claude Desktop
içe aktarması aynı biçimi okur. Belgedeki alanların tümü kabul edilir
(https://code.claude.com/docs/en/mcp — .mcp.json format):

    type (stdio|http|sse|ws; streamable-http = http), command, args, env, url, headers,
    headersHelper, timeout (ms), alwaysLoad, oauth {clientId, callbackPort,
    authServerMetadataUrl, scopes}

Claude Code gibi `type` yoksa girdi stdio sayılır: `url`'si olup `type`'ı olmayan girdi
hatadır (#270). `type: "sdk"` yalnız SDK uygulamalarının kaydedebildiği süreç içi sunucudur;
atlanır. Hatalı girdi `McpEntryError` verir; çağıran o girdiyi atlayıp diğerlerini yükler (#238).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from ..core.errors import ConfigError
from .models import McpScope, McpServerConfig, McpTransport

#: Claude Code `type` değerleri → Fusion taşıması.
TRANSPORTS: Mapping[str, McpTransport] = {
    "stdio": McpTransport.STDIO,
    "http": McpTransport.STREAMABLE_HTTP,
    "streamable_http": McpTransport.STREAMABLE_HTTP,
    "streamable-http": McpTransport.STREAMABLE_HTTP,
    "sse": McpTransport.SSE,
    "ws": McpTransport.WS,
}
#: Belgedeki alanlar. Bilinmeyen alan girdiyi düşürmez; yok sayılır (Claude gibi).
KNOWN_KEYS = frozenset(
    {
        "type",
        "transport",
        "command",
        "args",
        "env",
        "url",
        "headers",
        "headersHelper",
        "timeout",
        "alwaysLoad",
        "oauth",
    }
)
_OAUTH_KEYS = frozenset({"clientId", "callbackPort", "authServerMetadataUrl", "scopes"})
#: `claude mcp` komutlarıyla eklenen adların kuralı (#269).
SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
#: Claude Code'da `timeout` 1000 ms altındaysa yok sayılır.
MIN_TIMEOUT_MS = 1000


class McpEntryError(ConfigError):
    """Tek sunucu girdisi geçersiz; yalnız o girdi atlanır."""


class McpEntrySkippedError(McpEntryError):
    """Girdi geçerli ama bu istemcide yüklenmez (ör. `type: "sdk"`)."""


def valid_server_name(name: str) -> bool:
    return bool(SERVER_NAME_RE.fullmatch(name))


def parse_entry(
    name: str, entry: object, *, scope: McpScope, where: str = "mcpServers"
) -> McpServerConfig:
    """Tek girdiyi kayda çevir; geçersizse `McpEntryError`."""
    here = f"{where}.{name}"
    if not isinstance(entry, dict):
        raise McpEntryError(f"{here}: nesne bekleniyordu")
    kind = str(entry.get("type") or entry.get("transport") or "stdio").strip().lower()
    if kind == "sdk":
        raise McpEntrySkippedError(
            f'Atlandı — MCP sunucusu "{name}" type "sdk" bildiriyor; bunu yalnız SDK '
            "uygulaması süreç içinde kaydedebilir."
        )
    transport = TRANSPORTS.get(kind)
    if transport is None:
        raise McpEntryError(f"{here}.type: '{kind}' desteklenmiyor. Geçerli: stdio, http, sse, ws")
    url = _text(entry.get("url"), f"{here}.url")
    command = _text(entry.get("command"), f"{here}.command")
    if transport is McpTransport.STDIO and not command:
        if url:
            raise McpEntryError(
                f'MCP sunucusu "{name}" bir "url" taşıyor ama "type" yok; bu girdiye '
                '"type": "http" (ya da "sse" / "ws") ekle.'
            )
        raise McpEntryError(f"{here}: stdio sunucusu için 'command' gerekli")
    if transport is not McpTransport.STDIO and not url:
        raise McpEntryError(f"{here}: {kind} sunucusu için 'url' gerekli")
    oauth = _oauth(entry.get("oauth"), f"{here}.oauth")
    return McpServerConfig(
        name=name,
        command=command if transport is McpTransport.STDIO else "",
        args=_texts(entry.get("args"), f"{here}.args") if transport is McpTransport.STDIO else (),
        transport=transport,
        url=url if transport is not McpTransport.STDIO else "",
        env_literals=_pairs(entry.get("env"), f"{here}.env"),
        headers=_pairs(entry.get("headers"), f"{here}.headers"),
        headers_helper=_text(entry.get("headersHelper"), f"{here}.headersHelper"),
        always_load=entry.get("alwaysLoad") is True,
        timeout_ms=_timeout(entry.get("timeout"), f"{here}.timeout"),
        client_id=str(oauth.get("clientId") or ""),
        oauth_callback_port=_port(oauth.get("callbackPort"), f"{here}.oauth.callbackPort"),
        oauth_metadata_url=_metadata_url(oauth.get("authServerMetadataUrl"), here),
        scopes=tuple(str(oauth.get("scopes") or "").split()),
        scope=scope,
    )


def to_entry(server: McpServerConfig) -> dict[str, object]:
    """Kaydı Claude Code girdisine çevir (sırlar `${AD}` başvurusu olarak kalır)."""
    entry: dict[str, object] = {}
    if server.is_remote:
        streamable = server.transport is McpTransport.STREAMABLE_HTTP
        entry["type"] = "http" if streamable else server.transport.value
        entry["url"] = server.url
        if server.headers:
            entry["headers"] = dict(server.headers)
        if server.headers_helper:
            entry["headersHelper"] = server.headers_helper
    else:
        entry["command"] = server.command
        if server.args:
            entry["args"] = list(server.args)
    env: dict[str, str] = dict(server.env_literals)
    for env_name in server.env_names:
        env.setdefault(env_name, f"${{{env_name}}}")
    if env:
        entry["env"] = env
    if server.timeout_ms is not None:
        entry["timeout"] = server.timeout_ms
    if server.always_load:
        entry["alwaysLoad"] = True
    oauth = _oauth_entry(server)
    if oauth:
        entry["oauth"] = oauth
    return entry


def _oauth_entry(server: McpServerConfig) -> dict[str, object]:
    oauth: dict[str, object] = {}
    if server.client_id:
        oauth["clientId"] = server.client_id
    if server.oauth_callback_port is not None:
        oauth["callbackPort"] = server.oauth_callback_port
    if server.oauth_metadata_url:
        oauth["authServerMetadataUrl"] = server.oauth_metadata_url
    if server.scopes:
        oauth["scopes"] = " ".join(server.scopes)
    return oauth


def _oauth(value: object, where: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise McpEntryError(f"{where}: nesne bekleniyordu")
    return {key: item for key, item in value.items() if key in _OAUTH_KEYS}


def _metadata_url(value: object, where: str) -> str:
    text = _text(value, f"{where}.oauth.authServerMetadataUrl")
    if text and not text.lower().startswith("https://"):
        raise McpEntryError(f"{where}.oauth.authServerMetadataUrl: https:// ile başlamalı")
    return text


def _timeout(value: object, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise McpEntryError(f"{where}: milisaniye sayısı bekleniyordu")
    # Claude Code: 1000 altı yok sayılır, MCP_TOOL_TIMEOUT'a düşülür.
    return int(value) if value >= MIN_TIMEOUT_MS else None


def _port(value: object, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 65536:
        raise McpEntryError(f"{where}: 1-65535 arası port bekleniyordu")
    return value


def _text(value: object, where: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise McpEntryError(f"{where}: metin bekleniyordu")
    return value.strip()


def _texts(value: object, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise McpEntryError(f"{where}: metin listesi bekleniyordu")
    return tuple(value)


def _pairs(value: object, where: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise McpEntryError(f"{where}: nesne bekleniyordu")
    pairs: list[tuple[str, str]] = []
    for key, item in value.items():
        if not isinstance(item, str):
            raise McpEntryError(f"{where}.{key}: metin bekleniyordu")
        pairs.append((str(key), item))
    return tuple(pairs)
