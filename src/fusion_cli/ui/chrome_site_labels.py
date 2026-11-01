"""Chrome site izni kartının seçenek adları (#435): CLI, TUI ve masaüstü aynı metni gösterir.

Claude in Chrome: "Allow this action" (bir kez), "Always allow actions on this site" (CLI'de
oturum boyu), "Decline". Ad Claude'unki, parantez içi Türkçe açıklama.
"""

from __future__ import annotations

from dataclasses import replace

from ..engines.agent.approval import ApprovalRequest
from .picker import Choice

SITE_ONCE = "Allow this action"
SITE_ONCE_DESC = "yalnız bu eylem"
SITE_SESSION = "Always allow actions on this site"
SITE_SESSION_SHORT = "{host} sitesinde bu oturum boyunca"
SITE_DENY = "Decline"
SITE_DENY_DESC = "bu eylem yapılmaz"
#: Düz terminal ipucu (`o` oturum iznidir).
SITE_SESSION_HINT = "o = Always allow actions on this site ({host}, bu oturum)"


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
    names = {
        "once": (SITE_ONCE, SITE_ONCE_DESC),
        "session": (SITE_SESSION, SITE_SESSION_SHORT.format(host=host)),
        "deny": (SITE_DENY, SITE_DENY_DESC),
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
    options = [{"deger": "once", "etiket": SITE_ONCE, "aciklama": SITE_ONCE_DESC}]
    if request.can_remember:
        options.append(
            {
                "deger": "session",
                "etiket": SITE_SESSION,
                "aciklama": request.remembered_scope_description
                or SITE_SESSION_SHORT.format(host=host),
            }
        )
    options.append({"deger": "deny", "etiket": SITE_DENY, "aciklama": SITE_DENY_DESC})
    return options
