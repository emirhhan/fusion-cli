"""Türkçe-duyarlı küçültme (yalnız stdlib) — kalıp ve arama eşleştirmesi için.

Ölçüldü (30 Ekim, A1-27/A2-12/E1-12): `"İNCELE".lower()` -> `"i̇ncele"` (i + birleşik nokta
U+0307). Sınıflayıcıların `[^0-9a-zçğıöşü]+` ayırıcısı o noktayı ayraç sayar, sözcük
"i" ve "ncele"ye bölünür; `required_effect_for("DOSYAYI SİL")` hiçbir etki bulmuyordu.
Burada `İ` önce `i`ye çevrilir. `I` bilerek `i` kalır (kalıplar karışık dillidir:
`fix`, `index`, `Import`/`ISSUE` için `ı` yanlış olurdu); `ı` korunur.
"""

from __future__ import annotations

_COMBINING_DOT = "̇"


def fold_tr(text: str) -> str:
    """Anahtar kelime eşleşmesi için küçült; birleşik noktayı bırakmaz."""
    return text.replace("İ", "i").lower().replace(_COMBINING_DOT, "")


# İki dal aynı yardımcıyı farklı adla yazdı; ikisi de aynı işlevi gösterir.
lower_tr_aware = fold_tr
