"""Yerleşik tarayıcıda dış site kuralları (#439): yönetici ayarlarının uygulandığı tek yer.

"Dış site": http(s) adresi olup loopback (localhost, 127.0.0.0/8, ::1, *.localhost) olmayan her
yer. Yerel dosya önizlemesi ve `about:`/`data:` sayfaları dış sayılmaz.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from urllib.parse import urlsplit

from ..config.browser_admin import BrowserAdmin, load_browser_admin

NAVIGATION_BLOCKED = (
    "yönetici ayarı (disableBrowserExternalNavigation) dış sitelere gezinmeyi kapatmış: {host}. "
    "Yalnız localhost geliştirme sunucuları ve yerel dosyalar açılır"
)
PAGE_TOOLS_BLOCKED = (
    "yönetici ayarı (browserExternalPageTools: false) ajanın dış sayfaları okumasını ve onlarda "
    "eylem yapmasını kapatmış: {host}. Kullanıcı sayfayı kendisi gezebilir"
)
AdminLoader = Callable[[], BrowserAdmin]


def external_host(url: object) -> str | None:
    """Dış sitenin ana bilgisayar adı; yerel ya da web dışı adreste `None`."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme not in ("http", "https") or not host:
        return None
    if host == "localhost" or host.endswith(".localhost"):
        return None
    try:
        if ipaddress.ip_address(host).is_loopback:
            return None
    except ValueError:
        pass
    return host


def navigation_blocked(url: object, loader: AdminLoader = load_browser_admin) -> str | None:
    host = external_host(url)
    if host is None or loader().external_navigation:
        return None
    return NAVIGATION_BLOCKED.format(host=host)


def page_tools_blocked(url: object, loader: AdminLoader = load_browser_admin) -> str | None:
    host = external_host(url)
    if host is None:
        return None
    admin = loader()
    if admin.external_page_tools and admin.external_navigation:
        return None
    return PAGE_TOOLS_BLOCKED.format(host=host)
