"""Oturumun başlangıç izin kipi: `--permission-mode` ve `permissions.defaultMode` (#328).

Claude Code (permission-modes, "Start in a different permission mode") sırası:
1. `--permission-mode <kip>` bayrağı;
2. `permissions.defaultMode` (`.claude/settings.local.json` > `.claude/settings.json` >
   `~/.claude/settings.json`). Proje ve yerel dosyada `"auto"` yok sayılır ve kullanıcı
   dosyasına düşülmez (yerleşik varsayılan kullanılır); `"bypassPermissions"` yok sayılır ve
   oturum Manual açılır;
3. yerleşik varsayılan (`auto`). Fusion'ın eski `runtime.approval_mode` ayarı bu adımda okunur.
Bypass kipine yalnız bununla başlatılan oturumda girilebilir; root olarak reddedilir (Fusion
Manual açar). Otomatik kip kullanılamıyorsa (`disableAutoMode`, desteklenmeyen model) Manual.

Değerler Fusion'ın kip adlarıyla döner (`auto`, `edits`, `security`, `plan`, `bypass`,
`dontAsk`); çağıran `ApprovalMode(...)` ile çevirir (config katmanı motoru içe aktarmaz).
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import ConfigError
from .trust import is_permissions_trusted, is_project_settings_trusted

_LOG = logging.getLogger(__name__)

#: Claude kip adı (ve Fusion'ın eski adları) → Fusion kip değeri.
_MODES = {
    "default": "security",
    "manual": "security",
    "acceptEdits": "edits",
    "plan": "plan",
    "auto": "auto",
    "dontAsk": "dontAsk",
    "bypassPermissions": "bypass",
    # Eski Fusion adları (takma ad):
    "security": "security",
    "edits": "edits",
    "bypass": "bypass",
}
MANUAL = "security"
BUILT_IN_DEFAULT = "auto"


@dataclass(frozen=True, slots=True)
class StartMode:
    mode: str
    #: Bypass Shift+Tab döngüsünde mi (oturum bypass ile başladı).
    bypass_available: bool = False
    #: Kullanıcıya bir kez gösterilecek açıklama (ör. root'ta bypass reddi).
    note: str = ""


def parse_mode(value: str) -> str:
    """Bayrak değerini Fusion kipine çevir; bilinmeyen değer `ConfigError`."""
    mode = _MODES.get(value.strip())
    if mode is None:
        allowed = "default, acceptEdits, plan, auto, dontAsk, bypassPermissions"
        raise ConfigError(f"Geçersiz --permission-mode: {value!r}. Geçerli kipler: {allowed}.")
    return mode


def _default_mode(path: Path) -> str | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        _LOG.warning("Claude ayar dosyası okunamadı; defaultMode atlandı: %s", path)
        return None
    permissions = raw.get("permissions") if isinstance(raw, dict) else None
    value = permissions.get("defaultMode") if isinstance(permissions, dict) else None
    return value if isinstance(value, str) else None


def _from_settings(root: Path, home: Path) -> tuple[str | None, bool]:
    """(kip, kullanıcı dosyasından mı) — dosyalarda yoksa (None, False)."""
    project_files = []
    if is_permissions_trusted(root):
        project_files.append(root / ".claude" / "settings.local.json")
    if is_project_settings_trusted(root):
        project_files.append(root / ".claude" / "settings.json")
    for path in project_files:
        value = _default_mode(path)
        if value is None:
            continue
        if value == "auto":
            return BUILT_IN_DEFAULT, False
        if value == "bypassPermissions":
            return MANUAL, False
        if value in _MODES:
            return _MODES[value], False
        _LOG.warning("Geçersiz permissions.defaultMode yok sayıldı: %s", path)
    value = _default_mode(home / ".claude" / "settings.json")
    if value in _MODES:
        return _MODES[value], True
    return None, False


def resolve_start_mode(
    root: Path,
    *,
    flag: str = "",
    legacy: str = "",
    auto_available: bool = True,
    home: Path | None = None,
    is_root: Callable[[], bool] | None = None,
) -> StartMode:
    """Bayrak > `permissions.defaultMode` > eski `runtime.approval_mode` > `auto`."""
    if flag.strip():
        mode = parse_mode(flag)
    else:
        mode, _ = _from_settings(root, home or Path.home())
        if mode is None:
            legacy_mode = _MODES.get(legacy.strip(), BUILT_IN_DEFAULT)
            if legacy_mode == "bypass":
                # Eski davranış (#370): YAML'daki bypass döngüye eklenir, oturum auto açılır.
                return _checked(StartMode(BUILT_IN_DEFAULT, bypass_available=True), auto_available)
            mode = legacy_mode
    if mode == "bypass":
        running_as_root = is_root() if is_root is not None else _is_root()
        if running_as_root:
            return StartMode(
                MANUAL, note="Bypass kipi root olarak reddedildi; oturum Manual kipte açıldı."
            )
        return StartMode("bypass", bypass_available=True)
    return _checked(StartMode(mode), auto_available)


def _checked(start: StartMode, auto_available: bool) -> StartMode:
    if start.mode == "auto" and not auto_available:
        return StartMode(MANUAL, bypass_available=start.bypass_available)
    return start


def auto_available(config: object) -> bool:
    """Otomatik kip bu yapılandırmada kullanılabilir mi (`disableAutoMode`, model listesi)?"""
    settings = getattr(config, "agent_launch", None)
    if settings is None:
        return True
    supported = getattr(settings, "auto_supported_models", ())
    model = getattr(getattr(config, "agent", None), "model", "")
    return not getattr(settings, "disable_auto_mode", False) and (
        not supported or model in supported
    )


def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return bool(geteuid is not None and geteuid() == 0)
