"""Geçici araç hataları: ağ kesintisi ve zaman aşımı yeniden denemeye değer.

Ölçüldü (7 Ekim 2026, dalga24): clone_site kaynak sitenin bir sayfasında 60 sn zaman
aşımına düştü (site birkaç saat sonra 0,5 sn'de açılıyordu). Tekrar kapısı aynı çağrıyı
"bunu zaten yaptın" diye engelledi; model kopyalamayı bırakıp siteyi elle yazdı.
"""

from __future__ import annotations

import re

#: Aynı çağrıya geçici hatadan sonra tanınan en fazla yeniden deneme.
MAX_TOOL_TRANSIENT_RETRIES = 2

_TRANSIENT = re.compile(
    r"TimeoutError|Timeout \d+ ?ms exceeded|timed? ?out|zaman aşımı|net::ERR_|"
    r"ECONNRESET|ECONNREFUSED|ETIMEDOUT|Connection (?:reset|refused|aborted)|"
    r"temporarily unavailable|Service Unavailable|\b50[234]\b",
    re.IGNORECASE,
)


def is_transient_failure(output: str) -> bool:
    """Araç çıktısı geçici bir ağ/zaman aşımı hatası mı?"""
    return _TRANSIENT.search(output[:2000]) is not None
