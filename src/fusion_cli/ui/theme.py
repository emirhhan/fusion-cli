"""Görsel tema — renk ve simgelerin tek kaynağı.

Kod içine hex ya da Rich markup gömülmez. Renkler truecolor'dır; terminal
desteklemiyorsa Rich otomatik olarak 256 renge iner.
"""

from __future__ import annotations

ACCENT = "#FF8C42"
ACCENT_ALT = "#D6409F"
DIM = "#6B7280"
OK = "#3FB950"
WARN = "#D29922"
ERROR = "#F85149"
INFO = "#58A6FF"

#: Kullanıcı mesajı bandının zemini — koyu temada hafifçe ayrışır.
SURFACE = "#1B1F27"


def blend(start: str, end: str, ratio: float) -> str:
    """İki `#RRGGBB` rengi arasında doğrusal geçiş; `ratio` 0..1.

    Ürünün turuncu→pembe geçişini üreten TEK fonksiyon. İmza (`banner.gradient`)
    ve seçim ekranı (`picker.row_colors`) bunu paylaşır; ikinci bir geçiş formülü
    tanımlanırsa iki yer zamanla ayrışır ve aynı ürün iki farklı renk gösterir.
    """
    left, right = start.lstrip("#"), end.lstrip("#")
    channels = []
    for offset in (0, 2, 4):
        start_value = int(left[offset : offset + 2], 16)
        end_value = int(right[offset : offset + 2], 16)
        channels.append(round(start_value + (end_value - start_value) * ratio))
    return "#" + "".join(f"{value:02X}" for value in channels)


ICON_OK = "✓"
ICON_ERROR = "✗"
ICON_DENIED = "⊘"
ICON_DONE = "✦"
ICON_STATUS = "›"
ICON_PROMPT = "❯"
ICON_ANSWER = "●"
