"""Claude in Chrome argümanlarının iç Chrome araçlarındaki karşılıkları (#431).

`computer` `modifiers` (ör. `cmd+shift`), `read_page` `max_chars` ve `tabs_context_mcp`
`createIfEmpty` burada işlenir; `chrome.py` yalnız bu yardımcıları çağırır.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from ..core.tools import ToolContext, ToolResult

#: Claude'un kabul ettiği değiştirici adları → eklentideki olay bayrağı.
MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "cmd": "meta",
    "command": "meta",
    "meta": "meta",
    "win": "meta",
    "windows": "meta",
}

#: Claude `read_page` varsayılan çıktı sınırı.
DEFAULT_MAX_CHARS = 50_000

Call = Callable[[ToolContext, str, dict[str, Any]], Awaitable[ToolResult]]


def parse_modifiers(value: object) -> list[str] | str:
    """`'cmd+Shift'` → `['meta', 'shift']`; boş → `[]`; tanınmayan ad → hata metni."""
    if value is None or value == "":
        return []
    if not isinstance(value, str):
        return "modifiers metin olmalı; ör. 'cmd+shift'."
    names: list[str] = []
    for part in value.split("+"):
        name = MODIFIER_ALIASES.get(part.strip().lower())
        if name is None:
            return (
                f"Tanınmayan değiştirici tuş: {part.strip()!r}. Geçerli: ctrl, shift, alt, "
                "cmd (meta), win; '+' ile birleştir."
            )
        if name not in names:
            names.append(name)
    return names


def limit_output(result: ToolResult, max_chars: object) -> ToolResult:
    """Okuma çıktısını `max_chars` ile kes; kesildiyse daraltma yolunu söyle."""
    if not result.ok or not isinstance(max_chars, int) or isinstance(max_chars, bool):
        return result
    limit = max(1, max_chars)
    if len(result.output) <= limit:
        return result
    return ToolResult(
        f"{result.output[:limit]}\n… (çıktı max_chars={limit} sınırında kesildi; depth "
        "küçült, ref_id ile alt ağaca in ya da filter=interactive kullan)"
    )


async def tabs_create_if_empty(context: ToolContext, call: Call) -> ToolResult:
    """Sekme listesi boşsa gruba boş sekme aç ve listeyi yeniden ver (`createIfEmpty`)."""
    listed = await call(context, "tabs", {})
    if not listed.ok or _has_tabs(listed.output):
        return listed
    opened = await call(context, "tab_open", {"blank": True})
    if not opened.ok:
        return opened
    return await call(context, "tabs", {})


def _has_tabs(output: str) -> bool:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return True
    tabs = data.get("tabs") if isinstance(data, dict) else None
    return not isinstance(tabs, list) or bool(tabs)
