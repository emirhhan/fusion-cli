"""`fusion mcp` alt grubu — Claude Code `claude mcp …` paritesi (P-049).

    fusion mcp                       → Fusion araçlarını MCP sunucusu olarak aç (eski davranış)
    fusion mcp add <ad> <komut> …    → dış sunucu ekle (--transport, --scope, --env, --token-env)
    fusion mcp add-json <ad> <json>  → Claude Code JSON tanımıyla ekle
    fusion mcp remove|list|tools|prompts|resources|login|reconnect

Eski `fusion mcp-add` / `fusion mcp-tools` komutları aynı işlevlere bağlı takma ad olarak
kalır. Kapsamlar: `user` kullanıcının `config.yaml`'ı, `project` kökteki `.mcp.json`
(Claude Code ile ortak biçim; yalnız güvenilen projede yüklenir).

Ölçüldü (31 Ekim): `mcp-add` yalnız stdio, kapsamsız; `.mcp.json`, `${VAR:-default}`,
`login`, `reconnect` yoktu.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from ..config.loader import load_config
from ..config.mcp_json import (
    parse_project_mcp,
    upsert_project_mcp_server,
)
from ..config.mcp_local import upsert_local_mcp_server
from ..config.models import Config, McpScope, McpServerConfig, McpTransport
from ..config.writer import write_mcp_servers
from ..core.errors import ConfigError, FusionError
from ..ui import mcp_messages, messages, theme
from . import mcp_add, mcp_manage, mcp_reference_commands

console = Console()

#: Bağlanıp araç listeleme için üst süre; bağlanamayan sunucu komutu sonsuza dek bekletmesin.
MCP_TOOLS_TIMEOUT_S = 60.0
#: OAuth girişi tarayıcıda kullanıcıyı bekler; araç listesinden daha uzun.
MCP_LOGIN_TIMEOUT_S = 300.0

#: `--transport` değerleri (Claude Code adları) → Fusion taşıması.
_TRANSPORT_ALIASES = {
    "stdio": McpTransport.STDIO,
    "http": McpTransport.STREAMABLE_HTTP,
    "streamable_http": McpTransport.STREAMABLE_HTTP,
    "streamable-http": McpTransport.STREAMABLE_HTTP,
    "sse": McpTransport.SSE,
}

mcp_app = typer.Typer(
    help="Dış MCP sunucularını yönet (Claude Code `claude mcp`); `serve` Fusion'ı sunucu açar.",
    invoke_without_command=True,
)


@mcp_app.callback()
def mcp(
    ctx: typer.Context,
    write: bool = typer.Option(False, "--write", hidden=True),
) -> None:
    """MCP sunucularını yapılandır ve yönet.

    Alt komutsuz çağrı Claude Code gibi yardımı gösterir. Eski davranış (stdin bir MCP
    istemcisine bağlıyken `fusion mcp` → salt-okunur sunucu) bir sürüm boyunca korunur;
    yeni yapılandırmalarda `fusion mcp serve` kullan.
    """
    if ctx.invoked_subcommand is not None:
        return
    if sys.stdin.isatty():
        typer.echo(ctx.get_help())
        return
    # DİKKAT: stdout MCP protokolüne aittir; uyarı yalnız stderr'e.
    typer.echo(mcp_messages.DEPRECATED_BARE_MCP, err=True)
    _serve(expose_mutating=write)


@mcp_app.command("serve")
def serve() -> None:
    """Fusion'ı stdio MCP sunucusu olarak aç (Claude Code `claude mcp serve`).

    Fusion'ın araçlarının tümü sunulur; araç çağrılarının onayı bağlanan MCP istemcisinin
    işidir (Claude Code belgesi). Açılışta hiçbir şey basılmaz.
    """
    _serve(expose_mutating=True)


def _serve(*, expose_mutating: bool) -> None:
    try:
        from ..mcp_bridge.server import run_stdio
    except ImportError:
        typer.echo(messages.MCP_MISSING_DEP, err=True)
        raise typer.Exit(code=1) from None
    asyncio.run(run_stdio(Path.cwd(), expose_mutating=expose_mutating))


# --------------------------------------------------------------------------- #
# add / add-json / remove / list
# --------------------------------------------------------------------------- #


def _parse_scope(raw: str) -> McpScope:
    try:
        value = McpScope(raw.strip().lower())
        if value is McpScope.PLUGIN:
            raise ValueError(raw)
        return value
    except ValueError:
        valid = "local, project, user"
        raise typer.BadParameter(f"Bilinmeyen kapsam: {raw}. Geçerli olanlar: {valid}") from None


def _parse_transport(raw: str) -> McpTransport:
    if raw.strip().lower() == "ws":
        raise typer.BadParameter(mcp_messages.WS_NOT_FOR_ADD)
    transport = _TRANSPORT_ALIASES.get(raw.strip().lower())
    if transport is None:
        raise typer.BadParameter(
            f"Bilinmeyen taşıma: {raw}. Geçerli olanlar: {', '.join(_TRANSPORT_ALIASES)}"
        )
    return transport


def save_server(config: Config, server: McpServerConfig, *, root: Path) -> tuple[Path, bool]:
    """Sunucuyu kapsamının dosyasına yaz; (yol, aynı ad vardı mı) döner.

    Aynı ad başka kapsamda da varsa oradan DÜŞÜRÜLMEZ: proje kaydı kullanıcı kaydını
    yükleme sırasında zaten geçer; kullanıcı kaydını silmek onun verisine dokunmak olur
    (gölgelenen kullanıcı kaydını `config.writer._shadowed_user_entries` korur). Proje
    kaydı `.mcp.json`'da yalnız kendi adını değiştirir; güvenilmeyen dosya reddedilir.
    """
    same_scope = tuple(item for item in config.mcp_servers if item.scope is server.scope)
    replaced = any(item.name == server.name for item in same_scope)
    if server.scope is McpScope.PROJECT:
        return upsert_project_mcp_server(root, server), replaced
    if server.scope is McpScope.LOCAL:
        return upsert_local_mcp_server(root, server), replaced
    others = tuple(item for item in config.mcp_servers if item.scope is not server.scope)
    kept = tuple(item for item in same_scope if item.name != server.name)
    return write_mcp_servers(replace(config, mcp_servers=(*others, *kept, server))), replaced


def _save_or_exit(config: Config, server: McpServerConfig) -> tuple[Path, bool]:
    """`save_server`; yazma reddi (güvenilmeyen/bozuk `.mcp.json`) Türkçe hata ve çıkış 1."""
    from ..config.mcp_policy import add_refusal

    refusal = add_refusal(server, Path.cwd())  # kuruluş politikası (#274)
    if refusal:
        console.print(f"[{theme.ERROR}]{escape(refusal)}[/{theme.ERROR}]")
        raise typer.Exit(code=1)
    try:
        return save_server(config, server, root=Path.cwd())
    except ConfigError as error:
        console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
        raise typer.Exit(code=1) from None


def _announce_saved(server: McpServerConfig, path: Path, replaced: bool) -> None:
    if server.scope is McpScope.LOCAL:
        console.print(mcp_messages.LOCAL_ADDED.format(name=server.name))
        console.print(f"[{theme.DIM}]{path}[/{theme.DIM}]")
        return
    if server.scope is McpScope.PROJECT:
        console.print(messages.MCP_PROJECT_ADDED.format(name=server.name, path=path))
        return
    template = messages.MCP_REPLACED if replaced else messages.MCP_ADDED
    console.print(template.format(name=server.name))
    console.print(f"[{theme.DIM}]{path}[/{theme.DIM}]")


@mcp_app.command("add")
def add(
    name: Annotated[str, typer.Argument(help="Sunucu adı (harf, rakam, - ve _).")],
    command: Annotated[
        str, typer.Argument(help="stdio'da çalıştırılacak komut; http/sse'de sunucu adresi.")
    ] = "",
    args: Annotated[
        list[str] | None,
        typer.Argument(help="Komuta verilecek argümanlar. `-` ile başlıyorsa önce -- koy."),
    ] = None,
    transport: str = typer.Option("stdio", "--transport", "-t", help="stdio | http | sse"),
    scope: str = typer.Option(
        "local",
        "--scope",
        "-s",
        help="local (varsayılan; yalnız bu proje, paylaşılmaz) | project (.mcp.json) | user",
    ),
    env: Annotated[
        list[str] | None,
        typer.Option("--env", "-e", help="Ortam değişkeni KEY=value (tekrarlanabilir)."),
    ] = None,
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help='Uzak sunucu başlığı "Ad: değer" (tekrarlanabilir).'),
    ] = None,
    client_id: str = typer.Option("", "--client-id", help="Önceden kayıtlı OAuth istemci kimliği."),
    client_secret: bool = typer.Option(
        False, "--client-secret", help="OAuth istemci sırrını sor (ya da MCP_CLIENT_SECRET)."
    ),
    callback_port: int | None = typer.Option(
        None, "--callback-port", help="Sabit OAuth dönüş portu (http://localhost:PORT/callback)."
    ),
    url: str = typer.Option("", "--url", hidden=True),
    token_env: str = typer.Option("", "--token-env", hidden=True),
) -> None:
    """Dış bir MCP sunucusu ekle (Claude Code `claude mcp add` sözdizimi).

    Örnekler:
      fusion mcp add --transport http notion https://mcp.notion.com/mcp
      fusion mcp add --transport http api https://api.example.com/mcp \\
        -H "Authorization: Bearer ${API_KEY}"
      fusion mcp add airtable -e AIRTABLE_API_KEY=anahtar -- npx -y airtable-mcp-server

    Argümanlar `-` ile başlıyorsa Typer'ın seçenek sanmaması için `--` şart.
    """
    add_server(
        name,
        command,
        tuple(args or ()),
        transport=transport,
        url=url,
        scope=scope,
        env=tuple(env or ()),
        token_env=token_env,
        headers=tuple(header or ()),
        client_id=client_id,
        client_secret=client_secret,
        callback_port=callback_port,
    )


def add_server(
    name: str,
    command: str,
    args: tuple[str, ...],
    *,
    transport: str = "stdio",
    url: str = "",
    scope: str = "local",
    env: tuple[str, ...] = (),
    token_env: str = "",
    headers: tuple[str, ...] = (),
    client_id: str = "",
    client_secret: bool = False,
    callback_port: int | None = None,
) -> McpServerConfig:
    """`add` gövdesi; eski `fusion mcp-add` takma adı da bunu çağırır."""
    server_name = mcp_add.check_name(name)
    kind = _parse_transport(transport)
    target_scope = _parse_scope(scope)
    mcp_add.check_oauth_flags(kind, client_id, client_secret, callback_port)
    env_names, env_literals = mcp_add.split_env(env)
    remote_url = ""
    if kind is not McpTransport.STDIO:
        remote_url, args = mcp_add.remote_target(kind, command, args, url, server_name)
        if not remote_url:
            raise typer.BadParameter(messages.MCP_ADD_NEEDS_URL)
        from ..mcp_bridge.oauth import validate_remote_mcp_url

        validate_remote_mcp_url(remote_url)
    elif not command.strip():
        raise typer.BadParameter(messages.MCP_ADD_NEEDS_COMMAND)
    if token_env.strip():
        typer.echo(mcp_messages.DEPRECATED_TOKEN_ENV.format(name=token_env.strip()), err=True)
        if target_scope is McpScope.PROJECT:
            raise typer.BadParameter(messages.MCP_PROJECT_NO_TOKEN_ENV)
    server = McpServerConfig(
        name=server_name,
        command=command.strip() if kind is McpTransport.STDIO else "",
        args=args if kind is McpTransport.STDIO else (),
        transport=kind,
        url=remote_url,
        env_names=env_names,
        token_env=token_env.strip(),
        scope=target_scope,
        env_literals=env_literals,
        headers=mcp_add.parse_headers(headers) if kind is not McpTransport.STDIO else (),
        client_id=client_id.strip(),
        oauth_callback_port=callback_port,
    )
    secret = mcp_add.read_client_secret(client_secret)
    path, replaced = _save_or_exit(load_config(), server)
    if secret:
        asyncio.run(mcp_add.store_client_secret(server, secret))
        console.print(mcp_messages.CLIENT_SECRET_STORED)
    _announce_saved(server, path, replaced)
    return server


def split_env_options(
    raw: Iterable[str] | None,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """`--env AD` → sır adı (şifreli depodan); `--env AD=değer` → sır olmayan değer."""
    names: list[str] = []
    literals: list[tuple[str, str]] = []
    for item in raw or ():
        text = item.strip()
        if not text:
            continue
        if "=" in text:
            key, value = text.split("=", 1)
            literals.append((key.strip(), value))
        else:
            names.append(text)
    return tuple(names), tuple(literals)


@mcp_app.command("add-json")
def add_json(
    name: Annotated[str, typer.Argument(help="Sunucu adı.")],
    definition: Annotated[
        str,
        typer.Argument(
            help='Claude Code JSON tanımı: \'{"command":"npx","args":["-y","x"],"env":{...}}\''
        ),
    ],
    scope: str = typer.Option("local", "--scope", "-s", help="local | project | user"),
    client_secret: bool = typer.Option(
        False, "--client-secret", help="OAuth istemci sırrını sor (ya da MCP_CLIENT_SECRET)."
    ),
) -> None:
    """Claude Code `claude mcp add-json` biçimindeki tanımla sunucu ekle."""
    mcp_add.check_name(name)
    target_scope = _parse_scope(scope)
    try:
        raw = json.loads(definition)
    except json.JSONDecodeError as error:
        raise typer.BadParameter(messages.MCP_ADD_JSON_INVALID.format(error=error)) from None
    try:
        (parsed,) = parse_project_mcp({"mcpServers": {name.strip(): raw}})
    except ConfigError as error:
        raise typer.BadParameter(str(error)) from None
    server = replace(parsed, scope=target_scope)
    mcp_add.check_oauth_flags(server.transport, "", client_secret, None)
    secret = mcp_add.read_client_secret(client_secret)
    path, replaced = _save_or_exit(load_config(), server)
    if secret:
        asyncio.run(mcp_add.store_client_secret(server, secret))
        console.print(mcp_messages.CLIENT_SECRET_STORED)
    _announce_saved(server, path, replaced)


@mcp_app.command("remove")
def remove(
    name: Annotated[str, typer.Argument(help="Kaldırılacak sunucunun adı.")],
    scope: str | None = typer.Option(
        None, "--scope", "-s", help="local | project | user (ad birden çok kapsamdaysa şart)"
    ),
) -> None:
    """Sunucuyu kapsamından kaldır; o adresin saklı OAuth bilgileri de silinir."""
    mcp_manage.remove_server(name, scope)


@mcp_app.command("list")
def list_servers() -> None:
    """Kayıtlı MCP sunucularını bağlantı durumlarıyla listele."""
    mcp_manage.list_servers()


@mcp_app.command("add-from-claude-desktop")
def add_from_claude_desktop(
    scope: str = typer.Option("local", "--scope", "-s", help="local | project | user"),
) -> None:
    """Claude Desktop'taki MCP sunucularını seçerek içe aktar (macOS ve WSL)."""
    from .mcp_desktop_import import add_from_claude_desktop as _import

    _import(scope)


