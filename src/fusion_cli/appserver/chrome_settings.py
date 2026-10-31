"""Masaüstü Ayarlar → Tarayıcı: eklentinin konsol/ağ izleme anahtarı ve kısayolları (P-042, P-073).

Eklenti bu ayarları kendi `chrome.storage.local` deposunda tutar; panel ve masaüstü aynı
depoyu değiştirir. Masaüstü köprü üzerinden eklentiye sorar (`monitor_get/set`,
`shortcuts`, `shortcut_set/delete`); eklenti bağlı değilse anlaşılır hata döner.
Ölçüldü (31 Ekim, bağımsız inceleme): bu iki ayar yalnız eklenti panelindeydi,
masaüstü yalnız anlatıyordu.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable
from typing import Any, Protocol

CHROME_SETTINGS_ROUTES = frozenset(
    {"chrome.izleme", "chrome.kisayollar", "chrome.kisayol_kaydet", "chrome.kisayol_sil"}
)
#: Kısayol adı: boşluksuz harf/rakam/_/-, en çok 40 karakter (eklenti `shortcuts.js` ile aynı).
SHORTCUT_NAME = re.compile(r"^[\w-]{1,40}$", re.UNICODE)
#: Görev metninin üst sınırı (paneldeki alanla aynı).
MAX_SHORTCUT_TEXT = 2000


class _Bridge(Protocol):
    def invoke(self, operation: str, args: dict[str, Any]) -> Awaitable[dict[str, Any]]: ...


async def dispatch_chrome_settings(
    bridge: _Bridge, name: str, data: dict[str, Any]
) -> dict[str, Any]:
    """`CHROME_SETTINGS_ROUTES` içindeki isteği eklentiye ilet; sonucu Türkçe alanlarla döndür."""
    try:
        if name == "chrome.izleme":
            return await _monitor(bridge, data)
        if name == "chrome.kisayollar":
            return _shortcut_list(await _call(bridge, "shortcuts", {}))
        if name == "chrome.kisayol_kaydet":
            parsed = _parse_shortcut(data)
            if isinstance(parsed, str):
                return {"ok": False, "metin": parsed}
            return _shortcut_list(await _call(bridge, "shortcut_set", parsed))
        if name == "chrome.kisayol_sil":
            ad = data.get("ad")
            if not isinstance(ad, str) or not ad.strip():
                return {"ok": False, "metin": "Silinecek kısayolun adı gerekli."}
            return _shortcut_list(await _call(bridge, "shortcut_delete", {"ad": ad.strip()}))
    except (ConnectionError, TimeoutError) as exc:
        return {"ok": False, "metin": str(exc)}
    except _ExtensionError as exc:
        return {"ok": False, "metin": str(exc)}
    return {"ok": False, "metin": f"Bilinmeyen Chrome ayarı: {name}"}


class _ExtensionError(RuntimeError):
    """Eklenti komutu `ok: false` döndürdü."""


async def _call(bridge: _Bridge, operation: str, args: dict[str, Any]) -> dict[str, Any]:
    result = await bridge.invoke(operation, args)
    if not result.get("ok"):
        raise _ExtensionError(str(result.get("hata") or "Eklenti komutu başarısız."))
    veri = result.get("veri")
    return veri if isinstance(veri, dict) else {}


async def _monitor(bridge: _Bridge, data: dict[str, Any]) -> dict[str, Any]:
    wanted = data.get("acik")
    if isinstance(wanted, bool):
        veri = await _call(bridge, "monitor_set", {"enabled": wanted})
    else:
        veri = await _call(bridge, "monitor_get", {})
    return {"ok": True, "acik": veri.get("enabled") is not False}


def _shortcut_list(veri: dict[str, Any]) -> dict[str, Any]:
    raw = veri.get("shortcuts")
    rows = [
        {"ad": str(item["ad"]), "metin": str(item["metin"])}
        for item in (raw if isinstance(raw, list) else [])
        if isinstance(item, dict) and item.get("ad") and item.get("metin")
    ]
    return {"ok": True, "kisayollar": rows}


def _parse_shortcut(data: dict[str, Any]) -> dict[str, str] | str:
    """Ad ve görev metnini denetle; hata metni ya da köprüye gidecek veri döner."""
    ad, metin = data.get("ad"), data.get("metin")
    if not isinstance(ad, str) or not isinstance(metin, str):
        return "Kısayol adı ve görev metni yazı olmalı."
    ad = ad.strip().lstrip("/")
    metin = metin.strip()
    if not ad:
        return "Kısayol adı gerekli (ör. ozet)."
    if SHORTCUT_NAME.match(ad) is None:
        return "Kısayol adı boşluksuz, en çok 40 karakter olmalı (ör. ozet)."
    if not metin:
        return "Kısayolun görev metnini yaz."
    if len(metin) > MAX_SHORTCUT_TEXT:
        return f"Görev metni en çok {MAX_SHORTCUT_TEXT} karakter olabilir."
    return {"ad": ad, "metin": metin}


__all__ = ["CHROME_SETTINGS_ROUTES", "dispatch_chrome_settings"]
