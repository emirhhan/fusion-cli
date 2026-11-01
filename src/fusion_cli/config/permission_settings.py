"""Claude Code ayar dosyalarındaki izin anahtarları (kurallar dışındakiler).

Claude Code belgesiyle birebir (code.claude.com/docs/en/permission-modes, settings-reference):

    permissions.defaultMode                 başlangıç kipi; `auto` ve `bypassPermissions`
                                            proje ve yerel dosyada YOK SAYILIR (#50)
    permissions.disableAutoMode: "disable"  (ya da üst düzey `disableAutoMode`) auto kipini
                                            kapatır; her ayar dosyasında geçerli (#85)
    permissions.disableBypassPermissionsMode: "disable"  bypass kipini kapatır (#51)
    permissions.blockReadsOutsideWorkingDirectories      `true` her kapsamdan geçerli (#76)
    permissions.additionalDirectories       ek çalışma dizinleri; proje/yerel güven ister (#57)
    useAutoModeDuringPlan                   varsayılan `true`: plan kipinde auto sınıflandırıcısı
                                            komutu inceler; `false` kullanıcı/yerel/yönetilen
                                            dosyada geçerli, proje dosyasında yok sayılır (#52)

Öncelik (yüksekten alçağa): yönetilen (managed) > yerel > proje > kullanıcı (#65). Managed
dosyada `auto`/`bypassPermissions` başlangıç kipi geçerlidir; managed `disable` hiçbir
katmanca geri açılamaz.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .local_settings_location import local_settings_path
from .managed_settings import MANAGED_SETTINGS_NAME, managed_dir, managed_settings_data
from .permission_rules import CLAUDE_USER_SETTINGS
from .trust import (
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
#: `defaultMode` değerinde kısıtsız katmanlar.
_UNRESTRICTED_MODE_LAYERS = frozenset({"kullanici", "yonetilen"})
#: Depoyla gelen paylaşılan dosya: kullanıcının güvenlik tercihini kapatamaz.
_PROJECT_LAYER = "proje"


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
    """Okuma sırasıyla (alçaktan yükseğe): kullanıcı → proje → yerel → yönetilen."""
    home = home or Path.home()
    found: list[SettingsLayer] = []
    sources = (
        ("kullanici", home / CLAUDE_USER_SETTINGS, True),
        ("proje", root / PROJECT_SETTINGS_PATH, is_project_settings_trusted(root)),
        ("yerel", local_settings_path(root), is_permissions_trusted(root)),
    )
    for name, path, trusted in sources:
        data = _read(path)
        if data is not None:
            found.append(SettingsLayer(name, path, data, trusted))
    managed = managed_settings_data()
    if managed:
        found.append(SettingsLayer("yonetilen", _managed_path(), managed, True))
    return tuple(found)


def _managed_path() -> Path:
    return (managed_dir() or Path()) / MANAGED_SETTINGS_NAME


def default_mode_setting(root: Path, home: Path | None = None) -> str | None:
    """Geçerli `permissions.defaultMode` (en yüksek öncelikli dosyadan); yoksa `None`."""
    for layer in reversed(settings_layers(root, home)):
        value = layer.permissions.get("defaultMode")
        if not isinstance(value, str) or value not in CLAUDE_MODE_NAMES:
            continue
        if layer.name not in _UNRESTRICTED_MODE_LAYERS and value in _PROJECT_IGNORED_MODES:
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


def use_auto_mode_during_plan(root: Path, home: Path | None = None) -> bool:
    """`useAutoModeDuringPlan` açık mı? Proje dosyası dışındaki herhangi bir `false` kapatır."""
    return not any(
        layer.data.get("useAutoModeDuringPlan") is False
        for layer in settings_layers(root, home)
        if layer.name != _PROJECT_LAYER
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


def working_directories(
    root: Path, extra: tuple[Path, ...] = (), home: Path | None = None
) -> tuple[Path, ...]:
    """`--add-dir` dizinleri + ayarlardaki `additionalDirectories` (var olan dizinler, #57)."""
    found = [Path(item) for item in extra]
    for path in additional_directories(root, home):
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            continue
        if resolved.is_dir():
            found.append(resolved)
    return tuple(dict.fromkeys(found))


def _read(path: Path) -> Mapping[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
