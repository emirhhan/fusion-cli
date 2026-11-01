"""Claude Code `settings.json` katmanlarından tek anahtar okuma (talimat/beceri ayarları).

Claude Code ayarları şu katmanlarda tutar (genelden özele): kurumsal (`managed-settings.json`),
kullanıcı (`~/.claude/settings.json`), proje (`.claude/settings.json`), yerel
(`.claude/settings.local.json`). Bu modül talimat ve beceri yüklemesinin ihtiyaç duyduğu
anahtarları (`claudeMdExcludes`, `disableSkillShellExecution`, `skillOverrides`,
`skillListingBudgetFraction`, `autoMemoryEnabled`…) aynı katmanlardan okur.

İzin kuralları ayrı yükleyicidedir (`permission_rules`); burası yalnız düz anahtar okur ve
hiçbir dosyaya yazmaz. Bozuk ya da okunamayan dosya o katmanı boş sayar.

Katman okuma (`claude_settings_layers`, `claude_setting`): ayar katmanları Claude
önceliğiyle okunur, tek bir üst düzey değer döndürülür.

Sıra Claude Code'daki gibidir (settings#settings-precedence; sonraki öncekini ezer):
`~/.claude/settings.json`, proje `.claude/settings.json`, `.claude/settings.local.json`,
`--settings` ve en üstte yönetilen (managed) ayarlar (`claude_top_layers`). Proje dosyaları
yalnız güvenilen projede okunur. Bozuk dosya yazılımı durdurmaz: uyarı yazılır, dosya atlanır.
`claude_setting`, `worktree.*` (#338, #361) ve diğer tek değer okuyucuları bu tek okuyucuyu
kullanır.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .claude_home import claude_user_dir
from .claude_top_layers import top_layers
from .trust import is_permissions_trusted, is_project_settings_trusted

#: Kurumsal ayar dosyası konumları (işletim sistemine göre).
MANAGED_DIRS: dict[str, Path] = {
    "Darwin": Path("/Library/Application Support/ClaudeCode"),
    "Linux": Path("/etc/claude-code"),
    "Windows": Path("C:/Program Files/ClaudeCode"),
}

#: Testlerin gerçek sistem dizinine dokunmaması için kurumsal dizini ezer.
MANAGED_DIR_ENV = "FUSION_CLAUDE_MANAGED_DIR"

USER_SETTINGS = Path(".claude") / "settings.json"
PROJECT_SETTINGS = Path(".claude") / "settings.json"
LOCAL_SETTINGS = Path(".claude") / "settings.local.json"

LAYER_MANAGED = "managed"
LAYER_USER = "user"
LAYER_PROJECT = "project"
LAYER_LOCAL = "local"


@dataclass(frozen=True, slots=True)
class SettingValue:
    """Bir katmandan okunan değer."""

    layer: str
    path: Path
    value: object


def managed_dir() -> Path | None:
    """Kurumsal Claude Code dizini; ortam değişkeni verilmişse o."""
    override = os.environ.get(MANAGED_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return MANAGED_DIRS.get(platform.system())


def settings_files(root: Path, home: Path | None) -> tuple[tuple[str, Path], ...]:
    """Okuma sırasıyla `(katman, dosya)`: kurumsal → kullanıcı → proje → yerel."""
    files: list[tuple[str, Path]] = []
    managed = managed_dir()
    if managed is not None:
        files.append((LAYER_MANAGED, managed / "managed-settings.json"))
    if home is not None:
        files.append((LAYER_USER, home / USER_SETTINGS))
    files.append((LAYER_PROJECT, root / PROJECT_SETTINGS))
    files.append((LAYER_LOCAL, root / LOCAL_SETTINGS))
    return tuple(files)


def read_json(path: Path) -> dict[str, object] | None:
    """JSON nesnesi oku; yoksa/bozuksa `None`."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def setting_values(
    root: Path, home: Path | None, key: str, *, layers: Iterable[str] | None = None
) -> tuple[SettingValue, ...]:
    """`key` anahtarının her katmandaki değeri (yalnız yazılmış olanlar)."""
    wanted = frozenset(layers) if layers is not None else None
    found: list[SettingValue] = []
    for layer, path in settings_files(root, home):
        if wanted is not None and layer not in wanted:
            continue
        data = read_json(path)
        if data is not None and key in data:
            found.append(SettingValue(layer, path, data[key]))
    return tuple(found)


def merged_list(root: Path, home: Path | None, key: str) -> tuple[str, ...]:
    """Dizi anahtarı: katmanlar arasında birleşir (Claude `claudeMdExcludes` kuralı)."""
    items: list[str] = []
    for item in setting_values(root, home, key):
        if isinstance(item.value, list):
            items.extend(str(entry) for entry in item.value if isinstance(entry, str))
    return tuple(dict.fromkeys(items))


def effective(root: Path, home: Path | None, key: str, default: object = None) -> object:
    """Tek değerli anahtar: kurumsal her zaman kazanır, yoksa en özel katman."""
    values = setting_values(root, home, key)
    if not values:
        return default
    managed = [item for item in values if item.layer == LAYER_MANAGED]
    return (managed[0] if managed else values[-1]).value


def effective_bool(root: Path, home: Path | None, key: str, default: bool = False) -> bool:
    value = effective(root, home, key, default)
    return value if isinstance(value, bool) else default


def effective_float(root: Path, home: Path | None, key: str, default: float) -> float:
    value = effective(root, home, key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return float(value)


def effective_int(root: Path, home: Path | None, key: str, default: int) -> int:
    value = effective(root, home, key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def merged_mapping(root: Path, home: Path | None, key: str) -> dict[str, object]:
    """Nesne anahtarı: katmanlar sırayla üst üste yazılır (özel olan kazanır)."""
    merged: dict[str, object] = {}
    for item in setting_values(root, home, key):
        if isinstance(item.value, dict):
            merged.update({str(name): value for name, value in item.value.items()})
    return merged


_LOG = logging.getLogger(__name__)


def _load(path: Path) -> Mapping[str, object] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        _LOG.warning("Claude ayar dosyası okunamadı; atlandı: %s", path)
        return None
    return raw if isinstance(raw, dict) else None


def claude_settings_layers(
    root: Path, *, home: Path | None = None
) -> list[tuple[Mapping[str, object], Path]]:
    """(içerik, kaynak) çiftleri artan öncelikle: kullanıcı, proje, yerel, --settings, managed."""
    paths = [claude_user_dir(home) / "settings.json"]
    if is_project_settings_trusted(root):
        paths.append(root / ".claude" / "settings.json")
    if is_permissions_trusted(root):
        paths.append(root / ".claude" / "settings.local.json")
    layers = [(data, path) for path in paths if (data := _load(path)) is not None]
    layers.extend((top.data, top.source) for top in top_layers(root))
    return layers


def claude_setting(root: Path, key: str, *, home: Path | None = None) -> object | None:
    """`key` için en yüksek öncelikli katmandaki değer; hiçbir katmanda yoksa `None`."""
    found: object | None = None
    for data, _ in claude_settings_layers(root, home=home):
        if key in data:
            found = data[key]
    return found
