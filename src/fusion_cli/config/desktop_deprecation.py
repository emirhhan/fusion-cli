"""Kullanımdan kalkan `desktop:` anahtarları için tek seferlik uyarı (#424, #426).

Claude Desktop'ta uygulama kademeleri kategoriye göre sabittir ve uygulama onayı kapatılamaz.
Fusion'ın eski `control_level`, `category_defaults`, `app_levels` ve `app_consent` ayarları
kullanıcının dosyasında kalabilir: yükleme bozulmaz, değer yok sayılır, süreçte bir kez uyarılır.
"""

from __future__ import annotations

import logging

from ..core.desktop_settings import DEPRECATED_KEYS

_logger = logging.getLogger(__name__)
_WARNED: set[str] = set()

DEPRECATED_DESKTOP_WARNING = (
    "desktop.{key} kullanımdan kalktı ve yok sayılıyor: Claude Code'daki gibi uygulama "
    "kademeleri kategoriye göre sabit, uygulama onayı her zaman sorulur. Satırı silebilirsin."
)


def warn_deprecated_desktop_keys(raw: object) -> tuple[str, ...]:
    """Bölümde kullanımdan kalkan anahtar varsa ilk görüşte uyar; görülen anahtarları döndür."""
    if not isinstance(raw, dict):
        return ()
    found = tuple(key for key in DEPRECATED_KEYS if key in raw)
    for key in found:
        if key not in _WARNED:
            _WARNED.add(key)
            _logger.warning(DEPRECATED_DESKTOP_WARNING.format(key=key))
    return found


#: Okunup uygulanmayan eski `runtime:` ekran görüntüsü ayarları (#448).
DEPRECATED_RUNTIME_KEYS: tuple[str, ...] = (
    "desktop_screenshot_max_width",
    "desktop_exclude_fusion_window",
)
DEPRECATED_RUNTIME_WARNING = (
    "runtime.{key} kullanımdan kalktı ve yok sayılıyor: Claude Code'daki gibi ekran görüntüsü "
    "sabit boyuta küçültülür ve Fusion penceresi her zaman dışlanır. Satırı silebilirsin."
)


def warn_deprecated_runtime_keys(raw: object) -> tuple[str, ...]:
    """`runtime:` bölümündeki eski ekran görüntüsü ayarları için tek seferlik uyarı."""
    if not isinstance(raw, dict):
        return ()
    found = tuple(key for key in DEPRECATED_RUNTIME_KEYS if key in raw)
    for key in found:
        if f"runtime.{key}" not in _WARNED:
            _WARNED.add(f"runtime.{key}")
            _logger.warning(DEPRECATED_RUNTIME_WARNING.format(key=key))
    return found
