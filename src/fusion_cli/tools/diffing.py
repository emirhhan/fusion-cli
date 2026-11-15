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

#: Bu satır sayısının üstünde `difflib` çağrılmaz (ikinci derece yavaşlar; minify JS, günlükler).
MAX_DIFF_LINES = 20_000


def _large_summary(old_lines: list[str], new_lines: list[str], path: str) -> str:
    """Ortak baş/son satırları budayıp değişen bölgenin boyutunu söyleyen tek satır."""
    start = 0
    limit = min(len(old_lines), len(new_lines))
    while start < limit and old_lines[start] == new_lines[start]:
        start += 1
    end_old, end_new = len(old_lines), len(new_lines)
    while end_old > start and end_new > start and old_lines[end_old - 1] == new_lines[end_new - 1]:
        end_old -= 1
        end_new -= 1
    return (
        f"{path}: dosya çok büyük, ayrıntılı fark gösterilmedi. İlk değişen satır {start + 1}; "
        f"değişen bölge: -{end_old - start} / +{end_new - start} satır."
    )


def unified_diff(old: str, new: str, path: str) -> str:
    """İki metin arasındaki farkı standart unified diff biçiminde üret."""
    old_lines, new_lines = old.splitlines(), new.splitlines()
    if max(len(old_lines), len(new_lines)) > MAX_DIFF_LINES:
        return _large_summary(old_lines, new_lines, path)
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