@mcp_app.command("get")
def get(name: Annotated[str, typer.Argument(help="Sunucu adı.")]) -> None:
    """Tek sunucunun ayrıntısını göster (kapsam, durum, taşıma, hedef, OAuth)."""
    mcp_manage.get_server(name)


@mcp_app.command("logout")
def logout(name: Annotated[str, typer.Argument(help="Sunucu adı.")]) -> None:
    """Uzak sunucunun saklı OAuth kimlik bilgilerini sil."""
    mcp_manage.logout(name)


# --------------------------------------------------------------------------- #
# tools / login / reconnect  (bağlanan komutlar)
# --------------------------------------------------------------------------- #


def _run_connected(
    coro_factory: Callable[[], Coroutine[object, object, None]],
    *,
    timeout_s: float,
    timeout_message: str,
) -> None:
    """Bağlanan komutların ortak sınır katmanı: zaman aşımı ve Türkçe hata."""
    try:
        asyncio.run(asyncio.wait_for(coro_factory(), timeout=timeout_s))
    except FusionError:
        raise
    except TimeoutError as error:
        raise FusionError(timeout_message) from error
    except Exception as error:
        raise FusionError(messages.MCP_CONNECT_FAILED.format(error=error)) from error


# İstem/kaynak listeleri ayrı modülde (P-049); komut adları bu alt grupta.
mcp_app.command("prompts", hidden=True)(mcp_reference_commands.prompts)
mcp_app.command("resources", hidden=True)(mcp_reference_commands.resources)


