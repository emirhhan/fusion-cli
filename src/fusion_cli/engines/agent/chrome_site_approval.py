"""Chrome'da site izni (#435): ilk eylemde "Allow this action / Always allow / Decline".

Claude in Chrome: bir sitede ilk eylemde site izni istenir ("Claude in Chrome wants to …");
"Allow this action" yalnız o eylemi, "Always allow actions on this site" o siteyi (CLI'de oturum
boyu) izinli yapar, "Decline" reddeder. Auto kipte sınıflandırıcı onaylarsa site denetimi atlanır;
yetişkin ve korsan siteler engellidir; finansal sitelerde izin her kipte istenir.

Fusion'da karşılığı:

- Okumayan Chrome eylemi hedef sitenin oturum izni anahtarını (`chrome-site:<host>`) taşır.
  Manuel kipte ilk eylem sorulur; "bu sitede hep izin ver" denince o sitedeki sıradan eylemler
  oturum boyu sorulmaz (riskli eylem — gönder/sil/öde, parola alanı — yine her seferinde).
- Otomatik kip site sorusu sormaz: sıradan eylem Otomatik kipin kendi kuralıyla geçer.
- İzinleri atla kipi site sorusu sormaz; finansal site ise her kipte (bypass dahil) ilk eylemde
  sorulur ve oturumda hatırlanır.
- Yetişkin/korsan sitede eylem sorulmadan engellenir (gezinme de engelli: `tools/chrome`).
- Hedef site okunamazsa katman uygulanmaz; çağrı eski kurallarla sorulur (gevşeme yok).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ...core.tools import ToolArgs, ToolContext, ToolEffect
from ...tools.chrome_site_policy import ChromeSite, blocked_reason, site_of

if TYPE_CHECKING:
    from .approval import ApprovalRequest

SITE_KEY_PREFIX = "chrome-site:"
#: Kartın başlık satırı (Claude: "Claude in Chrome wants to …").
SITE_NOTE = "Chrome'da Fusion {host} sitesinde {action} istiyor."
FINANCIAL_NOTE = "Finansal site: izin her kipte (İzinleri atla dahil) istenir."
#: "Always allow actions on this site" seçeneğinin kapsam açıklaması.
SITE_SCOPE = (
    "Bu oturum boyunca yalnız {host} sitesinde; riskli eylemler (gönder, sil, öde, parola "
    "alanı) yine her seferinde sorulur. Başka site ayrıca sorulur."
)
_ACTIONS = {
    "chrome_click": "tıklamak",
    "chrome_type": "yazmak",
    "chrome_javascript": "betik çalıştırmak",
    "chrome_upload": "dosya yüklemek",
}
_ACTION_VERBS = {
    "key": "tuşa basmak",
    "select": "seçim yapmak",
    "check": "işaretlemek",
    "drag": "sürüklemek",
    "upload": "dosya yüklemek",
    "close": "sekmeyi kapatmak",
}


def site_key(host: str) -> str:
    return f"{SITE_KEY_PREFIX}{host}"


def is_site_consent(request: ApprovalRequest) -> bool:
    """Her kipte (bypass dahil) sorulan finansal site izni mi?"""
    site = getattr(request, "chrome_site", None)
    return isinstance(site, ChromeSite) and site.financial and request.consent_key is not None


def site_description(request: ApprovalRequest) -> str | None:
    site = getattr(request, "chrome_site", None)
    if not isinstance(site, ChromeSite) or request.consent_key is None:
        return None
    return SITE_SCOPE.format(host=site.host)


def _action(tool_name: str, args: ToolArgs) -> str:
    if tool_name == "chrome_action":
        return _ACTION_VERBS.get(str(args.get("action", "")), "işlem yapmak")
    return _ACTIONS.get(tool_name, "işlem yapmak")


async def _current_url(context: ToolContext) -> str | None:
    """Bağlı (yoksa etkin) sekmenin adresi; okunamazsa `None`."""
    chrome = context.chrome
    if chrome is None:
        return None
    status = getattr(chrome, "status", None)
    if callable(status) and not status().get("bagli"):
        # Onay adımı Chrome'u açtırmaz/kurdurmaz; bağlantı yokken katman uygulanmaz.
        return None
    try:
        result = await chrome.invoke("tabs", {})
    except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError):
        return None
    veri: Any = result.get("veri") if result.get("ok") else None
    tabs = veri.get("tabs") if isinstance(veri, dict) else None
    if not isinstance(tabs, list):
        return None
    rows = [tab for tab in tabs if isinstance(tab, dict)]
    chosen = next((t for t in rows if t.get("bound")), None) or next(
        (t for t in rows if t.get("active")), None
    )
    url = chosen.get("url") if chosen is not None else None
    return url if isinstance(url, str) else None


async def apply_site(
    request: ApprovalRequest, tool_name: str, args: ToolArgs, context: ToolContext
) -> ApprovalRequest:
    """İsteğe site iznini işle; okuma ve hedefi okunamayan çağrı olduğu gibi kalır."""
    if (
        not tool_name.startswith("chrome_")
        or tool_name in {"chrome_batch", "chrome_navigate"}
        or request.read_only
        or request.pre_denied is not None
        or context.chrome is None
    ):
        return request
    site = site_of(await _current_url(context), _action(tool_name, args))
    if site is None:
        return request
    blocked = blocked_reason(site)
    if blocked is not None:
        return replace(request, pre_denied=blocked, chrome_site=site)
    note = SITE_NOTE.format(host=site.host, action=site.action)
    if site.financial:
        note = f"{note} {FINANCIAL_NOTE}"
    existing = request.danger or request.note
    updates: dict[str, Any] = {
        "chrome_site": site,
        "consent_key": site_key(site.host),
        "note": f"{note} {existing}".strip() if existing and not request.danger else note,
    }
    if site.financial:
        # Otomatik kip de sorsun (risk dolu); ilk onaydan sonra oturumda hatırlanır.
        updates.update(risk=note, unattended_safe=False)
        if request.effect is ToolEffect.REMOTE_READ:
            updates["effect"] = ToolEffect.REMOTE_INTERACT
    return replace(request, **updates)
