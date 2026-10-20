"""MCP taşıma ayrıntılarını istemci yaşam döngüsünden ayır."""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any, TextIO

import httpx
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from ..config.models import McpServerConfig, McpTransport

_SECRET_ARGUMENT_PREFIX = "__FUSION_SECRET__:"


def resolve_stdio_args(
    config: McpServerConfig, *, environ: Mapping[str, str] | None = None
) -> list[str]:
    """Şifreli ortam başvurularını yalnız alt-süreç başlatılırken çöz."""
    source = os.environ if environ is None else environ
    allowed = set(config.env_names)
    resolved: list[str] = []
    for argument in config.args:
        if not argument.startswith(_SECRET_ARGUMENT_PREFIX):
            resolved.append(argument)
            continue
        name = argument.removeprefix(_SECRET_ARGUMENT_PREFIX)
        if name not in allowed:
            raise ValueError(f"MCP gizli argümanı yapılandırılmamış: {name}")
        value = source.get(name, "")
        if not value:
            raise ValueError(f"MCP gizli argümanı bulunamadı: {name}")
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
        raise ValueError(f"MCP ortam değişkeni bulunamadı: {', '.join(missing_names)}")
    return {name: source[name] for name in config.env_names}


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
        raise ValueError(
            f"MCP erişim token'ı bulunamadı: {config.token_env}. "
            "Bağlantıyı yeniden ekleyip token'ı gir."
        )
    return {"Authorization": f"Bearer {value}"}


@asynccontextmanager
async def open_mcp_stream(
    config: McpServerConfig,
    *,
    auth: httpx.Auth | None = None,
    errlog: TextIO | None = None,
) -> AsyncIterator[tuple[Any, Any]]:
    """Yapılandırılmış taşımanın okuma/yazma akışlarını aç.

    `errlog` stdio sunucusunun stderr'ini alır. İstemci bunu geçici bir dosyaya
    yönlendirir: paket bulunamadığında SDK yalnız "Connection closed" der, asıl
    neden (npm E404) yalnız sürecin kendi çıktısındadır (bkz. `failures.py`).
    """
    if config.transport is McpTransport.STDIO:
        if not config.command:
            raise ValueError("stdio MCP bağlantısı için komut gerekli")
        params = StdioServerParameters(
            command=config.command,
            args=resolve_stdio_args(config),
            # Boş sözlük yerine None: SDK varsayılan ortamı kendisi kurar.
            env=resolve_stdio_env(config) or None,
        )
        async with stdio_client(params, errlog=errlog or sys.stderr) as streams:
            yield streams
        return

    if not config.url:
        raise ValueError("HTTP MCP bağlantısı için URL gerekli")
    headers = resolve_bearer_headers(config)
    async with streamablehttp_client(config.url, headers=headers, auth=auth) as streams:
        read, write, _session_id = streams
        yield read, write
