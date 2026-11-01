"""Claude Code ayar dosyalarındaki izin anahtarları (kurallar dışındakiler).

Claude Code belgesiyle birebir (code.claude.com/docs/en/permission-modes, settings-reference):

    permissions.defaultMode                 başlangıç kipi; `auto` ve `bypassPermissions`
                                            proje ve yerel dosyada YOK SAYILIR (#50)
    permissions.disableAutoMode: "disable"  (ya da üst düzey `disableAutoMode`) auto kipini
                                            kapatır; her ayar dosyasında geçerli (#85)
    permissions.disableBypassPermissionsMode: "disable"  bypass kipini kapatır (#51)
    permissions.blockReadsOutsideWorkingDirectories      `true` her kapsamdan geçerli (#76)
    permissions.additionalDirectories       ek çalışma dizinleri; proje/yerel güven ister (#57)

Öncelik (yüksekten alçağa): yerel > proje > kullanıcı. Managed ve `--settings` katmanı henüz
yok (#65).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .permission_rules import CLAUDE_USER_SETTINGS
from .trust import (
    PROJECT_PERMISSIONS_PATH,
    PROJECT_SETTINGS_PATH,
    is_permissions_trusted,
    is_project_settings_trusted,
)

#: Claude Code'un geçerli `defaultMode` değerleri (`manual` = `default` takma adı).
CLAUDE_MODE_NAMES = frozenset(
    {"default", "manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"}
)
#: Proje ve yerel dosyada etkisiz `defaultMode` değerleri.
_PROJECT_IGNORED_MODES = frozenset({"auto", "bypassPermissions"})
_DISABLE = "disable"


@dataclass(frozen=True, slots=True)
class SettingsLayer:
    """Okunmuş bir ayar dosyası (`kullanici`, `proje`, `yerel`)."""

    name: str
    path: Path
    data: Mapping[str, object]
    trusted: bool = True

    @property
    def permissions(self) -> Mapping[str, object]:
        value = self.data.get("permissions")
        return value if isinstance(value, Mapping) else {}


def settings_layers(root: Path, home: Path | None = None) -> tuple[SettingsLayer, ...]:
    """Okuma sırasıyla (alçaktan yükseğe): kullanıcı → proje → yerel."""
    home = home or Path.home()
    found: list[SettingsLayer] = []
    sources = (
        ("kullanici", home / CLAUDE_USER_SETTINGS, True),
        ("proje", root / PROJECT_SETTINGS_PATH, is_project_settings_trusted(root)),
        ("yerel", root / PROJECT_PERMISSIONS_PATH, is_permissions_trusted(root)),
    )
    for name, path, trusted in sources:
        data = _read(path)
        if data is not None:
            found.append(SettingsLayer(name, path, data, trusted))
    return tuple(found)


def default_mode_setting(root: Path, home: Path | None = None) -> str | None:
    """Geçerli `permissions.defaultMode` (en yüksek öncelikli dosyadan); yoksa `None`."""
    for layer in reversed(settings_layers(root, home)):
        value = layer.permissions.get("defaultMode")
        if not isinstance(value, str) or value not in CLAUDE_MODE_NAMES:
            continue
        if layer.name != "kullanici" and value in _PROJECT_IGNORED_MODES:
            continue
        return value
    return None


def auto_mode_disabled(root: Path, home: Path | None = None) -> bool:
    """Herhangi bir ayar dosyası auto kipini kapatıyor mu?"""
    return any(
        layer.permissions.get("disableAutoMode") == _DISABLE
        or layer.data.get("disableAutoMode") == _DISABLE
        for layer in settings_layers(root, home)
    )


def bypass_mode_disabled(root: Path, home: Path | None = None) -> bool:
    """Herhangi bir ayar dosyası bypass kipini kapatıyor mu?"""
    return any(
        layer.permissions.get("disableBypassPermissionsMode") == _DISABLE
        for layer in settings_layers(root, home)
    )


def block_reads_outside_working_directories(root: Path, home: Path | None = None) -> bool:
    """`blockReadsOutsideWorkingDirectories: true` herhangi bir kapsamda var mı?"""
    return any(
        layer.permissions.get("blockReadsOutsideWorkingDirectories") is True
        for layer in settings_layers(root, home)
    )


def additional_directories(root: Path, home: Path | None = None) -> tuple[Path, ...]:
    """`permissions.additionalDirectories`: kullanıcıdan her zaman, proje/yerelden güvenle."""
    home = home or Path.home()
    found: list[Path] = []
    for layer in settings_layers(root, home):
        if not layer.trusted:
            continue
        entries = layer.permissions.get("additionalDirectories")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, str) and entry.strip():
                path = Path(entry.strip()).expanduser()
                found.append(path if path.is_absolute() else root / path)
    return tuple(dict.fromkeys(found))


def _read(path: Path) -> Mapping[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
