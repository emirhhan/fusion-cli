"""Başka araçların MCP sunucu tanımlarını Fusion kaydına çevirme (P-071).

Claude Code (`~/.claude.json`), Cursor (`mcp.json`) ve Gemini CLI (`settings.json`) aynı
JSON ailesini kullanır: `command/args/env` ya da `url` (+ `headers`). Codex TOML tutar:
`command/args/env/env_vars` ya da `url` + `bearer_token_env_var`. Hepsi buradan geçer ki
sır kuralı TEK yerde uygulansın:

- `${VAR}` / `$VAR` başvurusu olduğu gibi kalır (bağlantı anında çözülür).
- Adı ya da değeri sır gibi görünen ortam değeri `config.yaml`'a YAZILMAZ; şifreli depoya
  gider ve kayıtta yalnız adı (`env_names`) durur.
- `Authorization: Bearer …` başlığı `token_env`'e iner; başka başlık desteklenmez (Fusion
  başlık sözlüğü tutmaz), sunucu gerekçesiyle atlanır.
- Eski `sse` taşıması desteklenmez; atlanır.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from ...core.redaction import contains_sensitive
from ..models import McpScope, McpServerConfig, McpTransport, McpTrust

#: Sır sayılan ortam adı parçaları.
_SECRET_NAME = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|PASSWD|AUTH|CREDENTIAL|COOKIE|SESSION", re.I)
#: Tek başına bir ortam başvurusu: `${VAR}`, `${VAR:-x}`, `$VAR`.
_REFERENCE = re.compile(r"^\$(?:\{[A-Za-z_][A-Za-z0-9_]*(?::-[^}]*)?\}|[A-Za-z_][A-Za-z0-9_]*)$")
_BARE_REFERENCE = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_]*)$")
_BRACED_NAME = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
#: Masaüstü bağlayıcısının token adı öneki (`appserver/connectors.token_env_name` ile aynı).
TOKEN_ENV_PREFIX = "FUSION_MCP_TOKEN_"
#: Fusion sunucu adı: araç adının parçası olur (`<sunucu>__<araç>`).
_NAME_CLEAN = re.compile(r"[^A-Za-z0-9_-]+")

REASON_SSE = "sse taşıması desteklenmiyor (sunucunun http adresini kullan)"
REASON_HEADERS = "Authorization dışındaki başlıklar desteklenmiyor: {names}"
REASON_NO_TARGET = "komut ya da adres yok"
REASON_DISABLED = "kaynakta kapalı"
REASON_BAD_URL = "adres reddedildi: {error}"


@dataclass(frozen=True, slots=True)
class MappedServer:
    """Çeviri sonucu: kayıt ve sırlar ya da atlanma nedeni."""

    server: McpServerConfig | None
    secrets: tuple[tuple[str, str], ...] = ()
    reason: str = ""


def server_name(raw: str) -> str:
    """Fusion'ın kabul ettiği sunucu adı (boşluk/nokta → `-`)."""
    return _NAME_CLEAN.sub("-", raw.strip()).strip("-") or "mcp"


def token_env_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return f"{TOKEN_ENV_PREFIX}{slug}"


def is_secret(key: str, value: str) -> bool:
    return bool(_SECRET_NAME.search(key)) or contains_sensitive(value)


