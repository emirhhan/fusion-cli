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
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

from ..config.loader import load_config
from ..config.mcp_json import (
    PROJECT_MCP_FILE,
    parse_project_mcp,
    project_mcp_path,
    remove_project_mcp_server,
    upsert_project_mcp_server,
)
from ..config.models import Config, McpScope, McpServerConfig, McpTransport
from ..config.writer import write_mcp_servers
from ..core.errors import ConfigError, FusionError
from ..core.redaction import redact
from ..ui import messages, theme
from . import mcp_reference_commands

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
}

mcp_app = typer.Typer(
    help="Dış MCP sunucularını yönet; alt komutsuz çağrıda Fusion'ı MCP sunucusu olarak aç.",
    invoke_without_command=True,
)


@mcp_app.callback()
def mcp(
    ctx: typer.Context,
    write: bool = typer.Option(
        False, "--write", help="Değiştirici araçları da aç (dikkat: dışarıya yazma verir)."
    ),
) -> None:
    """Fusion araçlarını bir MCP sunucusu olarak aç (stdio).

    MCP destekleyen araçlar (Claude masaüstü, Cursor, Cline…) buna bağlanıp Fusion'ın
    araçlarını (kod arama, dosya okuma…) kullanabilir. Varsayılan yalnızca salt-okunur.
    Alt komutlarla (`add`, `list`, `login`…) dış MCP sunucuları yönetilir.
    """
    if ctx.invoked_subcommand is not None:
        return
    # DİKKAT: stdout MCP protokolüne aittir; buraya hiçbir şey BASILMAZ.
    try:
        from ..mcp_bridge.server import run_stdio
    except ImportError:
        typer.echo(messages.MCP_MISSING_DEP, err=True)
        raise typer.Exit(code=1) from None
    asyncio.run(run_stdio(Path.cwd(), expose_mutating=write))


# --------------------------------------------------------------------------- #
# add / add-json / remove / list
# --------------------------------------------------------------------------- #


def _parse_scope(raw: str) -> McpScope:
    try:
        return McpScope(raw.strip().lower())
    except ValueError:
        valid = ", ".join(item.value for item in McpScope)
        raise typer.BadParameter(f"Bilinmeyen kapsam: {raw}. Geçerli olanlar: {valid}") from None


def _parse_transport(raw: str) -> McpTransport:
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
    others = tuple(item for item in config.mcp_servers if item.scope is not server.scope)
    kept = tuple(item for item in same_scope if item.name != server.name)
    return write_mcp_servers(replace(config, mcp_servers=(*others, *kept, server))), replaced


def _save_or_exit(config: Config, server: McpServerConfig) -> tuple[Path, bool]:
    """`save_server`; yazma reddi (güvenilmeyen/bozuk `.mcp.json`) Türkçe hata ve çıkış 1."""
    try:
        return save_server(config, server, root=Path.cwd())
    except ConfigError as error:
        console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
        raise typer.Exit(code=1) from None


def _announce_saved(server: McpServerConfig, path: Path, replaced: bool) -> None:
    if server.scope is McpScope.PROJECT:
        console.print(messages.MCP_PROJECT_ADDED.format(name=server.name, path=path))
        return
    template = messages.MCP_REPLACED if replaced else messages.MCP_ADDED
    console.print(template.format(name=server.name))
    console.print(f"[{theme.DIM}]{path}[/{theme.DIM}]")


