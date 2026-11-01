"""MCP zaman sınırları — Claude Code değerleri (#233, #239).

https://code.claude.com/docs/en/mcp (Time limits on MCP tool calls),
https://code.claude.com/docs/en/env-vars:

- Araç çağrısı: sunucu `timeout` (ms, ≥1000) > `MCP_TOOL_TIMEOUT` (ms) > 100000000 ms (~28 sa).
- HTTP/SSE istek başına sınır: en büyüğü(60 sn, sunucuya uygulanan araç sınırı, MCP_TIMEOUT);
  ayarlanmamış MCP_TOOL_TIMEOUT'un 28 saatlik varsayılanı bu karşılaştırmaya girmez.
- Boşta kalma: ağ sunucuları 5 dk, stdio 30 dk; `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` (0 = kapalı,
  <1000 → 1 sn, en çok etkin araç sınırı); sunucu `timeout`'u boşta kalmanın alt sınırıdır.
  İlerleme bildirimi boşta kalma sayacını sıfırlar.
- Başlatma: `MCP_TIMEOUT` (ms) > 30000 ms.
- Bloklamayan açılış (varsayılan; `MCP_CONNECTION_NONBLOCKING=0` kapatır): tur başı sunucuları
  en çok `MCP_CONNECT_TIMEOUT_MS` (5000 ms) bekler, geç kalan arka planda bağlanmayı sürdürür.

`config.yaml`'daki eski `connect_timeout_s` / `call_timeout_s` verilmişse önceliklidir.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from ..config.models import McpServerConfig, McpTransport

DEFAULT_TOOL_TIMEOUT_MS = 100_000_000
DEFAULT_STARTUP_TIMEOUT_MS = 30_000
HTTP_REQUEST_FLOOR_MS = 60_000
IDLE_NETWORK_MS = 300_000
IDLE_STDIO_MS = 1_800_000
MIN_MS = 1000
#: SSE akışında boşta kalma kapalıyken okuma sınırı (SDK'ya sonlu bir değer gerekir).
MAX_SSE_READ_S = DEFAULT_TOOL_TIMEOUT_MS / 1000

TOOL_TIMEOUT_ENV = "MCP_TOOL_TIMEOUT"
STARTUP_TIMEOUT_ENV = "MCP_TIMEOUT"
IDLE_TIMEOUT_ENV = "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT"


def _env_ms(name: str, environ: Mapping[str, str] | None) -> int | None:
    raw = (os.environ if environ is None else environ).get(name, "").strip()
    return int(raw) if raw.isdigit() else None


def _server_ms(config: McpServerConfig) -> int | None:
    value = config.timeout_ms
    return value if value is not None and value >= MIN_MS else None


def tool_timeout_ms(config: McpServerConfig, environ: Mapping[str, str] | None = None) -> int:
    """Araç çağrısının duvar saati sınırı (ms)."""
    if config.call_timeout_s is not None:
        return int(config.call_timeout_s * 1000)
    env = _env_ms(TOOL_TIMEOUT_ENV, environ)
    return _server_ms(config) or (env if env else None) or DEFAULT_TOOL_TIMEOUT_MS


def tool_timeout_s(config: McpServerConfig, environ: Mapping[str, str] | None = None) -> float:
    return tool_timeout_ms(config, environ) / 1000


def startup_timeout_s(config: McpServerConfig, environ: Mapping[str, str] | None = None) -> float:
    """Sunucu başlatma/bağlanma sınırı (sn)."""
    if config.connect_timeout_s is not None:
        return config.connect_timeout_s
    env = _env_ms(STARTUP_TIMEOUT_ENV, environ)
    return (env if env else DEFAULT_STARTUP_TIMEOUT_MS) / 1000


def http_request_timeout_s(
    config: McpServerConfig, environ: Mapping[str, str] | None = None
) -> float:
    """HTTP/SSE istek başına sınır (sn)."""
    candidates = [HTTP_REQUEST_FLOOR_MS]
    explicit = _server_ms(config) or _env_ms(TOOL_TIMEOUT_ENV, environ)
    if config.call_timeout_s is not None:
        explicit = int(config.call_timeout_s * 1000)
    if explicit:
        candidates.append(explicit)
    startup = _env_ms(STARTUP_TIMEOUT_ENV, environ)
    if startup:
        candidates.append(startup)
    return max(candidates) / 1000


def idle_timeout_s(
    config: McpServerConfig, environ: Mapping[str, str] | None = None
) -> float | None:
    """Yanıt ve ilerleme gelmeden beklenecek en uzun süre (sn); None = kapalı."""
    env = _env_ms(IDLE_TIMEOUT_ENV, environ)
    if env == 0:
        return None
    if env is not None:
        window = max(env, MIN_MS)
    else:
        window = IDLE_STDIO_MS if config.transport is McpTransport.STDIO else IDLE_NETWORK_MS
    server = _server_ms(config)
    if server is not None:
        window = max(window, server)
    return min(window, tool_timeout_ms(config, environ)) / 1000


#: Bloklamayan açılışta tur başının sunucuları toplu bekleme süresi (Claude 5 sn).
DEFAULT_CONNECT_WAIT_MS = 5_000
CONNECT_WAIT_ENV = "MCP_CONNECT_TIMEOUT_MS"
NONBLOCKING_ENV = "MCP_CONNECTION_NONBLOCKING"
_OFF_WORDS = frozenset({"0", "false", "no", "off"})


def connection_nonblocking(environ: Mapping[str, str] | None = None) -> bool:
    """Varsayılan açık: bağlanmayı bitirmeyen sunucu arka planda bağlanmaya devam eder.

    `MCP_CONNECTION_NONBLOCKING=0` açılışı bütün sunucuları (başlatma sınırına kadar)
    beklemeye zorlar (#239).
    """
    raw = (os.environ if environ is None else environ).get(NONBLOCKING_ENV, "").strip().lower()
    return raw not in _OFF_WORDS


def connect_wait_s(environ: Mapping[str, str] | None = None) -> float:
    """Bloklamayan açılışta sunucuların toplu bekleme süresi (`MCP_CONNECT_TIMEOUT_MS`)."""
    env = _env_ms(CONNECT_WAIT_ENV, environ)
    return (env if env else DEFAULT_CONNECT_WAIT_MS) / 1000
