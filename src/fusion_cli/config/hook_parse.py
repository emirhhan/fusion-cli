"""Kanca `hooks` bloğunun şema doğrulaması — Claude Code'un işleyici alanlarıyla aynı.

    ortak       `type` (ZORUNLU: command|http|mcp_tool|prompt|agent), `if`, `timeout`,
                `statusMessage`, `once` (yalnız beceri frontmatter'ında anlamlı)
    command     `command`, `args` (kabuksuz exec biçimi), `async`, `asyncRewake`,
                `shell` (bash|powershell), `onFailure` (continue|block)
    http        `url`, `headers`, `allowedEnvVars`, `onFailure`

Olay × tür tablosu Claude belgesindeki gibidir: SessionStart/Setup yalnız command ve
mcp_tool, gözlem olayları (Notification, PreCompact, SessionEnd, CwdChanged…) prompt/agent
desteklemez. Desteklenmeyen birleşim gerekçesiyle listede görünür, çalıştırılmaz.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from ..core.hooks.events import (
    CLAUDE_ONLY_EVENTS,
    COMMAND_HANDLER,
    HTTP_HANDLER,
    HookCommand,
    HookEvent,
    HookSkip,
    parse_event,
)

#: Süresi yazılmamış command/http kancasının Claude varsayılanı (sn).
DEFAULT_HOOK_TIMEOUT_S = 600.0
#: Geriye uyum: eski adın değeri (artık üst sınır değil, varsayılan).
MAX_HOOK_TIMEOUT_S = DEFAULT_HOOK_TIMEOUT_S

KNOWN_HANDLERS = frozenset({"command", "http", "mcp_tool", "prompt", "agent"})
#: Fusion'ın çalıştırdığı türler; ötekiler (prompt, agent, mcp_tool) henüz atlanır.
RUNNABLE_HANDLERS = frozenset({COMMAND_HANDLER, HTTP_HANDLER})
#: Olay başına izinli türler (Claude "Prompt-based hooks" tablosu).
_ALL = KNOWN_HANDLERS
_NO_MODEL = frozenset({"command", "http", "mcp_tool"})
_START = frozenset({"command", "mcp_tool"})
EVENT_HANDLERS: dict[HookEvent, frozenset[str]] = {
    HookEvent.PRE_TOOL_USE: _ALL,
    HookEvent.POST_TOOL_USE: _ALL,
    HookEvent.POST_TOOL_USE_FAILURE: _ALL,
    HookEvent.USER_PROMPT_SUBMIT: _ALL,
    HookEvent.STOP: _ALL,
    HookEvent.SUBAGENT_STOP: _ALL,
    HookEvent.TASK_CREATED: _ALL,
    HookEvent.TASK_COMPLETED: _ALL,
    HookEvent.TEAMMATE_IDLE: _ALL,
    HookEvent.SESSION_START: _START,
}

REASON_HANDLER = "tür henüz desteklenmiyor: {kind} (Fusion command ve http çalıştırır)"
REASON_UNKNOWN_HANDLER = "bilinmeyen tür: {kind} (command|http|mcp_tool|prompt|agent)"
REASON_NO_TYPE = "'type' alanı zorunlu (command|http|mcp_tool|prompt|agent)"
REASON_EVENT_HANDLER = "{event} olayı {kind} türünü desteklemez"
REASON_URL = "http kancasının 'url' alanı http:// ya da https:// adresi olmalı"
REASON_EVENT = "Fusion bu olayı tetiklemiyor"
REASON_UNKNOWN_EVENT = "bilinmeyen olay"
REASON_EMPTY = "komut boş"
REASON_OPTION = "geçersiz alan: {detail}"
_SHELLS = frozenset({"bash", "powershell"})
_FAILURE_MODES = frozenset({"continue", "block"})


def parse_hooks_block(
    block: object, *, source: str, path: Path, default_timeout_s: float = DEFAULT_HOOK_TIMEOUT_S
) -> tuple[tuple[HookCommand, ...], tuple[HookSkip, ...]]:
    """Kanca şemasını doğrula; bozuk koruyucu girdiyi sessizce kaybetme."""
    if not isinstance(block, Mapping):
        return (), (_invalid_shape("hooks", source, path),)
    commands: list[HookCommand] = []
    skipped: list[HookSkip] = []
    for event_name, groups in block.items():
        name = str(event_name)
        if not isinstance(groups, list):
            skipped.append(_invalid_shape(name, source, path))
            continue
        for group in groups:
            found, rejected = _parse_group(name, group, source, path, default_timeout_s)
            commands.extend(found)
            skipped.extend(rejected)
    return tuple(commands), tuple(skipped)


def _invalid_shape(event: str, source: str, path: Path) -> HookSkip:
    known = parse_event(event) is not None or event in CLAUDE_ONLY_EVENTS
    return rejected_hook(
        event if known else "bilinmeyen",
        "",
        {},
        "kanca şeması geçersiz; olay grupları ve hooks alanı liste, girdiler nesne olmalı",
        source,
        path,
    )


def _parse_group(
    name: str, group: object, source: str, path: Path, default_timeout_s: float
) -> tuple[tuple[HookCommand, ...], tuple[HookSkip, ...]]:
    if not isinstance(group, Mapping):
        return (), (_invalid_shape(name, source, path),)
    matcher = group.get("matcher", "")
    handlers = group.get("hooks")
    if not isinstance(matcher, str) or not isinstance(handlers, list):
        return (), (_invalid_shape(name, source, path),)
    commands: list[HookCommand] = []
    skipped: list[HookSkip] = []
    event = parse_event(name)
    for handler in handlers:
        if not isinstance(handler, Mapping):
            skipped.append(_invalid_shape(name, source, path))
            continue
        reason = _skip_reason(name, event, handler) or _option_error(handler)
        if reason is not None or event is None:
            skipped.append(rejected_hook(name, matcher, handler, reason or "", source, path))
            continue
        commands.append(_command(event, matcher, handler, source, path, default_timeout_s))
    return tuple(commands), tuple(skipped)


def _command(
    event: HookEvent,
    matcher: str,
    handler: Mapping[str, object],
    source: str,
    path: Path,
    default_timeout_s: float,
) -> HookCommand:
    kind = str(handler.get("type"))
    target = handler.get("url" if kind == HTTP_HANDLER else "command")
    raw_args = handler.get("args")
    headers, env_names = http_options(handler)
    timeout, explicit = _timeout(handler.get("timeout"), default_timeout_s)
    return HookCommand(
        event,
        matcher,
        str(target),
        timeout,
        source,
        str(path),
        kind,
        headers,
        env_names,
        args=tuple(str(item) for item in raw_args) if isinstance(raw_args, list) else None,
        once=handler.get("once") is True,
        run_async=handler.get("async") is True,
        async_rewake=handler.get("asyncRewake") is True,
        shell=str(handler.get("shell") or ""),
        on_failure=str(handler.get("onFailure") or ""),
        status_message=str(handler.get("statusMessage") or ""),
        condition=str(handler.get("if") or "").strip(),
        timeout_explicit=explicit,
    )


def rejected_hook(
    event: str, matcher: str, handler: Mapping[str, object], reason: str, source: str, path: Path
) -> HookSkip:
    """Ham komut/başlık/argüman yalnız görünmez metaveride tutulur."""
    return HookSkip(
        event,
        matcher,
        "kanca tanımı uygulanmadı",
        reason[:160],
        source,
        str(path),
        definition_json=json.dumps(dict(handler), ensure_ascii=False, sort_keys=True, default=str),
    )


def _skip_reason(
    event_name: str, event: HookEvent | None, handler: Mapping[str, object]
) -> str | None:
    if event is None:
        return REASON_EVENT if event_name in CLAUDE_ONLY_EVENTS else REASON_UNKNOWN_EVENT
    raw_kind = handler.get("type")
    if not isinstance(raw_kind, str) or not raw_kind:
        return REASON_NO_TYPE
    if raw_kind not in KNOWN_HANDLERS:
        return REASON_UNKNOWN_HANDLER.format(kind=raw_kind)
    if raw_kind not in EVENT_HANDLERS.get(event, _NO_MODEL):
        return REASON_EVENT_HANDLER.format(event=event.value, kind=raw_kind)
    if raw_kind not in RUNNABLE_HANDLERS:
        return REASON_HANDLER.format(kind=raw_kind)
    target = handler.get("url" if raw_kind == HTTP_HANDLER else "command")
    if not isinstance(target, str) or not target.strip():
        return REASON_URL if raw_kind == HTTP_HANDLER else REASON_EMPTY
    if raw_kind == HTTP_HANDLER and not target.strip().lower().startswith(("http://", "https://")):
        return REASON_URL
    return None


def _option_error(handler: Mapping[str, object]) -> str | None:
    """Bozuk yazılmış kontrol alanı kancayı çalıştırmaz (sessiz yanlış çalışma yerine)."""
    args = handler.get("args")
    if args is not None and not (isinstance(args, list) and all(isinstance(a, str) for a in args)):
        return REASON_OPTION.format(detail="args metin listesi olmalı")
    shell = handler.get("shell")
    if shell is not None and shell not in _SHELLS:
        return REASON_OPTION.format(detail="shell bash ya da powershell olmalı")
    failure = handler.get("onFailure")
    if failure is not None and failure not in _FAILURE_MODES:
        return REASON_OPTION.format(detail="onFailure continue ya da block olmalı")
    condition = handler.get("if")
    if condition is not None and not isinstance(condition, str):
        return REASON_OPTION.format(detail="if izin kuralı metni olmalı")
    return None


def http_options(
    handler: Mapping[str, object],
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    """`headers` (ad → metin) ve `allowedEnvVars` (ad listesi); bozuk girdiler atlanır."""
    raw_headers = handler.get("headers")
    headers = tuple(
        (str(name), value)
        for name, value in (raw_headers.items() if isinstance(raw_headers, Mapping) else ())
        if isinstance(value, str)
    )
    raw_env = handler.get("allowedEnvVars")
    names = (
        tuple(name for name in raw_env if isinstance(name, str))
        if isinstance(raw_env, list)
        else ()
    )
    return headers, names


def _timeout(raw: object, default: float) -> tuple[float, bool]:
    """(süre, yazılı mı). Claude belgesi üst sınır koymaz."""
    if isinstance(raw, bool) or not isinstance(raw, int | float) or raw <= 0:
        return default, False
    return float(raw), True
