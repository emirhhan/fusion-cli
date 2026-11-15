"""`!` kabuk kipinden sonra modelin kendiliğinden yanıtı (#219, Claude Code).

Claude Code: `! npm test` çıktısı transcript'e düşünce Claude ikinci istem beklemeden yanıt
verir; `settings.json` içinde `respondToBashCommands: false` yalnız bağlama ekler. Ayar Claude
katmanlarından okunur (kullanıcı `~/.claude/settings.json`, proje `.claude/settings.json`,
yerel `.claude/settings.local.json`; sonraki katman kazanır). Varsayılan açıktır.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ...ui import messages

_LOG = logging.getLogger(__name__)
SETTING_KEY = "respondToBashCommands"


def _layers(root: Path, home: Path) -> tuple[Path, ...]:
    return (
        home / ".claude" / "settings.json",
        root / ".claude" / "settings.json",
        root / ".claude" / "settings.local.json",
    )


def _read_flag(path: Path) -> bool | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        _LOG.debug("ayar okunamadı (%s): %s", path, type(error).__name__)
        return None
    value = data.get(SETTING_KEY) if isinstance(data, dict) else None
    return value if isinstance(value, bool) else None


def responds_to_bash_commands(root: Path, home: Path) -> bool:
    """`respondToBashCommands` etkin değeri; hiçbir katmanda yoksa True."""
    result = True
    for path in _layers(root, home):
        value = _read_flag(path)
        if value is not None:
            result = value
    return result


def follow_up_task(command: str) -> str:
    """Kabuk çıktısından sonra başlayan turun görevi (çıktı zaten bağlamda)."""
    return messages.SHELL_PREFIX_RESPOND.format(command=command)
