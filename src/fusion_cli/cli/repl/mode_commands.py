"""Eski kip slash komutları (/auto, /edits, /security, /bypass) — Claude'da yok (#51, #74).

Claude Code'da kip Shift+Tab ile değişir; slash komutu yalnız `/plan [açıklama]`dır. Fusion'ın
eski komutları bir sürüm boyunca kullanımdan kalkmış takma ad olarak çalışır ve bir kez uyarır.
`/bypass` Claude'daki kurala uyar: bypass etkin başlamamış oturum bypass'a geçemez
(`--permission-mode bypassPermissions`, `--dangerously-skip-permissions` ya da kullanıcı
ayarında `defaultMode: bypassPermissions` gerekir).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...engines.agent.approval import ApprovalMode
from ...ui import messages

if TYPE_CHECKING:
    from .state import ReplState

LEGACY_COMMAND_NOTE = (
    "uyarı: /{name} kullanımdan kalktı; kipi Claude Code'daki gibi Shift+Tab ile değiştirin."
)
BYPASS_UNAVAILABLE = (
    "bypassPermissions bu oturumda kullanılamıyor: bypass ile başlamayan oturum bypass'a "
    "geçemez. `fusion --permission-mode bypassPermissions` ya da kullanıcı ayarında "
    '`"defaultMode": "bypassPermissions"` ile başlatın.'
)
_warned: set[str] = set()


def legacy_mode(name: str, mode: ApprovalMode) -> Callable[[ReplState, str], str]:
    """Kipi değiştir; komut adı başına bir kez kullanımdan kalktı uyarısı ekle."""

    def _handler(state: ReplState, argument: str) -> str:
        if mode is ApprovalMode.BYPASS and not getattr(state, "bypass_available", False):
            return BYPASS_UNAVAILABLE
        if mode is ApprovalMode.AUTO and not getattr(state, "auto_available", True):
            return "auto kipi ayarla kapatılmış (disableAutoMode)."
        state.approval = mode
        text = messages.REPL_MODE_CHANGED.format(mode=mode.value)
        if name not in _warned:
            _warned.add(name)
            text = f"{text}\n{LEGACY_COMMAND_NOTE.format(name=name)}"
        return text

    return _handler
