"""Kanca listesinin metin görünümü (P-009): `fusion hooks list` ve REPL `/hooks` ortak."""

from __future__ import annotations

from ..config.hooks import hook_rows, user_hooks_file
from ..core.hooks.events import HookSet
from ..ui import messages

#: Komut sütununda gösterilen en fazla karakter.
_COMMAND_CHARS = 80


def hook_list_lines(hooks: HookSet) -> list[str]:
    """Başlık + satırlar + kapalılık/güven uyarısı; tanım yoksa nasıl ekleneceği."""
    rows = hook_rows(hooks)
    lines: list[str] = []
    if hooks.disabled_reason is not None:
        lines.append(messages.HOOKS_LIST_DISABLED.format(reason=hooks.disabled_reason))
    ignored = _ignored_disable_line(hooks)
    if ignored is not None:
        lines.append(ignored)
    if not rows:
        lines.append(messages.HOOKS_LIST_EMPTY.format(path=user_hooks_file()))
        return lines
    lines.append(
        messages.HOOKS_LIST_HEADER.format(active=len(hooks.commands), skipped=len(hooks.skipped))
    )
    for row in rows:
        matcher = f" [{row.matcher}]" if row.matcher else ""
        command = row.command if len(row.command) <= _COMMAND_CHARS else row.command[:77] + "…"
        state = f" — atlandı: {row.skipped}" if row.skipped else ""
        timeout = f" · {row.timeout_s:g} sn" if row.timeout_s is not None else ""
        lines.append(f"· {row.event}{matcher}  {command}  ({row.source}{timeout}){state}")
    if hooks.untrusted_layers:
        lines.append(messages.HOOKS_LIST_UNTRUSTED.format(layers=", ".join(hooks.untrusted_layers)))
    return lines


def _ignored_disable_line(hooks: HookSet) -> str | None:
    if not hooks.ignored_disable_layers:
        return None
    return messages.HOOKS_LIST_IGNORED_DISABLE.format(
        layers=", ".join(hooks.ignored_disable_layers)
    )
