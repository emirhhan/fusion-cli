"""Chrome site izni katmanı (#435): engelli, finansal ve sıradan site ayrımı.

Claude in Chrome: yetişkin ve korsan içerik siteleri varsayılan engellidir; finansal sitelerde
izin istenir; diğer sitelerde ilk eylemde "Allow this action" / "Always allow actions on this
site" / "Decline" sorulur. Bu modül yalnız alan adını sınıflandırır; onay kararı
`engines/agent/chrome_site_approval` içindedir. Liste bilerek dardır: bilinen alan adları ve
alan adı parçası olarak geçen açık sözcükler (`essex.ac.uk` "sex" sayılmaz).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit


class SiteCategory(Enum):
    ADULT = "adult"
    PIRACY = "piracy"
    FINANCIAL = "financial"
    NORMAL = "normal"


@dataclass(frozen=True)
class ChromeSite:
    """Onay isteğinin hedef sitesi (kart "Chrome'da Fusion x.com sitesinde…" der)."""

    host: str
    category: SiteCategory
    #: Kartta gösterilecek eylem ("tıklamak", "yazmak").
    action: str = "işlem yapmak"

    @property
    def financial(self) -> bool:
        return self.category is SiteCategory.FINANCIAL


_ADULT_DOMAINS = frozenset(
    {
        "pornhub.com", "xvideos.com", "xnxx.com", "xhamster.com", "redtube.com",
        "youporn.com", "onlyfans.com", "chaturbate.com", "stripchat.com", "spankbang.com",
        "brazzers.com", "livejasmin.com", "fansly.com", "rule34.xxx", "e-hentai.org",
    }
)  # fmt: skip
_ADULT_TOKENS = frozenset({"porn", "porno", "xxx", "hentai", "nsfw", "camgirl", "sexcam"})
_PIRACY_DOMAINS = frozenset(
    {
        "thepiratebay.org", "1337x.to", "rarbg.to", "yts.mx", "fmovies.to", "123movies.to",
        "putlocker.vip", "kickasstorrents.to", "limetorrents.info", "nyaa.si", "torrentz2.eu",
        "libgen.is", "libgen.rs", "z-lib.org", "zlibrary.to", "sci-hub.se", "eztv.re",
        "torrentgalaxy.to", "fitgirl-repacks.site", "dytt8.net",
    }
)  # fmt: skip
_PIRACY_TOKENS = frozenset({"torrent", "torrents", "piratebay", "warez", "putlocker"})
_FINANCIAL_DOMAINS = frozenset(
    {
        "paypal.com", "stripe.com", "wise.com", "revolut.com", "chase.com",
        "bankofamerica.com", "wellsfargo.com", "citi.com", "capitalone.com", "hsbc.com",
        "barclays.co.uk", "coinbase.com", "binance.com", "kraken.com", "robinhood.com",
        "schwab.com", "fidelity.com", "vanguard.com", "etrade.com", "interactivebrokers.com",
        "americanexpress.com", "klarna.com", "venmo.com", "cash.app",
        "garantibbva.com.tr", "isbank.com.tr", "akbank.com", "yapikredi.com.tr",
        "ziraatbank.com.tr", "halkbank.com.tr", "vakifbank.com.tr", "qnb.com.tr",
        "denizbank.com", "enpara.com", "papara.com", "paytr.com", "iyzico.com",
        "btcturk.com", "paribu.com", "teb.com.tr", "kuveytturk.com.tr",
    }
)  # fmt: skip
_FINANCIAL_TOKENS = frozenset({"bank", "banking", "bankasi", "onlinebanking", "netbanking"})
_TOKEN_SPLIT = re.compile(r"[.\-]")


def host_of(url: object) -> str | None:
    """`https://www.x.com/a` → `x.com`; http(s) dışı ya da geçersizse `None`."""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _matches(host: str, domains: frozenset[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def classify(host: str) -> SiteCategory:
    host = host.lower().rstrip(".")
    tokens = set(_TOKEN_SPLIT.split(host))
    if _matches(host, _ADULT_DOMAINS) or tokens & _ADULT_TOKENS or host.endswith(".xxx"):
        return SiteCategory.ADULT
    if _matches(host, _PIRACY_DOMAINS) or tokens & _PIRACY_TOKENS:
        return SiteCategory.PIRACY
    if _matches(host, _FINANCIAL_DOMAINS) or tokens & _FINANCIAL_TOKENS:
        return SiteCategory.FINANCIAL
    return SiteCategory.NORMAL


def blocked_reason(site: ChromeSite) -> str | None:
    """Engelli sitenin modele dönen gerekçesi; engelli değilse `None`."""
    if site.category is SiteCategory.ADULT:
        return f"{site.host} yetişkin içerik sitesi; Chrome'da Fusion bu siteleri varsayılan engeller"
    if site.category is SiteCategory.PIRACY:
        return f"{site.host} korsan içerik sitesi; Chrome'da Fusion bu siteleri varsayılan engeller"
    return None


def site_of(url: object, action: str = "işlem yapmak") -> ChromeSite | None:
    host = host_of(url)
    return None if host is None else ChromeSite(host, classify(host), action)


def navigation_block_reason(url: str) -> str | None:
    """Gezinme hedefi engelli siteyse gerekçe (Claude: yetişkin ve korsan site engeli)."""
    site = site_of(url)
    return blocked_reason(site) if site is not None else None
