"""Kits'in Fusion Chrome eklentisi isteği (`chrome.kit_komut`): dar eylem kümesi, yalnız metin.

Kit (iframe) → Fusion hostu (`kitsBrowserHost.ts`, kullanıcı onayı) → bu RPC → oturumun
Chrome köprüsü. Eklentinin native hostu Kit sürecine AÇILMAZ; yetki her zaman Fusion
uygulamasındaki kullanıcı onayında kalır. Eylem adları Kits'teki `fusion_browser` aracıyla
aynıdır; bilinmeyen eylem ve ekran görüntüsü reddedilir (görsel taşınmaz, sır sızmaz).

Ölçüldü (31 Ekim): Kit'in kullanıcının Chrome'una hiçbir yolu yoktu (P-063).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..core.redaction import redact
from ..core.tools import ChromeControl
from ..tools.web import browser_block_reason

KITS_BROWSER_ROUTE = "chrome.kit_komut"
#: Kits'e dönen metnin üst sınırı (sayfa metni 20 000 karaktere kadar gelebilir).
MAX_TEXT_CHARS = 20_000
MAX_REF_CHARS = 100
MAX_VALUE_CHARS = 16_000
MAX_URL_CHARS = 2048

#: Kit eylemi → eklenti komutu. Okuma eylemleri sayfayı değiştirmez; host bunları
#: oturum boyunca bir kez onaylatır, etkileşimi her seferinde sorar.
READ_ACTIONS = frozenset({"read", "find", "text", "tabs", "scroll"})
INTERACT_ACTIONS = frozenset({"navigate", "click", "type", "key"})
_SCROLL_DIRECTIONS = frozenset({"up", "down", "left", "right"})


def is_read_action(action: object) -> bool:
    return isinstance(action, str) and action in READ_ACTIONS


def _str(data: Mapping[str, object], key: str, limit: int) -> str | None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value if len(value) <= limit else None


def build_command(data: Mapping[str, object]) -> tuple[str, dict[str, Any]] | str:
    """İstek verisini eklenti komutuna çevir; geçersizse Türkçe hata metni döndür."""
    action = data.get("action")
    if not isinstance(action, str) or action not in READ_ACTIONS | INTERACT_ACTIONS:
        return "Bilinmeyen tarayıcı eylemi."
    ref = _str(data, "ref", MAX_REF_CHARS)
    value = _str(data, "value", MAX_VALUE_CHARS)
    if action == "read":
        return "snapshot", {}
    if action == "tabs":
        return "tabs", {}
    if action == "find":
        if value is None:
            return "find için 'value' alanına aranan metni yaz."
        return "find", {"query": value.strip()}
    if action == "text":
        page = int(value) if value is not None and value.strip().isdigit() else 1
        return "text_page", {"page": max(1, page)}
    if action == "scroll":
        direction, _, amount = (value or "down").partition(":")
        payload: dict[str, Any] = {
            "direction": direction if direction in _SCROLL_DIRECTIONS else "down"
        }
        if amount.strip().isdigit():
            payload["amount"] = int(amount)
        if ref is not None:
            payload["ref"] = ref
        return "scroll", payload
    if action == "navigate":
        url = _str(data, "url", MAX_URL_CHARS)
        if url is None:
            return "navigate için 'url' alanına adresi yaz."
        url = url.strip()
        if not url.startswith(("https://", "http://")):
            url = f"https://{url}"
        reason = browser_block_reason(url)
        if reason is not None:
            return f"Bu adrese erişilemez: {reason}"
        return "navigate", {"url": url}
    if action == "click":
        if ref is None:
            return "click için 'ref' gerekli (read/find çıktısındaki öğe kimliği)."
        return "click", {"ref": ref}
    if action == "type":
        if ref is None or value is None:
            return "type için 'ref' ve 'value' gerekli."
        return "type", {"ref": ref, "text": value}
    payload = {"key": value if value is not None else "Enter"}
    if ref is not None:
        payload["ref"] = ref
    return "key", payload


async def dispatch_kits_browser(
    data: Mapping[str, object], chrome: ChromeControl | None
) -> dict[str, Any]:
    """Komutu köprüye ilet; sonucu yalnız metin ve sırları gizlenmiş hâlde döndür."""
    command = build_command(data)
    if isinstance(command, str):
        return {"ok": False, "status": "failed", "text": command}
    if chrome is None:
        return {
            "ok": False,
            "status": "unavailable",
            "text": "Chrome köprüsü bu oturumda yok.",
        }
    operation, args = command
    try:
        result = await chrome.invoke(operation, args)
    except TimeoutError:
        return {
            "ok": False,
            "status": "failed",
            "text": "Chrome komutunun sonucu gelmedi; sayfada etkisi olmuş olabilir, "
            "tekrar etmeden önce sayfayı yeniden oku.",
        }
    except ConnectionError as error:
        return {"ok": False, "status": "unavailable", "text": str(error)}
    except (ValueError, RuntimeError, OSError) as error:
        return {
            "ok": False,
            "status": "failed",
            "text": f"Chrome köprüsü hatası: {type(error).__name__}",
        }
    if not result.get("ok"):
        return {
            "ok": False,
            "status": "failed",
            "text": str(result.get("hata") or "Chrome komutu başarısız."),
        }
    veri = result.get("veri", {})
    if isinstance(veri, dict):
        # Ekran görüntüsü ve benzeri ikili alanlar Kits'e taşınmaz.
        veri = {k: v for k, v in veri.items() if k not in {"image", "screenshot", "data"}}
    text = json.dumps(veri, ensure_ascii=False)
    return {"ok": True, "status": "ok", "text": redact(text[:MAX_TEXT_CHARS])}
