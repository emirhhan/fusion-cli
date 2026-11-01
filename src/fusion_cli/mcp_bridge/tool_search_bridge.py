"""MCP sunucusu araçlarını araç aramasına (`ToolSearch`) bağlar (#258).

Hangi aracın ertelendiğini Claude Code kuralıyla seçer: sunucu `alwaysLoad: true` →
baştan; `alwaysLoad: false` → hepsi ertelenir (aracın işareti dahil); yazılmamışsa
aracın `_meta["anthropic/alwaysLoad"]: true` işareti baştan yükler, diğerleri ertelenir.
Baştan yüklenen açıklama 4096, aramayla yüklenen 16384 karakterde kesilir
(`CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` ikisini de değiştirir).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from ..config.models import McpServerConfig
from ..tools import ToolRegistry
from ..tools.tool_search import (
    ToolSearchMode,
    ToolSearchState,
    refresh_tool_search,
    tool_search_mode,
    tool_search_state,
)
from .schema import description_limit
from .types import RemoteTool

__all__ = ["ALWAYS_LOAD_META", "McpToolSearch", "is_deferrable", "meta_always_load"]

ALWAYS_LOAD_META = "anthropic/alwaysLoad"


def meta_always_load(meta: object) -> bool | None:
    """Araç `_meta` nesnesindeki `anthropic/alwaysLoad`; yoksa ya da bool değilse None."""
    if not isinstance(meta, Mapping):
        return None
    value = meta.get(ALWAYS_LOAD_META)
    return value if isinstance(value, bool) else None


def is_deferrable(config: McpServerConfig | None, tool: RemoteTool) -> bool:
    """Araç arama açıkken ertelenir mi (sunucu ayarı aracın işaretini ezer)."""
    server_flag = getattr(config, "always_load", None)
    if server_flag is True:
        return False
    if server_flag is False:
        return True
    return tool.always_load is not True


class McpToolSearch:
    """Bir istemcinin araçlarını paylaşılan `ToolSearch` durumuna yazar."""

    def __init__(self, mode: ToolSearchMode | None = None) -> None:
        self.mode = mode if mode is not None else tool_search_mode()

    def description(self, config: McpServerConfig | None, tool: RemoteTool) -> str:
        """Kayda yazılacak açıklama: ertelenen araçta uzun, baştan yüklenende kısa sınır."""
        deferred = (
            self.mode.enabled and self.mode.threshold_pct is None and is_deferrable(config, tool)
        )
        return tool.description[: description_limit(deferred=deferred)]

    def apply(
        self,
        registry: ToolRegistry,
        server: str,
        config: McpServerConfig | None,
        named: Sequence[tuple[str, RemoteTool]],
        previous: Iterable[str],
    ) -> None:
        """Sunucunun ertelenebilir adlarını yenile; `ToolSearch`'ü kur ya da kaldır."""
        if not self.mode.enabled:
            return
        state = tool_search_state(registry) or ToolSearchState(
            mode=self.mode, upfront_limit=description_limit()
        )
        deferrable = [name for name, remote in named if is_deferrable(config, remote)]
        state.set_owner(server, deferrable, previous)
        refresh_tool_search(registry, state)
