"""`/hooks` — kanca tarayıcısı (P-009, #130; Claude Code `/hooks` gibi salt okunur).

Argümansız ya da `list`: numaralı liste (kaynak etiketiyle); `<no>`: kancanın tam metni ve
tanım yeri; `all`: tanımı olmayanlar dahil bütün olaylar. TUI argümansız çağrıda
uygulama-içi seçici açar (`hooks_browser.hook_choices`). Ayar dosyaları izlendiği için
liste güncel hâli gösterir; düzenleme dosyada yapılır (`~/.claude/settings.json`).
"""

from __future__ import annotations

from ...config.hooks import user_hooks_file
from ...ui import messages
from ..hooks_view import hook_list_lines
from . import hooks_browser
from .state import ReplState

_LIST = frozenset({"", "list", "liste"})


def hooks(state: ReplState, argument: str) -> str:
    """Slash komut işleyicisi; çok satırlı Türkçe metin döndürür."""
    session = state.hooks()
    session.refresh()
    current = session.current()
    wanted = argument.strip().lower()
    if wanted in _LIST:
        if not current.commands:
            return "\n".join(hook_list_lines(current))
        return "\n".join(hooks_browser.browser_lines(current))
    if hooks_browser.is_all_events(wanted):
        return "\n".join(hooks_browser.all_event_lines(current))
    detail = hooks_browser.detail_lines(current, wanted)
    if detail is None:
        return messages.HOOKS_USAGE.format(path=user_hooks_file())
    return "\n".join(detail)
