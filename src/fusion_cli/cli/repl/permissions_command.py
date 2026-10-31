"""`/permissions` — izin kurallarını listele/ekle/sil (P-003; Claude Code `/permissions`).

    /permissions                       tüm katmanlardaki kurallar (kalıp · karar · kaynak)
    /permissions add allow Bash(npm test *) [--user]
    /permissions remove deny Edit(/src/**)

Yazma işi `config.permission_admin` üzerinden gider; masaüstü `izin.*` RPC'leri ve
`fusion permissions` aynı işlevleri kullanır.
"""

from __future__ import annotations

import shlex

from ...config import permission_admin
from ...core.errors import ConfigError
from ...ui import messages
from .state import ReplState

_ADD = frozenset({"add", "ekle"})
_REMOVE = frozenset({"remove", "rm", "sil", "del"})
_LIST = frozenset({"", "list", "liste"})


def permissions(state: ReplState, argument: str) -> str:
    """Slash komut işleyicisi; tek satırlık Türkçe sonuç döndürür."""
    try:
        words = shlex.split(argument)
    except ValueError:
        words = argument.split()
    action = words[0].lower() if words else ""
    if action in _LIST:
        return _render_list(state)
    if action not in _ADD | _REMOVE:
        return messages.PERMISSIONS_USAGE
    user_level = "--user" in words
    rest = [word for word in words[1:] if word != "--user"]
    if len(rest) < 2:
        return messages.PERMISSIONS_USAGE
    try:
        decision = permission_admin.parse_decision(rest[0])
    except ValueError:
        return messages.PERMISSIONS_BAD_DECISION.format(given=rest[0])
    pattern_text = " ".join(rest[1:])
    try:
        rule = permission_admin.parse_pattern(pattern_text, decision)
    except ValueError:
        return messages.PERMISSIONS_BAD_PATTERN.format(given=pattern_text)
    try:
        if action in _ADD:
            change = permission_admin.add_permission_rule(state.root, rule, user_level=user_level)
            if not change.changed:
                return messages.PERMISSIONS_EXISTS.format(
                    rule=change.pattern, decision=decision.value
                )
            return permission_admin.added_message(change, decision)
        removed = permission_admin.remove_permission_rule(state.root, rule)
    except ConfigError as error:
        return str(error)
    if removed is None:
        return messages.PERMISSIONS_NOT_FOUND.format(rule=rule.pattern, decision=decision.value)
    return messages.PERMISSIONS_REMOVED.format(
        rule=removed.pattern, decision=decision.value, path=removed.path
    )


def _render_list(state: ReplState) -> str:
    rows = permission_admin.rule_rows(state.root)
    loaded = state.permission_rules()
    lines = [f"· {row.pattern}  [{row.decision}]  ({row.source})" for row in rows]
    if not lines:
        lines.append(messages.PERMISSIONS_EMPTY)
    if loaded.untrusted_layers:
        lines.append(
            messages.PERMISSIONS_UNTRUSTED_LAYERS.format(layers=", ".join(loaded.untrusted_layers))
        )
    runtime = state.config.runtime
    lines.append(
        "kök dışı: okuma "
        + ("KAPALI" if runtime.block_reads_outside_root else "açık")
        + " · yazma "
        + ("KAPALI" if runtime.block_writes_outside_root else "onayla")
    )
    return "\n".join(lines)
