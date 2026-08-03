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
#: Karşılama kutusunun başındaki yıldız (Claude Code `✻`). Ürün imzasının yanında durur.
ICON_SPARKLE = "✻"
ICON_STATUS = "›"
ICON_PROMPT = "❯"
#: Gönderilen kullanıcı mesajının önündeki işaret (Claude Code `>`). Girdi istemindeki
#: `ICON_PROMPT`'tan ayrıdır: biri yazarken, biri gönderilmiş sözü yankılarken kullanılır.
ICON_USER = ">"

#: Claude Code dizilimi: asistan eylemi ve araç çağrısı aynı dolu madde işaretiyle
#: (`⏺`) başlar; durum bilgisini glyph değil rengi taşır. Cevap akışının önündeki
#: işaret de budur — böylece "asistan konuşuyor" ile "araç çalıştı" tek görsel dile
#: oturur.
ICON_BULLET = "⏺"
ICON_ANSWER = ICON_BULLET
#: Araç sonucunu çağrı satırına bağlayan L-bağlayıcı (Claude Code `⎿`). Sonuç ve
#: diff bu işaretle çağrının altına asılır.
ICON_RESULT = "⎿"

#: Diff renkleri — eklenen yeşil, silinen kırmızı (Claude Code diff dizilimi). Ön
#: plan `OK`/`ERROR` ile aynı tondadır; zeminler satırın tamamını hafifçe boyar ki
#: göz +/- işaretine bakmadan da değişikliği ayırt etsin.
DIFF_ADD = OK
DIFF_DEL = ERROR
DIFF_ADD_BG = "#0E2A18"
DIFF_DEL_BG = "#2D1417"
#: Diff satır numarası ve değişmeyen bağlam satırı için sönük ton.
DIFF_CONTEXT = DIM
