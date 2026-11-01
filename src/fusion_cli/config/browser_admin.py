"""Yerleşik tarayıcının yönetici ayarları (#439; Claude Code Desktop managed settings).

- `disableBrowserExternalNavigation: true`: Browser bölmesinde dış sitelere gezinme hem
  kullanıcıya hem ajana kapalı; localhost geliştirme sunucuları ve yerel dosya önizlemesi çalışır.
- `browserExternalPageTools: false`: kullanıcı dış sitelere gidebilir ama ajanın araçları o
  sayfaları okuyamaz ve onlarda eylem yapamaz.

Yalnız yönetilen ayar dosyası (`managed-settings.json`, Claude Code'la aynı konum) okunur:
kullanıcı ya da proje dosyası bu kısıtları gevşetemez de koyamaz da (Claude'da yönetici ayarı).
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

_MANAGED_DIRS = {
    "Darwin": Path("/Library/Application Support/ClaudeCode"),
    "Linux": Path("/etc/claude-code"),
    "Windows": Path("C:/Program Files/ClaudeCode"),
}
#: Test sürecinde yönetilen dizini ezer (izinler alanıyla aynı ad; üretimde etkisiz).
_MANAGED_DIR_ENV = "FUSION_CLAUDE_MANAGED_DIR"


@dataclass(frozen=True)
class BrowserAdmin:
    external_navigation: bool = True
    external_page_tools: bool = True


def _managed_file() -> Path | None:
    override = os.environ.get(_MANAGED_DIR_ENV, "").strip()
    if override and "pytest" in sys.modules:
        return Path(override).expanduser() / "managed-settings.json"
    base = _MANAGED_DIRS.get(platform.system())
    return base / "managed-settings.json" if base is not None else None


def load_browser_admin(path: Path | None = None) -> BrowserAdmin:
    """Yönetici ayarı; dosya yoksa ya da okunamıyorsa kısıt yok."""
    target = path or _managed_file()
    if target is None:
        return BrowserAdmin()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return BrowserAdmin()
    if not isinstance(data, dict):
        return BrowserAdmin()
    return BrowserAdmin(
        external_navigation=data.get("disableBrowserExternalNavigation") is not True,
        external_page_tools=data.get("browserExternalPageTools") is not False,
    )
