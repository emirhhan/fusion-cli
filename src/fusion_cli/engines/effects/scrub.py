"""Git çıktısındaki ve remote adresindeki sırları temizleyen yardımcılar.

`https://kullanici:TOKEN@github.com/...` biçimli bir origin adresi diske (workflow
kaydı) ve kullanıcıya dönen sonuç metnine ham yazılmamalıdır (E1-03).
"""

from __future__ import annotations

import re

from ...core.redaction import redact

#: URL içindeki `kullanici[:parola]@` kısmı (şema sonrası, ilk `/`'a kadar).
_URL_USERINFO = re.compile(r"(?P<scheme>\b[a-z][a-z0-9+.-]*://)[^/\s@]+@", re.IGNORECASE)


def strip_url_userinfo(text: str) -> str:
    """Metindeki her URL'den `kullanici:parola@` kısmını çıkar (sunucu/yol kalır)."""

    return _URL_USERINFO.sub(r"\g<scheme>", text)


def scrub_output(text: str) -> str:
    """Kaydedilecek ya da gösterilecek git çıktısını sırlardan arındır."""

    return redact(strip_url_userinfo(text))
