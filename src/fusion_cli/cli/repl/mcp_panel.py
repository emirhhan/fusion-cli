"""REPL `/mcp` paneli — Claude Code `/mcp` eşdeğeri (#250, #251).

    /mcp                       sunucular, kapsamları ve bağlantı durumları
    /mcp reconnect <ad>|all    yeniden bağlan (`commands.py` işler)
    /mcp auth <ad>             OAuth girişi (tarayıcı açılır)
    /mcp clear-auth <ad>       saklı kimlik bilgilerini sil
    /mcp enable|disable <ad>   sunucuyu bu proje için aç/kapat (disabledMcpServers)
    /mcp tools <ad>            araçlar: tam ad (mcp__<sunucu>__<araç>) ve izin durumu

Ekleme ve kaldırma Claude Code'da CLI'dadır (`fusion mcp add|remove`); eski `/mcp add` ve
`/mcp remove` yardımda gösterilmez, `remove` artık kaydı gerçekten kapsamından siler.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.mcp_local import disabled_mcp_servers, set_mcp_server_enabled
from ...config.models import McpServerConfig
from ...core.errors import ConfigError, FusionError
from ...core.redaction import redact
from ...ui import mcp_messages, messages

if TYPE_CHECKING:
    from .state import ReplState

PANEL_USAGE = (
    "Kullanım: /mcp · /mcp reconnect <ad>|all · /mcp auth <ad> · /mcp clear-auth <ad> · "
    "/mcp enable <ad> · /mcp disable <ad> · /mcp tools <ad>  "
    "(ekleme/kaldırma: fusion mcp add|remove)"
)
_STATE_LABELS = {
    "bagli": mcp_messages.STATUS_CONNECTED,
    "giris_gerekli": mcp_messages.STATUS_NEEDS_AUTH,
    "hata": mcp_messages.STATUS_FAILED,
    "zaman_asimi": mcp_messages.STATUS_FAILED,
}


def _status_label(name: str) -> str:
    try:
        from ...mcp_bridge.pool import mcp_pool_statuses
    except ImportError:
        return "—"
    status = mcp_pool_statuses().get(name)
    if status is None:
        return "henüz bağlanılmadı"
    label = _STATE_LABELS.get(status.state, status.state)
    if status.state == "bagli":
        label += " · " + mcp_messages.TOOL_COUNT.format(count=status.tool_count)
    return label


def _scope_label(server: McpServerConfig) -> str:
    return mcp_messages.SCOPE_LABELS.get(server.scope.value, server.scope.value)


def _target(server: McpServerConfig) -> str:
    return server.url if server.is_remote else " ".join((server.command, *server.args)).strip()


def panel(servers: tuple[McpServerConfig, ...], root: Path | None = None) -> str:
    disabled = sorted(disabled_mcp_servers(root or Path.cwd()))
    if not servers and not disabled:
        return messages.MCP_NO_SERVERS
    lines = [
        redact(
            f"· {server.name} [{_scope_label(server)}"
            f" · {server.transport.value}] {_target(server)} — {_status_label(server.name)}"
        )
        for server in servers
    ]
    lines.extend(f"· {name} {mcp_messages.STATUS_DISABLED}" for name in disabled)
    lines.append(PANEL_USAGE)
    return "\n".join(lines)


def _find(servers: tuple[McpServerConfig, ...], name: str) -> McpServerConfig | None:
    return next((server for server in servers if server.name == name), None)


def handle(state: ReplState, command: str, name: str) -> str | None:
    """Panel alt komutunu işle; bu modüle ait değilse None."""
    servers: tuple[McpServerConfig, ...] = state.config.mcp_servers
    if command in ("enable", "disable"):
        if not name:
            return PANEL_USAGE
        set_mcp_server_enabled(Path.cwd(), name, enabled=command == "enable")
        return _reload(
            state, f"'{name}' bu projede {'açıldı' if command == 'enable' else 'kapatıldı'}."
        )
    if command in ("auth", "clear-auth"):
        server = _find(servers, name)
        if server is None:
            return messages.MCP_NOT_FOUND.format(name=name) if name else PANEL_USAGE
        if not server.is_remote:
            return mcp_messages.LOGOUT_NOT_REMOTE.format(name=name)
        return _auth(server) if command == "auth" else _clear_auth(server)
    if command == "tools":
        from .mcp_tools_view import tools_view

        return tools_view(state, name)
    if command in ("remove", "del", "delete"):
        return _remove(state, name)
    return None


def _auth(server: McpServerConfig) -> str:
    from ...mcp_bridge.service import McpConnectionService
    from ..mcp_manage import run_coroutine

    try:
        status = run_coroutine(McpConnectionService().test(server))
    except FusionError as error:
        return str(error)
    return messages.MCP_LOGIN_RESULT.format(
        name=server.name,
        state=status.state,
        detail=f" — {status.message}" if status.message else "",
    )


def _clear_auth(server: McpServerConfig) -> str:
    from ...mcp_bridge.service import McpConnectionService
    from ..mcp_manage import run_coroutine

    run_coroutine(McpConnectionService().logout(server))
    return mcp_messages.LOGOUT_DONE.format(name=server.name)


def _remove(state: ReplState, name: str) -> str:
    from ..mcp_manage import remove_named

    if not name:
        return messages.MCP_REMOVE_USAGE
    try:
        message, cleared = remove_named(state.config, Path.cwd(), name, None)
    except ConfigError as error:
        return str(error)
    return _reload(state, message + (f"\n{mcp_messages.TOKENS_CLEARED}" if cleared else ""))


def _reload(state: ReplState, message: str) -> str:
    from ...config.loader import load_config

    try:
        fresh = load_config()
    except ConfigError as error:
        return f"{message}\n{messages.MCP_SAVE_FAILED.format(error=error)}"
    state.config = replace(state.config, mcp_servers=fresh.mcp_servers)
    return message
