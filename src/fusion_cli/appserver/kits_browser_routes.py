"""Kits'in Fusion Chrome eklentisi isteği (`chrome.kit_komut`): dar eylem kümesi, yalnız metin.

Kit (iframe) → Fusion hostu (`kitsBrowserHost.ts`, kullanıcı onayı) → bu RPC → oturumun
Chrome köprüsü. Eklentinin native hostu Kit sürecine AÇILMAZ; yetki her zaman Fusion
uygulamasındaki kullanıcı onayında kalır. Eylem adları Kits'teki `fusion_browser` aracıyla
aynıdır; bilinmeyen eylem ve ekran görüntüsü reddedilir (görsel taşınmaz, sır sızmaz).

Ölçüldü (31 Ekim): Kit'in kullanıcının Chrome'una hiçbir yolu yoktu (P-063).
Ölçüldü (31 Ekim, inceleme): onay penceresi click/type/key hedefini göstermiyordu;
`runtime.disabled_tools` bu RPC'yi kapatmıyordu; sırlar kesmeden sonra gizleniyordu.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from typing import Any

from ..core.redaction import redact
from ..core.tools import ChromeControl
from ..tools.chrome import click_is_risky, key_is_risky, key_needs_focus_lookup
from ..tools.web import browser_block_reason

KITS_BROWSER_ROUTE = "chrome.kit_komut"
#: Onay penceresi için hedef tarifi: öğe adı ve riskli mi (`describe`/`describe_key`).
KITS_BROWSER_DESCRIBE_ROUTE = "chrome.kit_tarif"
KITS_BROWSER_ROUTES = frozenset({KITS_BROWSER_ROUTE, KITS_BROWSER_DESCRIBE_ROUTE})
#: Kit'in Kits'te gördüğü araç adı; `runtime.disabled_tools` içine yazılınca yol kapanır.
KIT_BROWSER_TOOL = "fusion_browser"
#: Kit eylemi → aynı işi yapan Fusion aracı. Kullanıcı o aracı kapattıysa Kit de yapamaz;
#: kapatma tek yerden (`runtime.disabled_tools`) ve iki yüzeyde aynı anlama gelir.
ACTION_TOOLS: Mapping[str, str] = {
    "read": "chrome_page",
    "find": "chrome_action",
    "text": "chrome_action",
    "tabs": "chrome_action",
    "scroll": "chrome_action",
    "navigate": "chrome_navigate",
    "click": "chrome_click",
    "type": "chrome_type",
    "key": "chrome_action",
}
#: Onay penceresindeki öğe adının üst sınırı.
MAX_TARGET_CHARS = 120
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


def disabled_reason(action: object, disabled: Collection[str]) -> str | None:
    """Eylem `runtime.disabled_tools` yüzünden kapalıysa Türkçe neden; değilse `None`."""
    if KIT_BROWSER_TOOL in disabled:
        return (
            f"Kit'lerin Chrome erişimi kapalı (runtime.disabled_tools içinde {KIT_BROWSER_TOOL})."
        )
    tool = ACTION_TOOLS.get(action) if isinstance(action, str) else None
    if tool is not None and tool in disabled:
        return f"Bu eylem kapalı: {tool} aracı runtime.disabled_tools ile devre dışı."
    return None


def _clip(text: str, limit: int) -> str:
    """Önce gizle, sonra kes: sınırda yarım kalan anahtar desene uymaz ve sızardı."""
    return redact(text)[:limit]


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


def _gate(
    data: Mapping[str, object], chrome: ChromeControl | None, disabled: Collection[str]
) -> tuple[str, dict[str, Any]] | dict[str, Any]:
    """Komutu kur ve kapıları uygula; geçemezse hazır yanıt döndür."""
    command = build_command(data)
    if isinstance(command, str):
        return {"ok": False, "status": "failed", "text": command}
    reason = disabled_reason(data.get("action"), disabled)
    if reason is not None:
        return {"ok": False, "status": "denied", "text": reason}
    if chrome is None:
        return {
            "ok": False,
            "status": "unavailable",
            "text": "Chrome köprüsü bu oturumda yok.",
        }
    return command


async def dispatch_kits_browser(
    data: Mapping[str, object],
    chrome: ChromeControl | None,
    *,
    disabled: Collection[str] = (),
) -> dict[str, Any]:
    """Komutu köprüye ilet; sonucu yalnız metin ve sırları gizlenmiş hâlde döndür."""
    gated = _gate(data, chrome, disabled)
    if isinstance(gated, dict):
        return gated
    assert chrome is not None
    operation, args = gated
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
        return {"ok": False, "status": "unavailable", "text": _clip(str(error), MAX_TEXT_CHARS)}
    except (ValueError, RuntimeError, OSError) as error:
        return {
            "ok": False,
            "status": "failed",
            "text": f"Chrome köprüsü hatası: {type(error).__name__}",
        }
    if not result.get("ok"):
        # Eklenti hata metnine sayfadan okunan öğe adı girebilir; o da gizlenir.
        hata = str(result.get("hata") or "Chrome komutu başarısız.")
        return {"ok": False, "status": "failed", "text": _clip(hata, MAX_TEXT_CHARS)}
    veri = result.get("veri", {})
    if isinstance(veri, dict):
        # Ekran görüntüsü ve benzeri ikili alanlar Kits'e taşınmaz.
        veri = {k: v for k, v in veri.items() if k not in {"image", "screenshot", "data"}}
    text = json.dumps(veri, ensure_ascii=False)
    return {"ok": True, "status": "ok", "text": _clip(text, MAX_TEXT_CHARS)}


def _element_name(result: dict[str, Any] | None) -> str:
    """`describe` sonucundan onay penceresine yazılacak ad; okunamadıysa boş."""
    veri = result.get("veri") if result is not None and result.get("ok") else None
    if not isinstance(veri, dict):
        return ""
    name = veri.get("name")
    if isinstance(name, str) and name.strip():
        return _clip(name.strip(), MAX_TARGET_CHARS)
    kind = str(veri.get("role") or veri.get("tag") or veri.get("type") or "")[:40]
    return f"adı okunamayan {kind}".strip() if kind else ""


async def _safe_describe(
    chrome: ChromeControl, operation: str, args: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        return await chrome.invoke(operation, args)
    except (TimeoutError, ConnectionError, ValueError, RuntimeError, OSError):
        return None


async def describe_kits_browser(
    data: Mapping[str, object],
    chrome: ChromeControl | None,
    *,
    disabled: Collection[str] = (),
) -> dict[str, Any]:
    """Etkileşim eyleminin hedefini onay penceresi için tarif et: `{hedef, riskli}`.

    Fusion'ın kendi Chrome araçlarıyla aynı sınıflandırma (`tools/chrome.py`): gönder/sil/
    satın al düğmesi, mesaj kutusunda Enter ve alan dışında Delete risklidir. Öğe adı
    okunamazsa riskli sayılır; kullanıcı "e12"ye değil, ne olduğunu bilmediği bir şeye
    onay verdiğini görür. Hedef adı sayfadan gelir: sırları gizlenir, kısaltılır.
    """
    gated = _gate(data, chrome, disabled)
    if isinstance(gated, dict):
        return gated
    assert chrome is not None
    operation, args = gated
    hedef = ""
    riskli = False
    if operation == "click":
        result = await _safe_describe(chrome, "describe", {"ref": args["ref"]})
        hedef = _element_name(result)
        riskli = True if result is None else click_is_risky(result)
    elif operation == "type":
        hedef = _element_name(await _safe_describe(chrome, "describe", {"ref": args["ref"]}))
    elif operation == "key":
        key = str(args.get("key") or "Enter")
        if key_needs_focus_lookup(key):
            focus = {"ref": args["ref"]} if "ref" in args else {}
            result = await _safe_describe(chrome, "describe_key", focus)
            veri = result.get("veri") if result is not None and result.get("ok") else None
            hedef = _element_name(result)
            riskli = key_is_risky(key, veri if isinstance(veri, dict) else None)
    elif operation == "navigate":
        hedef = str(args["url"])[:MAX_TARGET_CHARS]
    return {"ok": True, "status": "ok", "hedef": hedef, "riskli": riskli}