@mcp_app.command("tools", hidden=True)
def tools() -> None:
    """Yapılandırılmış dış MCP sunucularının araçlarını listele (bağlanır ve keşfeder)."""
    list_remote_tools(load_config(), timeout_s=MCP_TOOLS_TIMEOUT_S)


def list_remote_tools(config: Config, *, timeout_s: float) -> None:
    """`tools` gövdesi; eski `fusion mcp-tools` takma adı kendi zaman aşımıyla çağırır."""
    if not config.mcp_servers:
        console.print(messages.MCP_NO_SERVERS)
        return
    try:
        from ..mcp_bridge.client import McpClient
    except ImportError:
        console.print(f"[red]{messages.MCP_MISSING_DEP}[/red]")
        raise typer.Exit(code=1) from None

    async def _run() -> None:
        async with McpClient(config.mcp_servers) as client:
            for server in config.mcp_servers:
                remote_tools = await client.list_tools(server.name)
                console.print(f"[bold]{escape(server.name)}[/bold] — {len(remote_tools)} araç:")
                for tool in remote_tools:
                    console.print(
                        f"  [{theme.ACCENT}]{escape(tool.name)}[/{theme.ACCENT}] — "
                        f"{escape(tool.description or '')}"
                    )

    _run_connected(
        _run,
        timeout_s=timeout_s,
        timeout_message=messages.MCP_TOOLS_TIMEOUT.format(seconds=timeout_s),
    )


