"""`vimInsertModeRemaps` (#217, Claude Code): INSERT kipinde iki tuşluk dizi → Escape.

`~/.claude/settings.json` içinde `{"vimInsertModeRemaps": {"jj": "<Esc>"}}`. Anahtar tam iki
yazdırılabilir karakter, hedef yalnız `"<Esc>"`; öteki girdiler yok sayılır. İlk karakter
normal yazılır; ikincisi bir saniye içinde gelirse bekleyen karakter silinir ve NORMAL kipe
geçilir. Ayar yalnız kullanıcı dosyasından okunur: proje `.claude/settings*.json` bir deponun
tuş vuruşlarını değiştirmesine izin vermez (Claude Code ile aynı).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)
SETTING_KEY = "vimInsertModeRemaps"
TARGET = "<Esc>"
WINDOW_SECONDS = 1.0


def load_remaps(home: Path) -> tuple[str, ...]:
    """Geçerli iki karakterlik diziler (kullanıcı ayar dosyasından)."""
    path = home / ".claude" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()
    except (OSError, ValueError) as error:
        _LOG.debug("vimInsertModeRemaps okunamadı: %s", error)
        return ()
    table = data.get(SETTING_KEY) if isinstance(data, dict) else None
    if not isinstance(table, dict):
        return ()
    return tuple(
        key
        for key, value in table.items()
        if isinstance(key, str) and len(key) == 2 and key.isprintable() and value == TARGET
    )


def add_remap_bindings(
    kb: Any, remaps: tuple[str, ...], *, clock: Callable[[], float] = time.monotonic
) -> None:
    """prompt_toolkit bağlarını ekle (yalnız vi INSERT kipinde etkin)."""
    from prompt_toolkit.filters import vi_insert_mode
    from prompt_toolkit.key_binding.vi_state import InputMode

    pending: dict[str, float] = {}
    for first, second in {(key[0], key[1]) for key in remaps}:

        @kb.add(first, filter=vi_insert_mode)
        def _first(event: Any, first: str = first) -> None:
            event.current_buffer.insert_text(first)
            pending[first] = clock()

        @kb.add(second, filter=vi_insert_mode)
        def _second(event: Any, first: str = first, second: str = second) -> None:
            buffer = event.current_buffer
            started = pending.pop(first, None)
            fresh = started is not None and clock() - started <= WINDOW_SECONDS
            if fresh and buffer.document.text_before_cursor.endswith(first):
                buffer.delete_before_cursor(1)
                event.app.vi_state.input_mode = InputMode.NAVIGATION
                return
            buffer.insert_text(second)
