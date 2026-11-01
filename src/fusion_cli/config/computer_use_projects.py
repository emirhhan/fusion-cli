"""Computer use'un proje başına açılması (#420): `/mcp` › `computer-use` › Enable karşılığı.

Claude Code CLI'de computer use `computer-use` adlı yerleşik bir MCP sunucusudur; varsayılan
KAPALIDIR ve `/mcp` menüsünden proje başına açılır ("The setting persists per project").
Masaüstü uygulamasında ise Ayarlar › Bu bilgisayar › "Enable computer use" tek bir küresel
anahtardır (`desktop.enabled`).

Fusion ikisini ayrı tutar: küresel anahtar `desktop.enabled` (varsayılan false), proje başına
açılış kullanıcıya ait bir dosyada (`<kullanıcı yapılandırma dizini>/computer-use-projects.json`)
mutlak proje yollarının listesidir. Proje dosyası (`.fusion/config.yaml`) bunu açamaz: kayıt
kullanıcının kendi dizinindedir, depoya işlenmiş bir dosya bilgisayar kontrolünü açtıramaz.

Bilgisayar kullanımı etkileşimli oturum ister (#445): `-p`/headless ve `fusion mcp` yolları bu
kaydı okumaz, `desktop_*` ailesini her zaman kapatır (`cli/headless.apply_limits`).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from ..core.desktop_settings import DesktopSettings
from ..core.errors import ConfigError
from .paths import user_config_dir

#: `/mcp` listesinde görünen yerleşik sunucu adı (Claude Code ile aynı).
SERVER_NAME = "computer-use"
STORE_NAME = "computer-use-projects.json"


def store_path() -> Path:
    return user_config_dir() / STORE_NAME


def _key(root: Path) -> str:
    return str(root.expanduser().resolve())


def enabled_projects(path: Path | None = None) -> frozenset[str]:
    """Computer use'un açık olduğu projeler; dosya yoksa ya da bozuksa boş (kapalı taraf)."""
    target = store_path() if path is None else path
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    projects = payload.get("projects") if isinstance(payload, dict) else None
    if not isinstance(projects, list):
        return frozenset()
    return frozenset(item for item in projects if isinstance(item, str) and item)


def is_enabled_for(root: Path, path: Path | None = None) -> bool:
    return _key(root) in enabled_projects(path)


def set_enabled_for(root: Path, enabled: bool, path: Path | None = None) -> None:
    """Projenin kaydını yaz; yazılamazsa `ConfigError` (Türkçe)."""
    target = store_path() if path is None else path
    current = set(enabled_projects(target))
    key = _key(root)
    updated = current | {key} if enabled else current - {key}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"projects": sorted(updated)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise ConfigError(f"computer-use proje kaydı yazılamadı: {error}") from None


def effective(settings: DesktopSettings, root: Path, path: Path | None = None) -> DesktopSettings:
    """Küresel anahtar kapalıysa projenin kaydına bak; açıksa `enabled=True` kopyası."""
    if settings.enabled or not is_enabled_for(root, path):
        return settings
    return dataclasses.replace(settings, enabled=True)


def interactive_only(settings: DesktopSettings) -> DesktopSettings:
    """Etkileşimsiz yol (`-p`, arka plan işi, `fusion mcp`): computer use her zaman kapalı."""
    if not settings.enabled:
        return settings
    return dataclasses.replace(settings, enabled=False)
