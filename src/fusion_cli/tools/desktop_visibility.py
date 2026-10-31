"""Reddedilen/engelli uygulamaların modele görünmemesi: pencere listeleri ve geri düşüş (P-007).

Claude Desktop'ta reddedilen uygulamaya "hiç dokunulmaz"; Fusion'da bu yalnız tam ekran +
ScreenCaptureKit yolundaydı. Ölçüldü (31 Ekim): `region=` yakalaması ve `screencapture` geri
düşüşü (macOS < 14, yardımcı derlenemedi) pencereyi olduğu gibi yakalıyor, `desktop_windows`
ile `desktop_background_windows` tüm başlıkları listeliyor, `desktop_accessibility` öndeki
uygulamanın ağacını hiç denetlemeden döndürüyordu.

Bu modül iki şey sağlar:

- `is_hidden_app`: uygulama (ad, varsa paket) ret listesinde ya da engelli kategoride mi
  (`desktop_policy.app_level`, `app_levels` ile açılan hariç). Liste çıktıları bununla süzülür.
- `visible_hidden_apps`: ekranda penceresi görünen engelli uygulamalar. Dışlama yapamayan
  yakalama (geri düşüş) bunlardan biri görünürken yapılmaz. Pencere sahipleri CoreGraphics'ten
  ctypes ile okunur (`kCGWindowOwnerName` izin istemez; yardımcıya gerek yoktur).
"""

from __future__ import annotations

import ctypes
import sys
import unicodedata
from collections.abc import Callable, Iterable

from ..core.desktop_settings import DesktopSettings
from .desktop_policy import app_level

_CORE_GRAPHICS = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
_CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
#: kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
_ON_SCREEN_OPTIONS = (1 << 0) | (1 << 4)
_UTF8 = 0x08000100
_SINT64 = 4
_NAME_BUFFER = 512

#: Ekrandaki normal pencerelerin sahip adları; okunamazsa None (sahte verilebilir).
OwnerReader = Callable[[], tuple[str, ...] | None]


def is_hidden_app(settings: DesktopSettings, app: str, bundle: str = "") -> bool:
    """Uygulama modele gösterilmez mi? (ret listesi, engelli kategori; Fusion dahil)."""
    if not (app or bundle):
        return False
    level, _category, _reason = app_level(settings, app, bundle)
    return level is None


def _is_fusion(app: str, bundle: str = "") -> bool:
    from .desktop_policy import category_for

    category = category_for(app, bundle)
    return category is not None and category.key == "fusion"


def visible_hidden_apps(
    settings: DesktopSettings, owners: Iterable[str] | None
) -> tuple[str, ...] | None:
    """Ekranda görünen engelli uygulamalar (Fusion hariç; o ayrı ayarla dışlanır).

    `owners` None ise (pencere listesi okunamadı) None döner: çağıran güvenli tarafta kalır.
    """
    if owners is None:
        return None
    found = {
        owner
        for owner in owners
        if owner and not _is_fusion(owner) and is_hidden_app(settings, owner)
    }
    return tuple(sorted(found, key=str.casefold))


def onscreen_owners() -> tuple[str, ...] | None:
    """Ekrandaki (katman 0) pencerelerin sahip uygulama adları; macOS dışında/hata → None."""
    if sys.platform != "darwin":
        return None
    try:
        graphics = ctypes.CDLL(_CORE_GRAPHICS)
        foundation = ctypes.CDLL(_CORE_FOUNDATION)
        return _read_owners(graphics, foundation)
    except (OSError, AttributeError, ValueError):
        return None


def _clean(name: str) -> str:
    """Biçim karakterlerini at: ölçüldü (31 Ekim) WhatsApp sahibi '\u200eWhatsApp' geliyor."""
    return "".join(char for char in name if unicodedata.category(char) != "Cf").strip()


def _bind(graphics: ctypes.CDLL, foundation: ctypes.CDLL) -> None:
    graphics.CGWindowListCopyWindowInfo.restype = ctypes.c_void_p
    graphics.CGWindowListCopyWindowInfo.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    foundation.CFArrayGetCount.restype = ctypes.c_long
    foundation.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    foundation.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    foundation.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    foundation.CFDictionaryGetValue.restype = ctypes.c_void_p
    foundation.CFDictionaryGetValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    foundation.CFStringCreateWithCString.restype = ctypes.c_void_p
    foundation.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    foundation.CFStringGetCString.restype = ctypes.c_bool
    foundation.CFStringGetCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_uint32,
    ]
    foundation.CFNumberGetValue.restype = ctypes.c_bool
    foundation.CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    foundation.CFRelease.argtypes = [ctypes.c_void_p]


def _read_owners(graphics: ctypes.CDLL, foundation: ctypes.CDLL) -> tuple[str, ...] | None:
    _bind(graphics, foundation)
    rows = graphics.CGWindowListCopyWindowInfo(_ON_SCREEN_OPTIONS, 0)
    if not rows:
        return None
    name_key = foundation.CFStringCreateWithCString(None, b"kCGWindowOwnerName", _UTF8)
    layer_key = foundation.CFStringCreateWithCString(None, b"kCGWindowLayer", _UTF8)
    owners: list[str] = []
    try:
        for index in range(foundation.CFArrayGetCount(rows)):
            row = foundation.CFArrayGetValueAtIndex(rows, index)
            layer = ctypes.c_int64(-1)
            number = foundation.CFDictionaryGetValue(row, layer_key)
            if not number or not foundation.CFNumberGetValue(number, _SINT64, ctypes.byref(layer)):
                continue
            if layer.value != 0:
                continue
            name = foundation.CFDictionaryGetValue(row, name_key)
            buffer = ctypes.create_string_buffer(_NAME_BUFFER)
            if name and foundation.CFStringGetCString(name, buffer, _NAME_BUFFER, _UTF8):
                owners.append(_clean(buffer.value.decode("utf-8", "replace")))
    finally:
        for handle in (name_key, layer_key, rows):
            if handle:
                foundation.CFRelease(handle)
    return tuple(owners)
