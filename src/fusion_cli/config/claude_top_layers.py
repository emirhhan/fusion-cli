"""Claude ayar katmanlarının en üst ikisi: `--settings` ve yönetilen (managed) ayarlar (#321, #328).

Claude Code (code.claude.com/docs/en/settings#settings-precedence) önceliği:
managed > komut satırı (`--settings`) > yerel > proje > kullanıcı. Sandbox bölümü
(`claude_sandbox_settings`) ve `permissions.defaultMode` (`start_mode`) kullanıcı/proje/yerel
dosyalarını kendisi okur; bu modül üstteki iki katmanı aynı biçimde (`SettingsLayer`) verir.

Yönetilen dosyalar Claude ile aynı yerdedir (macOS `/Library/Application Support/ClaudeCode`,
Linux `/etc/claude-code`, Windows `C:/Program Files/ClaudeCode`): `managed-settings.json`, sonra
`managed-settings.d/*.json` alfabetik sırayla. Güven denetimi gerekmez (yönetici dosyası); Fusion
bu dosyalara yazmaz. Testler sistem dizinine dokunmasın diye `FUSION_CLAUDE_MANAGED_DIR` ezer.

`--settings <dosya|json>` içeriği süreç ortamında taşınır (`FUSION_FLAG_SETTINGS_JSON`) ki aynı
süreçteki alt ajanlar ve oturumdan başlatılan alt süreçler aynı değeri görsün. Bayrağı okuyan
kök komut `set_flag_settings(veri, dosya)` çağırır; dosyanın dizini göreli sandbox yollarının
tabanıdır (`FUSION_FLAG_SETTINGS_DIR`), satır içi JSON'da proje kökü.
"""

from __future__ import annotations

import json
import logging
import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "FLAG_SETTINGS_ENV",
    "MANAGED_DIR_ENV",
    "SettingsLayer",
    "flag_layer",
    "managed_layers",
    "set_flag_settings",
    "top_layers",
]

_LOG = logging.getLogger(__name__)

MANAGED_DIRS: dict[str, Path] = {
    "Darwin": Path("/Library/Application Support/ClaudeCode"),
    "Linux": Path("/etc/claude-code"),
    "Windows": Path("C:/Program Files/ClaudeCode"),
}
MANAGED_DIR_ENV = "FUSION_CLAUDE_MANAGED_DIR"
FLAG_SETTINGS_ENV = "FUSION_FLAG_SETTINGS_JSON"
FLAG_SETTINGS_DIR_ENV = "FUSION_FLAG_SETTINGS_DIR"
#: `--settings` içinden taşınan bölümler (izin kuralları ayrı katmanda taşınır).
_FLAG_KEYS = ("sandbox", "permissions")


@dataclass(frozen=True, slots=True)
class SettingsLayer:
    """Bir ayar katmanı: ad (`managed`/`bayrak`), içerik, göreli yol tabanı, kaynak."""

    name: str
    data: Mapping[str, object]
    base: Path
    source: Path


def _read(path: Path) -> dict[str, object] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        _LOG.warning("Yönetilen ayar dosyası okunamadı; atlandı: %s", path)
        return None
    return raw if isinstance(raw, dict) else None


def _managed_dir() -> Path | None:
    override = os.environ.get(MANAGED_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return MANAGED_DIRS.get(platform.system())


def managed_layers() -> list[SettingsLayer]:
    """Yönetilen dosyalar okuma sırasıyla: ana dosya, sonra `managed-settings.d/*.json`."""
    base = _managed_dir()
    if base is None:
        return []
    files = [base / "managed-settings.json"]
    try:
        files.extend(sorted((base / "managed-settings.d").glob("*.json")))
    except OSError:
        pass
    layers = []
    for path in files:
        data = _read(path) if path.is_file() else None
        if data is not None:
            layers.append(SettingsLayer("managed", data, base, path))
    return layers


def set_flag_settings(settings: Mapping[str, object] | None, source: Path | None = None) -> None:
    """`--settings` içeriğini (sandbox, permissions) bu süreç için kaydet; `None` siler."""
    kept = {key: settings[key] for key in _FLAG_KEYS if settings and key in settings}
    if not kept:
        os.environ.pop(FLAG_SETTINGS_ENV, None)
        return
    os.environ[FLAG_SETTINGS_ENV] = json.dumps(kept, ensure_ascii=False)
    if source is not None:
        os.environ[FLAG_SETTINGS_DIR_ENV] = str(Path(source).expanduser().resolve().parent)


def flag_layer(root: Path) -> SettingsLayer | None:
    """Ortamdaki `--settings` katmanı; yoksa ya da bozuksa `None`."""
    raw = os.environ.get(FLAG_SETTINGS_ENV, "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        _LOG.warning("%s bozuk; --settings katmanı atlandı", FLAG_SETTINGS_ENV)
        return None
    if not isinstance(data, dict):
        return None
    base_raw = os.environ.get(FLAG_SETTINGS_DIR_ENV, "").strip()
    base = Path(base_raw) if base_raw and Path(base_raw).is_absolute() else root
    return SettingsLayer("bayrak", data, base, Path("--settings"))


def top_layers(root: Path) -> list[SettingsLayer]:
    """Kullanıcı/proje/yerel dosyalarının üstündeki katmanlar, artan öncelikle."""
    flag = flag_layer(root)
    return [*([flag] if flag is not None else []), *managed_layers()]