def _find_server(config: Config, name: str) -> McpServerConfig:
    server = next((item for item in config.mcp_servers if item.name == name), None)
    if server is None:
        raise FusionError(messages.MCP_NOT_FOUND.format(name=name))
    return server


def _print_status(status: object) -> None:
    state = getattr(status, "state", "")
    message = getattr(status, "message", "") or ""
    tool_count = getattr(status, "tool_count", None)
    detail = f" — {message}" if message else (f" — {tool_count} araç" if tool_count else "")
    console.print(
        escape(
            messages.MCP_LOGIN_RESULT.format(
                name=getattr(status, "server", ""), state=state, detail=detail
            )
        )
    )


@mcp_app.command("login")
def login(
    name: Annotated[str, typer.Argument(help="OAuth ile giriş yapılacak sunucu.")],
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Tarayıcı açma; adresi bas, dönüş adresini yapıştır."
    ),
) -> None:
    """Uzak MCP sunucusuna OAuth ile giriş yap (tarayıcı açılır); token şifreli depoda kalır."""
    server = _find_server(load_config(), name)
    if no_browser:
        from ..mcp_bridge.oauth import FORCE_NO_BROWSER

        FORCE_NO_BROWSER.set(True)
    try:
        from ..mcp_bridge.service import McpConnectionService
    except ImportError:
        console.print(f"[red]{messages.MCP_MISSING_DEP}[/red]")
        raise typer.Exit(code=1) from None

    async def _run() -> None:
        _print_status(await McpConnectionService().test(server))

    _run_connected(
        _run,
        timeout_s=MCP_LOGIN_TIMEOUT_S,
        timeout_message=messages.MCP_LOGIN_TIMEOUT.format(name=name, seconds=MCP_LOGIN_TIMEOUT_S),
    )


@mcp_app.command("reconnect")
def reconnect(
    name: Annotated[str, typer.Argument(help="Sunucu adı ya da `all`.")] = "all",
) -> None:
    """Sunucuya yeniden bağlan: park kaydı silinir, bağlantı yeniden yoklanır."""
    config = load_config()
    targets = tuple(config.mcp_servers) if name == "all" else (_find_server(config, name),)
    if not targets:
        console.print(messages.MCP_NO_SERVERS)
        return
    try:
        from ..mcp_bridge.service import McpConnectionService
    except ImportError:
        console.print(f"[red]{messages.MCP_MISSING_DEP}[/red]")
        raise typer.Exit(code=1) from None

    async def _run() -> None:
        service = McpConnectionService()
        for server in targets:
            _print_status(await service.reconnect(server))

    _run_connected(
        _run,
        timeout_s=MCP_LOGIN_TIMEOUT_S,
        timeout_message=messages.MCP_TOOLS_TIMEOUT.format(seconds=MCP_LOGIN_TIMEOUT_S),
    )
