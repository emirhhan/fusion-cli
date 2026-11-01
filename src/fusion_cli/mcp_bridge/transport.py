"""MCP taşıma ayrıntılarını istemci yaşam döngüsünden ayır."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, TextIO

import httpx
from mcp import StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from ..config.models import McpServerConfig, McpTransport
from ..core.env_refs import (
    REMOTE_BLANKED_VARIABLES,
    expand_claude_refs,
    has_env_refs,
    referenced_names,
)
from .egress import guarded_client_factory
from .timeouts import MAX_SSE_READ_S, http_request_timeout_s, idle_timeout_s
from .types import McpConfigError

_LOG = logging.getLogger(__name__)

_SECRET_ARGUMENT_PREFIX = "__FUSION_SECRET__:"

#: GUI'den açılan uygulamanın PATH'inde olmayan yaygın kurulum yerleri.
_SYSTEM_TOOL_DIRS = ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin")
_HOME_TOOL_DIRS = (".local/bin", ".cargo/bin", ".bun/bin", ".volta/bin")


def _expand(text: str, source: Mapping[str, str], *, remote: bool = False) -> str:
    """Claude Code `${VAR}` genişletmesi (#243, #244).

    Tanımsız ve varsayılansız başvuru `${VAR}` olarak kalır (uyarı günlüğe yazılır, bağlantı
    yine denenir); boş metne ayarlı değişken tanımlı sayılır. Uzak `url`/`headers` alanlarında
    kimlik bilgisi değişkenleri boş okunur.
    """
    if not has_env_refs(text):
        return text
    expanded, missing = expand_claude_refs(
        text, source, blanked=REMOTE_BLANKED_VARIABLES if remote else frozenset()
    )
    if missing:
        _LOG.warning("MCP yapılandırmasında ortam değişkeni eksik: %s", ", ".join(missing))
    if remote:
        blocked = [name for name in referenced_names(text) if name in REMOTE_BLANKED_VARIABLES]
        if blocked and any(name in source for name in blocked):
            _LOG.debug("never expanded toward a remote server: %s", ", ".join(sorted(set(blocked))))
    return expanded


def resolve_stdio_command(
    config: McpServerConfig, *, environ: Mapping[str, str] | None = None
) -> str:
    """Komut metnindeki `${VAR}` başvurularını çöz (`.mcp.json` `command: ${NPX:-npx}`)."""
    return _expand(config.command, os.environ if environ is None else environ)


def resolve_remote_url(config: McpServerConfig, *, environ: Mapping[str, str] | None = None) -> str:
    """Adresteki `${VAR}` başvurularını çöz; adres config'e çözülmüş hâliyle yazılmaz."""
    return _expand(config.url, os.environ if environ is None else environ, remote=True)


def resolve_static_headers(
    config: McpServerConfig, *, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """`headers` (`--header`) + eski `token_env` Bearer'ı; değerlerdeki `${VAR}` çözülür."""
    source = os.environ if environ is None else environ
    headers = {key: _expand(value, source, remote=True) for key, value in config.headers}
    bearer = resolve_bearer_headers(config, environ=source)
    return {**headers, **(bearer or {})}


def resolve_stdio_args(
    config: McpServerConfig, *, environ: Mapping[str, str] | None = None
) -> list[str]:
    """Şifreli ortam başvurularını ve `${VAR:-varsayılan}` başvurularını yalnız alt-süreç
    başlatılırken çöz (P-049: Claude Code `.mcp.json` sözdizimi)."""
    source = os.environ if environ is None else environ
    allowed = set(config.env_names)
    resolved: list[str] = []
    for argument in config.args:
        if not argument.startswith(_SECRET_ARGUMENT_PREFIX):
            resolved.append(_expand(argument, source))
            continue
        name = argument.removeprefix(_SECRET_ARGUMENT_PREFIX)
        if name not in allowed:
            raise McpConfigError(f"MCP gizli argümanı yapılandırılmamış: {name}")
        value = source.get(name, "")
        if not value:
            raise McpConfigError(f"MCP gizli argümanı bulunamadı: {name}")
        resolved.append(value)
    return resolved


def resolve_stdio_env(
    config: McpServerConfig, *, environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Kayıtlı ortam değişkenlerini alt-sürece verilecek sözlüğe çevir.

    MCP SDK `env` verilmezse yalnız HOME, PATH gibi güvenli değişkenleri aktarır.
    Ölçüldü (SDK 1.29.1, `mcp/client/stdio/__init__.py`): bağlantı ekranında girilen
    API anahtarları şifreli depodan ortama yükleniyor ama sunucu sürecine hiç
    ulaşmıyordu. Yalnız `env_names` içindeki adlar aktarılır; Fusion'ın bütün
    ortamı dış sürece açılmaz.
    """
    source = os.environ if environ is None else environ
    missing_names = [name for name in config.env_names if not source.get(name)]
    if missing_names:
        raise McpConfigError(f"MCP ortam değişkeni bulunamadı: {', '.join(missing_names)}")
    # Sır olmayan değerler (`.mcp.json` `env`) önce; başvuruları bağlantı anında çözülür.
    # Kayıtlı sır adları aynı adı taşıyorsa şifreli depodan gelen değer kazanır.
    literals = {name: _expand(value, source) for name, value in config.env_literals}
    return {**literals, **{name: source[name] for name in config.env_names}}


#: Claude Code: 1 iken stdio sunucusu yalnız güvenli temel ortam + `env` ile başlar (#245).
ALLOWLIST_ENV = "CLAUDE_CODE_MCP_ALLOWLIST_ENV"


def stdio_process_env(
    config: McpServerConfig,
    *,
    environ: Mapping[str, str] | None = None,
    project_dir: Path | None = None,
) -> dict[str, str] | None:
    """Stdio sürecinin ortamı (#245, #273).

    Claude Code varsayılanı: kabuk ortamı miras alınır, sunucunun `env`'i üstüne yazılır ve
    `CLAUDE_PROJECT_DIR` verilir. `CLAUDE_CODE_MCP_ALLOWLIST_ENV=1` iken SDK'nın güvenli
    temel ortamı (HOME, USER, PATH…) + `env` kullanılır.
    """
    source = os.environ if environ is None else environ
    stamped = str(getattr(config, "project_dir", "") or "")
    configured = {
        "PATH": stdio_search_path(source),
        "CLAUDE_PROJECT_DIR": str(project_dir or stamped or Path.cwd()),
        **resolve_stdio_env(config, environ=source),
    }
    if source.get(ALLOWLIST_ENV, "").strip() == "1":
        return configured
    return {**dict(source), **configured}


def resolve_bearer_headers(
    config: McpServerConfig, *, environ: Mapping[str, str] | None = None
) -> dict[str, str] | None:
    """Yapılandırılmış token'ı istek başlığına çevir; token yoksa None.

    Eksik değeri SESSİZCE geçmek kimliksiz bir istek gönderirdi; sunucunun 401'i
    kullanıcıya anlaşılmaz bir "başlatılamadı" hatası olarak dönerdi.
    """
    if not config.token_env:
        return None
    source = os.environ if environ is None else environ
    value = source.get(config.token_env, "").strip()
    if not value:
        raise McpConfigError(
            f"MCP erişim token'ı bulunamadı: {config.token_env}. "
            "Bağlantıyı yeniden ekleyip token'ı gir."
        )
    return {"Authorization": f"Bearer {value}"}


def stdio_search_path(environ: Mapping[str, str] | None = None, *, home: Path | None = None) -> str:
    """Stdio sunucusunun PATH'i: mevcut sıra korunur, eksik kurulum yerleri sona eklenir.

    Ölçüldü: Finder'dan açılan uygulamanın çekirdeği `/usr/bin:/bin:/usr/sbin:/sbin`
    ile başlar; Homebrew'daki `npx`/`uvx` bulunamaz ve kullanıcıya kurulu olan
    programı "kur" denirdi. Sona eklemek, kabuktan gelen PATH'in önceliğini bozmaz.
    """
    source = os.environ if environ is None else environ
    base = home or Path.home()
    parts = [part for part in source.get("PATH", "").split(os.pathsep) if part]
    extra = [*_SYSTEM_TOOL_DIRS, *(str(base / sub) for sub in _HOME_TOOL_DIRS)]
    return os.pathsep.join(dict.fromkeys([*parts, *extra]))


@asynccontextmanager
async def open_mcp_stream(
    config: McpServerConfig,
    *,
    auth: httpx.Auth | None = None,
    errlog: TextIO | None = None,
    extra_headers: Mapping[str, str] | None = None,
    on_status: Callable[[int], None] | None = None,
) -> AsyncIterator[tuple[Any, Any]]:
    """Yapılandırılmış taşımanın okuma/yazma akışlarını aç.

    `errlog` stdio sunucusunun stderr'ini alır. İstemci bunu geçici bir dosyaya
    yönlendirir: paket bulunamadığında SDK yalnız "Connection closed" der, asıl
    neden (npm E404) yalnız sürecin kendi çıktısındadır (bkz. `failures.py`).
    """
    if config.transport is McpTransport.STDIO:
        if not config.command:
            raise McpConfigError("stdio MCP bağlantısı için komut gerekli")
        params = StdioServerParameters(
            command=resolve_stdio_command(config),
            args=resolve_stdio_args(config),
            # SDK güvenli varsayılan ortamı (HOME, USER…) bununla birleştirir.
            env=stdio_process_env(config),
        )
        async with stdio_client(params, errlog=errlog or sys.stderr) as streams:
            yield streams
        return

    if not config.url:
        raise McpConfigError("Uzak MCP bağlantısı için URL gerekli")
    url = resolve_remote_url(config)
    headers = {**resolve_static_headers(config), **(extra_headers or {})} or None
    if config.transport is McpTransport.WS:
        from .ws_transport import ws_streams

        async with ws_streams(url, headers) as streams:
            yield streams
        return
    request_timeout = http_request_timeout_s(config)
    if config.transport is McpTransport.SSE:
        async with sse_client(
            url,
            headers=headers,
            timeout=request_timeout,
            sse_read_timeout=idle_timeout_s(config) or MAX_SSE_READ_S,
            auth=auth,
            httpx_client_factory=guarded_client_factory(url, on_response=on_status),
        ) as (read, write):
            yield read, write
        return
    # OAuth keşfi dahil her istek korumalı istemciden geçer (bkz. `egress.py`).
    async with streamablehttp_client(
        url,
        headers=headers,
        timeout=request_timeout,
        sse_read_timeout=idle_timeout_s(config) or MAX_SSE_READ_S,
        auth=auth,
        httpx_client_factory=guarded_client_factory(url, on_response=on_status),
    ) as streams:
        read, write, _session_id = streams
        yield read, write
