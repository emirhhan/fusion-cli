"""`fusion mcp list|get|remove|logout` — Claude Code yönetim komutları (#243, #261, #266, #272).

- `list` her sunucuyu yoklar: ✔ Bağlandı · ! Kimlik doğrulama gerekli · ✘ Bağlanılamadı;
  eksik `${VAR}` ve atlanan `.mcp.json` girdileri uyarı olarak görünür.
- `get <ad>` tek sunucunun kapsamını, taşımasını, hedefini, başlık/ortam ADLARINI ve
  OAuth ayarını gösterir (`${VAR}` başvuruları adıyla, değerler basılmaz).
- `remove <ad> [--scope]` kaydı kapsamından siler ve o adresin saklı OAuth token'larını
  ve istemci sırrını yerelde temizler.
- `logout <ad>` saklı kimlik bilgilerini siler.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
from collections.abc import Coroutine, Iterable
from pathlib import Path
from typing import Any, NoReturn, TypeVar

import typer
from rich.console import Console
from rich.markup import escape

from ..config import trust
from ..config.loader import load_config
from ..config.mcp_json import project_mcp_path, read_project_mcp_report, remove_project_mcp_server
from ..config.mcp_local import read_local_mcp_report, remove_local_mcp_server
from ..config.models import Config, McpScope, McpServerConfig
from ..config.writer import read_user_mcp_entries, remove_user_mcp_server
from ..core.env_refs import missing_refs
from ..core.errors import ConfigError
from ..core.redaction import redact
from ..ui import mcp_messages, messages, theme

console = Console()
_T = TypeVar("_T")

#: `list` yoklaması sunucu başına bu kadar bekler (Claude MCP_TIMEOUT varsayılanı 30 sn).
HEALTH_TIMEOUT_S = 30.0


def target_text(server: McpServerConfig) -> str:
    """Komut satırı ya da adres; `${VAR}` başvuruları çözülmeden, adıyla."""
    return server.url if server.is_remote else " ".join((server.command, *server.args)).strip()


def missing_variables(server: McpServerConfig, environ: object = None) -> tuple[str, ...]:
    source = os.environ if environ is None else environ
    texts: Iterable[str] = (
        server.command,
        *server.args,
        server.url,
        *(value for _, value in server.headers),
        *(value for _, value in server.env_literals),
    )
    names: dict[str, None] = {}
    for text in texts:
        names.update(dict.fromkeys(missing_refs(text, source)))  # type: ignore[arg-type]
    return tuple(names)


async def _health(server: McpServerConfig) -> str:
    from ..mcp_bridge.client import McpClient
    from ..mcp_bridge.failures import STATE_CONNECTED, STATE_LOGIN_REQUIRED

    try:
        async with asyncio.timeout(HEALTH_TIMEOUT_S):
            async with McpClient((server,), interactive=False) as client:
                state = getattr(client.statuses.get(server.name), "state", "")
    except Exception:
        return mcp_messages.STATUS_FAILED
    if state == STATE_CONNECTED:
        return mcp_messages.STATUS_CONNECTED
    if state == STATE_LOGIN_REQUIRED:
        return mcp_messages.STATUS_NEEDS_AUTH
    return mcp_messages.STATUS_FAILED


async def _all_health(servers: tuple[McpServerConfig, ...]) -> list[str]:
    return list(await asyncio.gather(*(_health(server) for server in servers)))


def list_servers() -> None:
    """Kayıtlı MCP sunucularını durumlarıyla listele (Claude Code `claude mcp list`)."""
    config = load_config()
    pending = _pending_project_servers(config)
    if not config.mcp_servers and not pending:
        console.print(messages.MCP_NO_SERVERS)
        _print_problems()
        return
    console.print(f"[{theme.DIM}]{mcp_messages.CHECKING_HEALTH}[/{theme.DIM}]")
    statuses = asyncio.run(_all_health(config.mcp_servers)) if config.mcp_servers else []
    for server, status in zip(config.mcp_servers, statuses, strict=True):
        _print_row(server, status)
    for server in pending:
        _print_row(server, mcp_messages.STATUS_PENDING)
    _print_problems()


def _print_row(server: McpServerConfig, status: str) -> None:
    label = mcp_messages.SCOPE_LABELS.get(server.scope.value, server.scope.value)
    console.print(escape(redact(f"{server.name}: {target_text(server)} ({label}) - {status}")))
    missing = missing_variables(server)
    if missing:
        console.print(
            f"[{theme.WARN}]"
            + escape(mcp_messages.MISSING_VAR.format(name=server.name, names=", ".join(missing)))
            + f"[/{theme.WARN}]"
        )


def _pending_project_servers(config: Config) -> tuple[McpServerConfig, ...]:
    """Güven onayı bekleyen `.mcp.json` sunucuları (Claude: ⏸ Pending approval)."""
    root = Path.cwd()
    path = project_mcp_path(root)
    if not path.is_file() or trust.is_file_trusted(root, path):
        return ()
    try:
        servers, _ = read_project_mcp_report(root)
    except ConfigError:
        return ()
    taken = {server.name for server in config.mcp_servers}
    return tuple(server for server in servers if server.name not in taken)


def _print_problems() -> None:
    root = Path.cwd()
    problems: list[str] = []
    for report in (read_project_mcp_report, read_local_mcp_report):
        try:
            problems.extend(report(root)[1])
        except ConfigError as error:
            problems.append(str(error))
    for problem in problems:
        console.print(
            f"[{theme.WARN}]"
            + escape(mcp_messages.SKIPPED_ENTRY.format(problem=problem))
            + f"[/{theme.WARN}]"
        )


def get_server(name: str) -> None:
    """Tek sunucunun ayrıntısı (Claude Code `claude mcp get`)."""
    server = _find_any(load_config(), name)
    label = mcp_messages.SCOPE_LABELS.get(server.scope.value, server.scope.value)
    lines = [
        f"{server.name}:",
        f"  Kapsam: {label} ({server.scope.value})",
        f"  Durum: {asyncio.run(_health(server))}",
        f"  Tür: {server.transport.value}",
        f"  {'URL' if server.is_remote else 'Komut'}: {target_text(server)}",
    ]
    if server.env_literals or server.env_names:
        names = [key for key, _ in server.env_literals] + list(server.env_names)
        lines.append(f"  Ortam: {', '.join(names)}")
    if server.headers:
        lines.append(f"  Başlıklar: {', '.join(key for key, _ in server.headers)}")
    if server.headers_helper:
        lines.append(f"  headersHelper: {server.headers_helper}")
    if server.client_id or server.oauth_callback_port is not None:
        port = server.oauth_callback_port
        lines.append(
            f"  OAuth: client_id={server.client_id or '-'}"
            + (f", callbackPort={port}" if port is not None else "")
        )
    for line in lines:
        console.print(escape(redact(line)))
    missing = missing_variables(server)
    if missing:
        console.print(escape(mcp_messages.MISSING_VAR.format(name=name, names=", ".join(missing))))
    console.print(f"\n[{theme.DIM}]Kaldırmak için: fusion mcp remove \"{name}\" -s {server.scope.value}[/{theme.DIM}]")


def _find_any(config: Config, name: str) -> McpServerConfig:
    server = next((item for item in config.mcp_servers if item.name == name), None)
    if server is None:
        server = next((item for item in _pending_project_servers(config) if item.name == name), None)
    if server is None:
        console.print(f"[{theme.ERROR}]{messages.MCP_NOT_FOUND.format(name=name)}[/{theme.ERROR}]")
        raise typer.Exit(code=1)
    return server


def _candidates(config: Config, root: Path) -> list[McpServerConfig]:
    """Adın bütün kapsamlardaki kayıtları (gölgelenenler dahil)."""
    found: list[McpServerConfig] = []
    for report in (read_local_mcp_report, read_project_mcp_report):
        try:
            found.extend(report(root)[0])
        except ConfigError:
            continue
    user_names = {
        entry.get("name") for entry in read_user_mcp_entries(config) if entry.get("name")
    }
    found.extend(
        McpServerConfig(name=str(name), scope=McpScope.USER)
        for name in user_names
        if not any(item.name == name and item.scope is McpScope.USER for item in config.mcp_servers)
    )
    found.extend(
        item for item in config.mcp_servers if item.scope in (McpScope.USER, McpScope.PLUGIN)
    )
    return found


def remove_server(name: str, scope: str | None) -> None:
    """Kaydı kapsamından sil; saklı OAuth bilgilerini temizle (Claude Code `claude mcp remove`)."""
    try:
        message, cleared = remove_named(load_config(), Path.cwd(), name, scope)
    except ConfigError as error:
        _fail(str(error))
    console.print(message)
    if cleared:
        console.print(f"[{theme.DIM}]{mcp_messages.TOKENS_CLEARED}[/{theme.DIM}]")


def remove_named(
    config: Config, root: Path, name: str, scope: str | None
) -> tuple[str, bool]:
    """CLI ve REPL ortak kaldırma gövdesi → (mesaj, kimlik bilgisi silindi mi) (#251, #272)."""
    matches = [item for item in _candidates(config, root) if item.name == name]
    if scope is not None:
        matches = [item for item in matches if item.scope.value == scope.strip().lower()]
        if not matches:
            raise ConfigError(mcp_messages.NOT_IN_SCOPE.format(name=name, scope=scope))
    if not matches:
        raise ConfigError(messages.MCP_NOT_FOUND.format(name=name))
    if len({item.scope for item in matches}) > 1:
        scopes = ", ".join(item.scope.value for item in matches)
        raise ConfigError(mcp_messages.AMBIGUOUS_SCOPE.format(name=name, scopes=scopes))
    target = matches[0]
    message = _remove_from_scope(config, root, target)
    if target.is_remote and not any(item.url == target.url for item in load_config().mcp_servers):
        run_coroutine(_clear_credentials(target))
        return message, True
    return message, False


def run_coroutine(coroutine: Coroutine[Any, Any, _T]) -> _T:
    """Çalışan olay döngüsü olsa da (REPL) eşzamansız işi ayrı iş parçacığında bitir."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coroutine).result()


def _remove_from_scope(config: Config, root: Path, target: McpServerConfig) -> str:
    if target.scope is McpScope.PLUGIN:
        raise ConfigError(messages.EKLENTI_MCP_REMOVE.format(name=target.name))
    if target.scope is McpScope.PROJECT:
        remove_project_mcp_server(root, target.name)
        return messages.MCP_PROJECT_REMOVED.format(name=target.name)
    if target.scope is McpScope.LOCAL:
        remove_local_mcp_server(root, target.name)
        return mcp_messages.LOCAL_REMOVED.format(name=target.name)
    remove_user_mcp_server(config, target.name)
    return messages.MCP_REMOVED.format(name=target.name)


async def _clear_credentials(server: McpServerConfig) -> None:
    from ..mcp_bridge.tokens import KeyringTokenStorage

    await KeyringTokenStorage(server.url).clear(include_secret=True)


def logout(name: str) -> None:
    """Saklı OAuth kimlik bilgilerini sil (Claude Code `claude mcp logout`)."""
    server = _find_any(load_config(), name)
    if not server.is_remote:
        _fail(mcp_messages.LOGOUT_NOT_REMOTE.format(name=name))
    from ..mcp_bridge.service import McpConnectionService

    asyncio.run(McpConnectionService().logout(server))
    console.print(mcp_messages.LOGOUT_DONE.format(name=name))


def _fail(text: str) -> NoReturn:
    console.print(f"[{theme.ERROR}]{escape(text)}[/{theme.ERROR}]")
    raise typer.Exit(code=1)
