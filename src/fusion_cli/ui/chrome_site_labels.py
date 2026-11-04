"""Site izni seçenekleri bütün yüzeylerde eylem, oturum ve kalıcı kapsamı ayırır.

Chrome site izni oturumluk, yerleşik Browser site izni kalıcıdır.
"""

from __future__ import annotations

from dataclasses import replace

from ..engines.agent.approval import ApprovalRequest
from .picker import Choice

SITE_ONCE = "Yalnız bu eyleme izin ver"
SITE_ONCE_DESC = "yalnız bu eylem"
SITE_SESSION = "Bu oturumda bu siteye izin ver"
SITE_SESSION_SHORT = "{host} sitesinde bu oturum boyunca"
SITE_DENY = "Reddet"
SITE_DENY_DESC = "bu eylem yapılmaz"
#: Yerleşik Browser bölmesi (#439): Allow once / Always allow / Deny.
BUILTIN_ONCE = "Yalnız bu kez izin ver"
BUILTIN_SESSION = "Bu siteye kalıcı izin ver"
BUILTIN_DENY = "Reddet"
#: Düz terminal ipucu (`o` oturum iznidir).
SITE_SESSION_HINT = "o = {host} sitesine bu oturum boyunca izin ver"


def site_host(request: ApprovalRequest) -> str | None:
    site = request.chrome_site
    if site is None or request.consent_key is None:
        return None
    return site.host


def relabel_choices(request: ApprovalRequest, choices: list[Choice]) -> list[Choice]:
    """TUI seçeneklerini site izni adlarıyla değiştir; site isteği değilse aynen döner."""
    host = site_host(request)
    if host is None:
        return choices
    once, session, deny = _labels(request)
    names = {
        "once": (once, SITE_ONCE_DESC),
        "session": (
            session,
            request.remembered_scope_description or SITE_SESSION_SHORT.format(host=host),
        ),
        "deny": (deny, SITE_DENY_DESC),
    }
    relabeled = []
    for choice in choices:
        name = names.get(choice.value)
        relabeled.append(
            replace(choice, label=name[0], description=name[1]) if name is not None else choice
        )
    return relabeled


def site_options(request: ApprovalRequest) -> list[dict[str, str]] | None:
    """Masaüstü kartı seçenekleri; site isteği değilse `None`."""
    host = site_host(request)
    if host is None:
        return None
    once, session, deny = _labels(request)
    options = [{"deger": "once", "etiket": once, "aciklama": SITE_ONCE_DESC}]
    if request.can_remember:
        options.append(
            {
                "deger": "session",
                "etiket": session,
                "aciklama": request.remembered_scope_description
                or SITE_SESSION_SHORT.format(host=host),
            }
        )
    options.append({"deger": "deny", "etiket": deny, "aciklama": SITE_DENY_DESC})
    return options


def _labels(request: ApprovalRequest) -> tuple[str, str, str]:
    site = request.chrome_site
    if site is not None and site.builtin:
        return BUILTIN_ONCE, BUILTIN_SESSION, BUILTIN_DENY
    return SITE_ONCE, SITE_SESSION, SITE_DENY


def site_session_hint(request: ApprovalRequest) -> str:
    """CLI kısayolu da yerleşik Browser kalıcılığını oturumluk diye sunmaz."""
    host = site_host(request)
    if host is None:
        return ""
    site = request.chrome_site
    if site is not None and site.builtin:
        return f"o = {host} sitesine kalıcı izin ver (yerleşik Browser)"
    return SITE_SESSION_HINT.format(host=host)
