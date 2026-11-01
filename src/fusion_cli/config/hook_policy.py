"""Kanca ayar politikası: `allowManagedHooksOnly` ve HTTP izin listeleri (#96, #106).

Claude Code: `allowedHttpHookUrls` ve `httpHookAllowedEnvVars` "apply to hooks from every
source" — dosya katmanları, eklentiler ve oturum boyu eklenen beceri kancaları dahil.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from dataclasses import replace

from ..core.hooks.events import HTTP_HANDLER, HookCommand, HookSet, HookSkip

REASON_MANAGED_ONLY = "allowManagedHooksOnly: yalnız yönetilen kancalar çalışır"
REASON_HTTP_URL = "adres allowedHttpHookUrls listesinde değil"


def policy_filter(
    hooks: HookSet, commands: Sequence[HookCommand]
) -> tuple[tuple[HookCommand, ...], tuple[HookSkip, ...]]:
    """Oturum boyu kancalara (beceri frontmatter'ı) ayar dosyalarının politikası.

    Claude: HTTP izin listeleri "apply to hooks from every source"; `allowManagedHooksOnly`
    altında yönetilen olmayan her kanca engellenir.
    """
    kept: list[HookCommand] = []
    skipped: list[HookSkip] = []
    for command in commands:
        reason = REASON_MANAGED_ONLY if hooks.managed_only else None
        reason = reason or http_rejection(command, hooks.http_urls)
        if reason is not None:
            skipped.append(as_skip(command, reason))
            continue
        kept.append(narrow_env(command, hooks.http_env))
    return tuple(kept), tuple(skipped)


def http_rejection(command: HookCommand, allowed: Sequence[str] | None) -> str | None:
    if command.handler != HTTP_HANDLER or allowed is None:
        return None
    if any(fnmatch.fnmatchcase(command.command, pattern) for pattern in allowed):
        return None
    return REASON_HTTP_URL


def narrow_env(command: HookCommand, allowed: Sequence[str] | None) -> HookCommand:
    if command.handler != HTTP_HANDLER or allowed is None:
        return command
    names = tuple(name for name in command.allowed_env_vars if name in allowed)
    return replace(command, allowed_env_vars=names)


def as_skip(command: HookCommand, reason: str) -> HookSkip:
    return HookSkip(
        command.event.value, command.matcher, command.command, reason, command.source, command.path
    )
