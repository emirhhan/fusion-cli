"""Taslağa giren metnin maskelenmesi — sırlar çıkar, yollar göreli olur.

Taslaklar gerçek kullanıcı konuşmasından türer. Kaynak makineden çıkmasa bile
kullanıcı taslağı kümeye alıp paylaşabilir; bu yüzden metin daha yazılırken
temizlenir: sır/kişisel veri `redact`'tan geçer, proje kökü kırpılır, kullanıcı
ev dizini ve kullanıcı adı yollardan düşer.
"""

from __future__ import annotations

import re
from pathlib import Path

from fusion_cli.core.redaction import redact

#: Taslakta tutulacak bir metin alanının üst sınırı (karakter). Uzun yapıştırmalar
#: (log, kaynak kodu) hem sır taşıma riskini hem küme şişmesini büyütür.
MAKS_METIN = 1500
_KISALTMA = "…[kırpıldı]"
#: Başka kullanıcıların/bu kullanıcının ev dizinleri: `/Users/ad/…`, `/home/ad/…`, `C:\Users\ad\…`.
_EV_DIZINI = re.compile(r"(?:/Users/|/home/)[^/\s\"']+|[A-Za-z]:\\Users\\[^\\\s\"']+")


def maskele(metin: str, *, kok: Path, ev: Path | None = None) -> str:
    """Metni taslağa yazılabilir hâle getir.

    Sıra anlamlıdır: önce sır maskesi, sonra proje kökü (daha uzun yol önce, yoksa
    ev dizini köke ait yolu bozardı), en son genel ev dizini kalıpları.
    """

    temiz = redact(metin)
    for yol in _kok_adaylari(kok):
        temiz = temiz.replace(f"{yol}/", "").replace(yol, ".")
    if ev is not None:
        temiz = temiz.replace(str(ev), "~")
    temiz = _EV_DIZINI.sub("~", temiz)
    if len(temiz) > MAKS_METIN:
        temiz = temiz[: MAKS_METIN - len(_KISALTMA)] + _KISALTMA
    return temiz


def _kok_adaylari(kok: Path) -> tuple[str, ...]:
    """Kökün hem verildiği hem çözümlenmiş (symlink'siz) yazımı; uzun olan önce."""

    adaylar = {str(kok), str(kok.expanduser().resolve())}
    return tuple(sorted((aday for aday in adaylar if aday not in {"", "/"}), key=len, reverse=True))