def split_env(
    env: Mapping[str, object],
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """`(sır olmayan değerler, sırlar)`; başvurular sır olmayan tarafta `${VAR}` olarak kalır."""
    literals: list[tuple[str, str]] = []
    secrets: list[tuple[str, str]] = []
    for key, raw in env.items():
        value = str(raw) if isinstance(raw, str | int | float) else ""
        name = str(key).strip()
        if not name:
            continue
        if _REFERENCE.match(value.strip()):
            bare = _BARE_REFERENCE.match(value.strip())
            literals.append((name, f"${{{bare.group(1)}}}" if bare else value.strip()))
        elif is_secret(name, value):
            secrets.append((name, value))
        else:
            literals.append((name, value))
    return tuple(literals), tuple(secrets)


def _bearer(name: str, headers: Mapping[str, object]) -> tuple[str, tuple[tuple[str, str], ...]]:
    """`Authorization: Bearer x` → (token_env, sırlar). Başvuruysa sır kaydı gerekmez."""
    value = next(
        (str(v) for k, v in headers.items() if str(k).lower() == "authorization"), ""
    ).strip()
    if not value.lower().startswith("bearer "):
        return "", ()
    token = value[7:].strip()
    reference = _BRACED_NAME.match(token) or _BARE_REFERENCE.match(token)
    if reference:
        return reference.group(1), ()
    env_name = token_env_name(name)
    return env_name, ((env_name, token),)


def map_json_server(
    name: str, entry: Mapping[str, object], *, url_is_sse: bool = False
) -> MappedServer:
    """Claude/Cursor/Gemini JSON tanımı → Fusion kaydı.

    `url_is_sse`: Gemini CLI'de `url` SSE, `httpUrl` akışlı HTTP demektir.
    """
    if entry.get("disabled") is True or entry.get("enabled") is False:
        return MappedServer(None, reason=REASON_DISABLED)
    kind = str(entry.get("type") or entry.get("transport") or "").strip().lower()
    url = str(entry.get("httpUrl") or entry.get("url") or "").strip()
    if kind == "sse" or (url_is_sse and entry.get("url") and not entry.get("httpUrl")):
        return MappedServer(None, reason=REASON_SSE)
    headers = entry.get("headers")
    header_map: Mapping[str, object] = headers if isinstance(headers, Mapping) else {}
    extra = sorted(str(k) for k in header_map if str(k).lower() != "authorization")
    if extra:
        return MappedServer(None, reason=REASON_HEADERS.format(names=", ".join(extra)))
    env = entry.get("env")
    literals, secrets = split_env(env if isinstance(env, Mapping) else {})
    allowed = entry.get("includeTools")
    allowed_tools = tuple(str(t) for t in allowed) if isinstance(allowed, list) else ()
    command = str(entry.get("command") or "").strip()
    if url and not command:
        token_env, token_secrets = _bearer(name, header_map)
        return _remote(name, url, token_env, (*secrets, *token_secrets), allowed_tools)
    if not command:
        return MappedServer(None, reason=REASON_NO_TARGET)
    args = entry.get("args")
    return _local(
        name,
        command,
        tuple(str(a) for a in args) if isinstance(args, list) else (),
        literals,
        secrets,
        allowed_tools,
    )


def map_codex_server(name: str, table: Mapping[str, object]) -> MappedServer:
    """Codex `[mcp_servers.<ad>]` tablosu → Fusion kaydı."""
    if table.get("enabled") is False:
        return MappedServer(None, reason=REASON_DISABLED)
    env = table.get("env")
    literals, secrets = split_env(env if isinstance(env, Mapping) else {})
    forwarded = table.get("env_vars")
    if isinstance(forwarded, list):
        # Codex bu adları kendi ortamından aktarır; Fusion'da aynı ad `${AD}` başvurusudur.
        literals = (*literals, *((str(v), f"${{{v}}}") for v in forwarded if str(v).strip()))
    enabled_tools = table.get("enabled_tools")
    allowed_tools = tuple(str(t) for t in enabled_tools) if isinstance(enabled_tools, list) else ()
    url = str(table.get("url") or "").strip()
    command = str(table.get("command") or "").strip()
    if url and not command:
        headers = table.get("http_headers")
        if isinstance(headers, Mapping) and headers:
            return MappedServer(None, reason=REASON_HEADERS.format(names=", ".join(headers)))
        token_env = str(table.get("bearer_token_env_var") or "").strip()
        return _remote(name, url, token_env, secrets, allowed_tools)
    if not command:
        return MappedServer(None, reason=REASON_NO_TARGET)
    args = table.get("args")
    return _local(
        name,
        command,
        tuple(str(a) for a in args) if isinstance(args, list) else (),
        literals,
        secrets,
        allowed_tools,
    )


def _remote(
    name: str,
    url: str,
    token_env: str,
    secrets: tuple[tuple[str, str], ...],
    allowed_tools: tuple[str, ...],
) -> MappedServer:
    server = McpServerConfig(
        name=name,
        transport=McpTransport.STREAMABLE_HTTP,
        url=url,
        token_env=token_env,
        env_names=tuple(key for key, _ in secrets if key != token_env),
        trust=McpTrust.UNREVIEWED,
        allowed_tools=allowed_tools,
        scope=McpScope.USER,
    )
    return MappedServer(server, secrets)


def _local(
    name: str,
    command: str,
    args: tuple[str, ...],
    literals: tuple[tuple[str, str], ...],
    secrets: tuple[tuple[str, str], ...],
    allowed_tools: tuple[str, ...],
) -> MappedServer:
    server = McpServerConfig(
        name=name,
        command=command,
        args=args,
        env_names=tuple(key for key, _ in secrets),
        env_literals=literals,
        trust=McpTrust.UNREVIEWED,
        allowed_tools=allowed_tools,
        scope=McpScope.USER,
    )
    return MappedServer(server, secrets)


def describe_server(server: McpServerConfig, secrets: tuple[tuple[str, str], ...]) -> str:
    """Önizleme satırı ayrıntısı; sır DEĞERİ içermez."""
    if server.transport is McpTransport.STREAMABLE_HTTP:
        target = f"http {server.url}"
    else:
        target = " ".join((server.command, *server.args))
    notes = [target]
    if secrets:
        notes.append("sır (şifreli depoya): " + ", ".join(name for name, _ in secrets))
    elif server.token_env:
        notes.append(f"token ortamdan: {server.token_env}")
    if server.allowed_tools:
        notes.append("araçlar: " + ", ".join(server.allowed_tools))
    return " · ".join(notes)
