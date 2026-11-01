"""`/mcp` içindeki yerleşik `computer-use` satırı (#420).

Claude Code: computer use `/mcp` listesinde `computer-use` adlı yerleşik sunucu olarak
görünür, varsayılan "disabled"dır; sunucu seçilip **Enable** ile proje başına açılır.
Fusion'da aynı adım `/mcp enable computer-use` (kapatmak için `disable`); kayıt
`config/computer_use_projects.py`'dedir ve oturumun yapılandırması hemen güncellenir.
"""

from __future__ import annotations

import dataclasses

from ...config import computer_use_projects
from ...core.errors import ConfigError
from ...ui import messages
from .state import ReplState

_ENABLE = frozenset({"enable", "ac", "aç"})
_DISABLE = frozenset({"disable", "kapat"})


def status_row(state: ReplState) -> str:
    """`/mcp` listesine eklenen satır: açık mı, nereden açık (küresel / proje)."""
    if state.config.desktop.enabled and not computer_use_projects.is_enabled_for(state.root):
        status = messages.COMPUTER_USE_MCP_ENABLED_GLOBAL
    elif state.config.desktop.enabled:
        status = messages.COMPUTER_USE_MCP_ENABLED
    else:
        status = messages.COMPUTER_USE_MCP_DISABLED
    return messages.COMPUTER_USE_MCP_ROW.format(
        name=computer_use_projects.SERVER_NAME, status=status
    )


def handle(state: ReplState, sub_command: str, rest: str) -> str | None:
    """`/mcp enable|disable computer-use`; bu satıra ait değilse None (komut devam eder)."""
    if rest.strip() != computer_use_projects.SERVER_NAME:
        return None
    if sub_command in _ENABLE:
        enabled = True
    elif sub_command in _DISABLE:
        enabled = False
    else:
        return None
    try:
        computer_use_projects.set_enabled_for(state.root, enabled)
    except ConfigError as error:
        return messages.MCP_SAVE_FAILED.format(error=error)
    desktop = dataclasses.replace(state.config.desktop, enabled=enabled)
    state.config = dataclasses.replace(state.config, desktop=desktop)
    template = messages.COMPUTER_USE_MCP_ON if enabled else messages.COMPUTER_USE_MCP_OFF
    return template.format(root=state.root)
