"""Claude Code `statusLine` ayarı (#192): `{type, command, padding, refreshInterval,
hideVimModeIndicator}`.

Okuma sırası (sonraki öncekini ezer, Claude'daki gibi özel olan kazanır): Claude kullanıcı
ayarı (`~/.claude/settings.json`), Fusion'ın eski `runtime.status_line_command` dizesi
(kullanımdan kalkmış takma ad; yalnız komut), proje `.claude/settings.json`, yerel
`.claude/settings.local.json`. Proje dosyaları kabuk komutu çalıştırdığı için yalnız
`fusion trust` sonrası okunur (kancalarla aynı kural, `config/hooks.py`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ...config.models import Config
from ...config.trust import (
    PROJECT_PERMISSIONS_PATH,
    PROJECT_SETTINGS_PATH,
    is_permissions_trusted,
    is_project_settings_trusted,
)

SETTINGS_KEY = "statusLine"
CLAUDE_USER_SETTINGS = Path(".claude") / "settings.json"
#: Claude: `refreshInterval` en az 1 sn.
MIN_REFRESH_S = 1


@dataclass(frozen=True, slots=True)
class StatusLineSpec:
    """Çözümlenmiş durum satırı ayarı."""

    command: str
    padding: int = 0
    refresh_interval_s: int | None = None
    hide_vim_mode_indicator: bool = False
    source: str = ""


def _read(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _int(raw: object, *, minimum: int) -> int | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return max(minimum, int(raw))


def parse_status_line(raw: object, source: str) -> StatusLineSpec | None:
    """`statusLine` nesnesini çöz; komutsuz ya da `type` 'command' değilse `None`."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type", "command")
    command = raw.get("command")
    if kind != "command" or not isinstance(command, str) or not command.strip():
        return None
    refresh = _int(raw.get("refreshInterval"), minimum=MIN_REFRESH_S)
    return StatusLineSpec(
        command=command.strip(),
        padding=_int(raw.get("padding"), minimum=0) or 0,
        refresh_interval_s=refresh,
        hide_vim_mode_indicator=raw.get("hideVimModeIndicator") is True,
        source=source,
    )


def _layer(path: Path, source: str) -> StatusLineSpec | None:
    data = _read(path)
    return None if data is None else parse_status_line(data.get(SETTINGS_KEY), source)


def resolve_status_line(config: Config, root: Path, home: Path) -> StatusLineSpec | None:
    """Geçerli durum satırı ayarı; hiçbiri yoksa `None` (yerleşik çubuk)."""
    found = _layer(home / CLAUDE_USER_SETTINGS, "user")
    legacy = str(getattr(config.runtime, "status_line_command", "") or "").strip()
    if legacy:
        found = StatusLineSpec(command=legacy, source="fusion")
    if is_project_settings_trusted(root):
        found = _layer(root / PROJECT_SETTINGS_PATH, "project") or found
    if is_permissions_trusted(root):
        found = _layer(root / PROJECT_PERMISSIONS_PATH, "local") or found
    return found
