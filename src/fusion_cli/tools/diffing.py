"""Metin farkı üretimi ve kırpılması — saf, dosya sistemine dokunmaz.

İki tüketicisi var: onay önizlemesi (`preview.py`, araç ÇALIŞMADAN önce) ve
düzenleme araçlarının modele dönen sonucu (`files.py`, araç çalıştıktan SONRA).
İkisi aynı biçimi ve aynı tavanı kullanır; ayrı yerlerde yazılsaydı kullanıcının
onayladığı diff ile modelin gördüğü diff sessizce ayrışırdı. `preview.py` zaten
`files.py`'yi import ettiği için ortak kod ikisinin de bağımlı olabileceği bu
modüldedir (import döngüsü olmaz).
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence

from ..core.constants import MAX_PREVIEW_LINES


def unified_diff(old: str, new: str, path: str) -> str:
    """İki metin arasındaki farkı standart unified diff biçiminde üret."""
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )


def clip_lines(lines: Sequence[str], limit: int = MAX_PREVIEW_LINES) -> list[str]:
    """Satırları tavana indir; kırpıldıysa kaç satırın gizlendiğini sona yaz.

    Sessiz kırpma "farkın tamamını gördüm" yanılgısı verir; not bunu önler.
    """
    if len(lines) <= limit:
        return list(lines)
    return [*lines[:limit], f"… (+{len(lines) - limit} satır)"]


def bounded_diff(old: str, new: str, path: str) -> str:
    """Tavanla sınırlanmış unified diff; fark yoksa boş metin."""
    return "\n".join(clip_lines(unified_diff(old, new, path).splitlines()))
