"""Sayfa hatası olmayan kaynak gürültüsü: favicon / ikon istekleri.

Ölçüldü (29 Ekim): tarayıcı her sayfada `/favicon.ico` ister; dosya yoksa konsola
"Failed to load resource: ... 404" yazar. Oyun ve önizleme sondaları bunu "konsol
hatası" sayıp çalışan sayfayı bozuk raporluyordu. Yalnız ikon adresleri ayrılır;
başka her kaynak (betik, görsel, stil) hâlâ gerçek hatadır.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: Tarayıcının kendiliğinden istediği ikon dosyalarının ad önekleri.
_ICON_PREFIXES = ("favicon", "apple-touch-icon")
_LOAD_FAILURE = "failed to load resource"


def is_favicon_url(url: str) -> bool:
    """Adresin son yol parçası bir tarayıcı ikonu mu (`/favicon.ico`, `/apple-touch-icon.png`)?"""
    name = urlparse(url).path.rsplit("/", 1)[-1].casefold()
    return name.startswith(_ICON_PREFIXES) and "." in name


def is_favicon_load_error(text: str, location_url: str) -> bool:
    """Konsolun "Failed to load resource" satırı ikon isteğinden mi geliyor?"""
    return text.casefold().startswith(_LOAD_FAILURE) and is_favicon_url(location_url)
