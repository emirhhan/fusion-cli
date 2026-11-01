"""`fusion mcp add` Claude Code sözdizimi yardımcıları (#235, #237, #248, #265, #269).

    fusion mcp add [--transport stdio|http|sse] [--scope local|project|user]
                   [-e KEY=value …] [-H "Ad: değer" …]
                   [--client-id ID] [--client-secret] [--callback-port N]
                   <ad> <komut ya da url> [argüman …]

http/sse taşımasında ikinci konumsal argüman URL'dir (Claude Code). Eski `--url`,
`--token-env` ve `-e AD` (eşittirsiz) bir sürüm boyunca uyarıyla okunur.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

import typer

from ..config.mcp_entry import valid_server_name
from ..config.models import McpServerConfig, McpTransport
from ..ui import mcp_messages

CLIENT_SECRET_ENV = "MCP_CLIENT_SECRET"


def check_name(name: str) -> str:
    """Claude Code ad kuralı: yalnız harf, rakam, - ve _ (#269)."""
    text = name.strip()
    if not valid_server_name(text):
        raise typer.BadParameter(mcp_messages.INVALID_NAME.format(name=name))
    return text


def parse_headers(raw: Iterable[str] | None) -> tuple[tuple[str, str], ...]:
    """`-H "Ad: değer"` → `(ad, değer)`; değer `${VAR}` taşıyabilir (bağlantıda çözülür)."""
    headers: list[tuple[str, str]] = []
    for item in raw or ():
        key, sep, value = item.partition(":")
        if not sep or not key.strip():
            raise typer.BadParameter(mcp_messages.BAD_HEADER.format(raw=item))
        headers.append((key.strip(), value.strip()))
    return tuple(headers)


def split_env(raw: Iterable[str] | None) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    """`-e KEY=value` → düz değer. Eski `-e AD` → şifreli depo adı (uyarıyla)."""
    names: list[str] = []
    literals: list[tuple[str, str]] = []
    for item in raw or ():
        text = item.strip()
        if not text:
            continue
        if "=" in text:
            key, value = text.split("=", 1)
            literals.append((key.strip(), value))
            continue
        typer.echo(mcp_messages.DEPRECATED_ENV_NAME.format(name=text), err=True)
        names.append(text)
    return tuple(names), tuple(literals)


def remote_target(
    kind: McpTransport, command: str, args: tuple[str, ...], url: str, name: str
) -> tuple[str, tuple[str, ...]]:
    """Uzak taşımada (url, kalan argümanlar): konumsal URL birincil, `--url` eski takma ad."""
    if url.strip():
        typer.echo(
            mcp_messages.DEPRECATED_URL.format(
                hint=f"fusion mcp add --transport {kind_label(kind)} {name} {url.strip()}"
            ),
            err=True,
        )
        return url.strip(), ()
    return command.strip(), args


def kind_label(kind: McpTransport) -> str:
    return "http" if kind is McpTransport.STREAMABLE_HTTP else kind.value


def read_client_secret(enabled: bool) -> str:
    """`--client-secret`: önce `MCP_CLIENT_SECRET`, yoksa maskeli istem (Claude Code)."""
    if not enabled:
        return ""
    from_env = os.environ.get(CLIENT_SECRET_ENV, "").strip()
    if from_env:
        return from_env
    return str(typer.prompt(mcp_messages.CLIENT_SECRET_PROMPT, hide_input=True)).strip()


async def store_client_secret(server: McpServerConfig, secret: str) -> None:
    """İstemci sırrını sunucu adresine bağlı anahtarlık kaydına yaz."""
    from ..mcp_bridge.tokens import KeyringTokenStorage

    await KeyringTokenStorage(server.url).set_client_secret(secret)


def check_oauth_flags(
    kind: McpTransport, client_id: str, client_secret: bool, callback_port: int | None
) -> None:
    if kind in (McpTransport.STREAMABLE_HTTP, McpTransport.SSE):
        return
    if client_id.strip() or client_secret or callback_port is not None:
        raise typer.BadParameter(mcp_messages.OAUTH_FLAGS_REMOTE_ONLY)
