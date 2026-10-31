"""`/hooks` — kancaları listele (P-009; Claude Code `/hooks` gibi salt okunur).

Tanımlar her kök turda dosyadan tazelenir; komut güncel hâli gösterir. Düzenleme dosyada
yapılır (Fusion: `<yapılandırma>/hooks.json`, Claude: `~/.claude/settings.json`).
"""

from __future__ import annotations

from ...config.hooks import user_hooks_file
from ...ui import messages
from ..hooks_view import hook_list_lines
from .state import ReplState

_LIST = frozenset({"", "list", "liste"})


def hooks(state: ReplState, argument: str) -> str:
    """Slash komut işleyicisi; çok satırlı Türkçe liste döndürür."""
    if argument.strip().lower() not in _LIST:
        return messages.HOOKS_USAGE.format(path=user_hooks_file())
    return "\n".join(hook_list_lines(state.hooks().refresh()))