@mcp_app.command("add")
def add(
    name: Annotated[str, typer.Argument(help="Sunucuya vereceğin kısa ad (ör. github).")],
    command: Annotated[
        str, typer.Argument(help="stdio için çalıştırılacak komut (ör. npx); http'de boş.")
    ] = "",
    args: Annotated[
        list[str] | None,
        typer.Argument(help="Komuta verilecek argümanlar. `-` ile başlıyorsa önce -- koy."),
    ] = None,
    transport: str = typer.Option("stdio", "--transport", "-t", help="stdio | http"),
    url: str = typer.Option("", "--url", help="http taşımasında sunucu adresi."),
    scope: str = typer.Option(
        "user", "--scope", "-s", help="user (config.yaml) | project (.mcp.json)"
    ),
    env: Annotated[
        list[str] | None,
        typer.Option(
            "--env",
            "-e",
            help="Sunucuya aktarılacak ortam değişkeni ADI (sır değeri config'e yazılmaz) "
            "ya da AD=değer (sır olmayan değer; ${VAR:-vars} başvurusu olabilir).",
        ),
    ] = None,
    token_env: str = typer.Option(
        "", "--token-env", help="http için Bearer token'ın ortam değişkeni adı (OAuth yerine)."
    ),
) -> None:
    """Dış bir MCP sunucusunu ekle; kullanıcı config'i elle düzenlemez.

    Örnekler:
      fusion mcp add github npx -- -y @modelcontextprotocol/server-github
      fusion mcp add linear --transport http --url https://mcp.linear.app/mcp
      fusion mcp add postgres --scope project npx -- -y server-postgres -e DATABASE_URL

    Argümanlar `-` ile başlıyorsa Typer'ın seçenek sanmaması için `--` şart. Agent bu
    komutu KENDİ dosya araçlarıyla DEĞİL, yalnızca shell'de çalıştırarak tetikler.
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
    )


def add_server(
    name: str,
    command: str,
    args: tuple[str, ...],
    *,
    transport: str = "stdio",
    url: str = "",
    scope: str = "user",
    env: tuple[str, ...] = (),
    token_env: str = "",
) -> McpServerConfig:
    """`add` gövdesi; eski `fusion mcp-add` takma adı da bunu çağırır."""
    kind = _parse_transport(transport)
    target_scope = _parse_scope(scope)
    env_names, env_literals = split_env_options(env)
    if kind is McpTransport.STDIO and not command.strip():
        raise typer.BadParameter(messages.MCP_ADD_NEEDS_COMMAND)
    if kind is McpTransport.STREAMABLE_HTTP and not url.strip():
        raise typer.BadParameter(messages.MCP_ADD_NEEDS_URL)
    if target_scope is McpScope.PROJECT and token_env.strip():
        # `.mcp.json` Claude Code biçimi `token_env` taşımaz; sessizce atmak kimliksiz istek
        # üretirdi (31 Ekim). Kullanıcı kapsamına yazılsın ya da `env` ile başvuru verilsin.
        raise typer.BadParameter(messages.MCP_PROJECT_NO_TOKEN_ENV)
    if kind is McpTransport.STREAMABLE_HTTP:
        from ..mcp_bridge.oauth import validate_remote_mcp_url

        validate_remote_mcp_url(url.strip())
    server = McpServerConfig(
        name=name.strip(),
        command=command.strip() if kind is McpTransport.STDIO else "",
        args=args if kind is McpTransport.STDIO else (),
        transport=kind,
        url=url.strip() if kind is McpTransport.STREAMABLE_HTTP else "",
        env_names=env_names,
        token_env=token_env.strip(),
        scope=target_scope,
        env_literals=env_literals,
    )
    path, replaced = _save_or_exit(load_config(), server)
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
    scope: str = typer.Option("user", "--scope", "-s", help="user | project"),
) -> None:
    """Claude Code `claude mcp add-json` biçimindeki tanımla sunucu ekle."""
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
    path, replaced = _save_or_exit(load_config(), server)
    _announce_saved(server, path, replaced)


@mcp_app.command("remove")
def remove(name: Annotated[str, typer.Argument(help="Kaldırılacak sunucunun adı.")]) -> None:
    """Sunucuyu kayıtlı olduğu kapsamdan (config.yaml ya da .mcp.json) kaldır."""
    config = load_config()
    target = next((item for item in config.mcp_servers if item.name == name), None)
    if target is None:
        console.print(f"[{theme.ERROR}]{messages.MCP_NOT_FOUND.format(name=name)}[/{theme.ERROR}]")
        raise typer.Exit(code=1)
    if target.scope is McpScope.PLUGIN:
        # Eklenti sunucusu hiçbir ayar dosyasında durmaz; eklentiyle birlikte kapanır (P-059).
        console.print(
            f"[{theme.ERROR}]{messages.EKLENTI_MCP_REMOVE.format(name=name)}[/{theme.ERROR}]"
        )
        raise typer.Exit(code=1)
    if target.scope is McpScope.PROJECT:
        try:
            remove_project_mcp_server(Path.cwd(), name)
        except ConfigError as error:
            console.print(f"[{theme.ERROR}]{escape(str(error))}[/{theme.ERROR}]")
            raise typer.Exit(code=1) from None
        console.print(messages.MCP_PROJECT_REMOVED.format(name=name))
        return
    kept = tuple(item for item in config.mcp_servers if item.name != name)
    write_mcp_servers(replace(config, mcp_servers=kept))
    console.print(messages.MCP_REMOVED.format(name=name))


@mcp_app.command("list")
def list_servers() -> None:
    """Kayıtlı dış MCP sunucularını kapsam ve taşımayla listele (sırlar maskeli)."""
    config = load_config()
    if not config.mcp_servers:
        console.print(messages.MCP_NO_SERVERS)
        return
    for server in config.mcp_servers:
        target = server.url if server.url else " ".join((server.command, *server.args)).strip()
        console.print(
            escape(
                redact(
                    messages.MCP_LIST_ROW.format(
                        name=server.name,
                        scope=messages.MCP_SCOPE_LABELS.get(server.scope.value, server.scope.value),
                        transport=server.transport.value,
                        target=target,
                    )
                )
            )
        )
    project_path = project_mcp_path(Path.cwd())
    if project_path.is_file():
        console.print(
            f"[{theme.DIM}]{messages.MCP_LIST_HEADER_PROJECT_HINT.format(path=PROJECT_MCP_FILE)}"
            f"[/{theme.DIM}]"
        )


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
mcp_app.command("prompts")(mcp_reference_commands.prompts)
mcp_app.command("resources")(mcp_reference_commands.resources)


@mcp_app.command("tools")
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
def login(name: Annotated[str, typer.Argument(help="OAuth ile giriş yapılacak sunucu.")]) -> None:
    """Uzak MCP sunucusuna OAuth ile giriş yap (tarayıcı açılır); token şifreli depoda kalır."""
    server = _find_server(load_config(), name)
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
