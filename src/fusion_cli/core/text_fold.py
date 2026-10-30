"""Türkçe büyük/küçük harfe duyarlı küçültme (yalnız stdlib).

Ölçüldü (30 Ekim, A1-27/A2-12): `"İNCELE".lower()` -> `"i̇ncele"` (i + birleşik nokta
U+0307). Sınıflayıcıların `[^0-9a-zçğıöşü]+` ayırıcısı o noktayı ayraç sayar, sözcük
"i" ve "ncele"ye bölünür ve anahtar kelime hiç eşleşmez. Burada `İ` önce `i`ye çevrilir.
`I` bilerek `i` kalır (İngilizce sözcükler `Import`/`ISSUE` için `ı` yanlış olurdu).
"""

from __future__ import annotations

_COMBINING_DOT = "̇"


def fold_tr(text: str) -> str:
    """Anahtar kelime eşleşmesi için küçült; birleşik noktayı bırakmaz."""
    return text.replace("İ", "i").lower().replace(_COMBINING_DOT, "")
