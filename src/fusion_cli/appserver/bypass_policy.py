"""Masaüstünde İzinleri atla (bypassPermissions) kipinin ayar/politikayla kapatılması (#442).

Claude Code Desktop: Pro/Max'ta Bypass ancak Ayarlar'daki "Allow bypass permissions mode"
anahtarıyla seçilebilir (Fusion'da Ayarlar › İzinler; değer uygulamanın yerel deposunda);
Team/Enterprise'da kurum politikası belirler. Politika Claude ayar dosyalarındaki
`permissions.disableBypassPermissionsMode: "disable"` anahtarıdır; herhangi bir kapsamda
(kullanıcı, proje, yerel, yönetilen) görülürse bypass açılamaz ve arayüz anahtarı kilitlenir.

İzinler alanının ortak okuyucusu (`config.permission_settings.bypass_mode_disabled`) varsa
o kullanılır; yoksa aynı dört dosya burada okunur (yalnız okuma, kısıtlayıcı yön).
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import sys
from collections.abc import Callable
from pathlib import Path

_DISABLE = "disable"
_KEY = "disableBypassPermissionsMode"
#: Yönetilen ayar dizini (Claude Code ile aynı konumlar).
_MANAGED_DIRS = {
    "Darwin": Path("/Library/Application Support/ClaudeCode"),
    "Linux": Path("/etc/claude-code"),
    "Windows": Path("C:/Program Files/ClaudeCode"),
}
#: Test sürecinde yönetilen dizini ezer (izinler alanıyla aynı ad; üretimde etkisiz).
_MANAGED_DIR_ENV = "FUSION_CLAUDE_MANAGED_DIR"


def bypass_policy_disabled(root: Path, home: Path | None = None) -> bool:
    """Ayar dosyalarından biri bypass kipini kapatıyor mu?"""
    shared = _shared_reader()
    if shared is not None:
        return bool(shared(root, home))
    return any(_disables(path) for path in _settings_files(root, home or Path.home()))


def _shared_reader() -> Callable[..., object] | None:
    try:
        module = importlib.import_module("fusion_cli.config.permission_settings")
    except ImportError:
        return None
    reader = getattr(module, "bypass_mode_disabled", None)
    return reader if callable(reader) else None


def _settings_files(root: Path, home: Path) -> tuple[Path, ...]:
    files = [
        home / ".claude" / "settings.json",
        root / ".claude" / "settings.json",
        root / ".claude" / "settings.local.json",
    ]
    managed = _managed_dir()
    if managed is not None:
        files.append(managed / "managed-settings.json")
    return tuple(files)


def _managed_dir() -> Path | None:
    override = os.environ.get(_MANAGED_DIR_ENV, "").strip()
    if override and "pytest" in sys.modules:
        return Path(override).expanduser()
    return _MANAGED_DIRS.get(platform.system())


def _disables(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    permissions = data.get("permissions") if isinstance(data, dict) else None
    return isinstance(permissions, dict) and permissions.get(_KEY) == _DISABLE
