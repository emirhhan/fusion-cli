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
