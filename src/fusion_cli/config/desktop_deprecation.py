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


#: Yok sayılan eski ayar bir uygulamayı kısıtlıyordu: yetki genişledi, ayrıca söylenir.
WIDENED_DESKTOP_WARNING = (
    "DİKKAT: computer use yetkisi genişledi. Eski ayarın şunları kısıtlıyordu: {items}. Artık "
    "kategori kademesi geçerli (çoğu uygulamada tam kontrol). Bir uygulamayı tümüyle kapatmak "
    "için masaüstünde Ayarlar › Bu bilgisayar › ret listesi'ne ekle."
)
#: Kısıtlayıcı (tam kontrolden düşük) kademeler.
_RESTRICTIVE = frozenset({"observe", "click"})


def _restrictive_items(raw: dict[object, object]) -> list[str]:
    """Eski ayarlardaki tam kontrolden düşük kademeler (`control_level=click`, `Terminal=observe`)."""
    items: list[str] = []
    level = raw.get("control_level")
    if isinstance(level, str) and level.strip().lower() in _RESTRICTIVE:
        items.append(f"control_level={level.strip().lower()}")
    for key in ("app_levels", "category_defaults"):
        for name, value in _entries(raw.get(key)):
            if value in _RESTRICTIVE:
                items.append(f"{name}={value}")
    return items


def _entries(values: object) -> list[tuple[str, str]]:
    """`{ad: kademe}` ya da `['Ad=kademe']` biçimini (ad, küçük harfli kademe) çiftlerine çevir."""
    if isinstance(values, dict):
        pairs = [(str(name), str(value)) for name, value in values.items()]
    elif isinstance(values, list):
        pairs = [item.partition("=")[::2] for item in values if isinstance(item, str)]
    else:
        pairs = []
    return [(name.strip(), value.strip().lower()) for name, value in pairs]


def warn_deprecated_desktop_keys(raw: object) -> tuple[str, ...]:
    """Bölümde kullanımdan kalkan anahtar varsa ilk görüşte uyar; görülen anahtarları döndür."""
    if not isinstance(raw, dict):
        return ()
    found = tuple(key for key in DEPRECATED_KEYS if key in raw)
    for key in found:
        if key not in _WARNED:
            _WARNED.add(key)
            _logger.warning(DEPRECATED_DESKTOP_WARNING.format(key=key))
    restrictive = _restrictive_items(raw)
    if restrictive and "widened" not in _WARNED:
        _WARNED.add("widened")
        _logger.warning(WIDENED_DESKTOP_WARNING.format(items=", ".join(restrictive)))
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
