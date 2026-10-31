"""Görsel tema — renk ve simgelerin tek kaynağı.

Kod içine hex ya da Rich markup gömülmez. Renkler truecolor'dır; terminal
desteklemiyorsa Rich otomatik olarak 256 renge iner.
"""

from __future__ import annotations

import re

#: Terminal paletleri (P-070, `/theme`). `koyu` ürünün özgün paleti; `acik` açık zeminde
#: okunur tonlar; `ansi` terminalin kendi 16 rengi (kullanıcının terminal teması belirler);
#: `daltonizm` kırmızı-yeşil ayrımı yerine mavi/turuncu (Okabe-Ito) kullanır.
PALETTES: dict[str, dict[str, str]] = {
    "koyu": {
        "ACCENT": "#FF8C42",
        "ACCENT_ALT": "#D6409F",
        "DIM": "#6B7280",
        "OK": "#3FB950",
        "WARN": "#D29922",
        "ERROR": "#F85149",
        "INFO": "#58A6FF",
        "DIFF_ADD_BG": "#0E2A18",
        "DIFF_DEL_BG": "#2D1417",
    },
    "acik": {
        "ACCENT": "#C2410C",
        "ACCENT_ALT": "#A21CAF",
        "DIM": "#4B5563",
        "OK": "#1A7F37",
        "WARN": "#9A6700",
        "ERROR": "#CF222E",
        "INFO": "#0969DA",
        "DIFF_ADD_BG": "#DAFBE1",
        "DIFF_DEL_BG": "#FFEBE9",
    },
    "ansi": {
        "ACCENT": "yellow",
        "ACCENT_ALT": "magenta",
        "DIM": "#808080",
        "OK": "green",
        "WARN": "yellow",
        "ERROR": "red",
        "INFO": "blue",
        "DIFF_ADD_BG": "#003300",
        "DIFF_DEL_BG": "#330000",
    },
    "daltonizm": {
        "ACCENT": "#CC79A7",
        "ACCENT_ALT": "#0072B2",
        "DIM": "#6B7280",
        "OK": "#1F77B4",
        "WARN": "#E69F00",
        "ERROR": "#D55E00",
        "INFO": "#56B4E9",
        "DIFF_ADD_BG": "#0B2238",
        "DIFF_DEL_BG": "#3A1E00",
    },
}
DEFAULT_THEME = "koyu"
THEME_NAMES: tuple[str, ...] = tuple(PALETTES)
#: Etkin palet adı; `apply_palette` günceller.
CURRENT_THEME = DEFAULT_THEME

ACCENT = "#FF8C42"
ACCENT_ALT = "#D6409F"
DIM = "#6B7280"
OK = "#3FB950"
WARN = "#D29922"
ERROR = "#F85149"
INFO = "#58A6FF"

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def apply_palette(name: str) -> str:
    """Modül sabitlerini seçilen palete çevir; etkin adı döndür.

    Tüm yüzeyler renkleri çağrı anında `theme.X` ile okur; bu yüzden modül düzeyinde
    yeniden bağlamak (tek yerde, oturum başında ya da `/theme` ile) yeterlidir. Tanınmayan
    ad `ValueError` verir — sessizce koyuya düşmek kullanıcıyı yanıltır.
    """
    global CURRENT_THEME, ACCENT, ACCENT_ALT, DIM, OK, WARN, ERROR, INFO
    global DIFF_ADD, DIFF_DEL, DIFF_ADD_BG, DIFF_DEL_BG, DIFF_CONTEXT
    palette = PALETTES.get(name.strip().lower())
    if palette is None:
        raise ValueError(f"Bilinmeyen tema: {name}. Seçenekler: {', '.join(THEME_NAMES)}")
    CURRENT_THEME = name.strip().lower()
    ACCENT, ACCENT_ALT, DIM = palette["ACCENT"], palette["ACCENT_ALT"], palette["DIM"]
    OK, WARN, ERROR, INFO = palette["OK"], palette["WARN"], palette["ERROR"], palette["INFO"]
    DIFF_ADD, DIFF_DEL, DIFF_CONTEXT = OK, ERROR, DIM
    DIFF_ADD_BG, DIFF_DEL_BG = palette["DIFF_ADD_BG"], palette["DIFF_DEL_BG"]
    MODE_COLORS.update(
        {"auto": OK, "edits": WARN, "plan": WARN, "security": ERROR, "bypass": ERROR}
    )
    return CURRENT_THEME


def blend(start: str, end: str, ratio: float) -> str:
    """İki `#RRGGBB` rengi arasında doğrusal geçiş; `ratio` 0..1.

    Ürünün turuncu→pembe geçişini üreten TEK fonksiyon. İmza (`banner.gradient`)
    ve seçim ekranı (`picker.row_colors`) bunu paylaşır; ikinci bir geçiş formülü
    tanımlanırsa iki yer zamanla ayrışır ve aynı ürün iki farklı renk gösterir.
    Adlı (ANSI) renkte geçiş hesaplanamaz; başlangıç rengi döner.
    """
    if not (_HEX.match(start) and _HEX.match(end)):
        return start
    left, right = start.lstrip("#"), end.lstrip("#")
    channels = []
    for offset in (0, 2, 4):
        start_value = int(left[offset : offset + 2], 16)
        end_value = int(right[offset : offset + 2], 16)
        channels.append(round(start_value + (end_value - start_value) * ratio))
    return "#" + "".join(f"{value:02X}" for value in channels)


#: Onay modunun rengi (durum çubuğu, banner, TUI): riskli mod göze çarpsın. Üç yüzey eskiden
#: ayrı kopyalar tutuyordu ve ayrışmıştı (L1-24, L2-33).
MODE_COLORS = {
    "auto": OK,
    "edits": WARN,
    "plan": WARN,
    "security": ERROR,
    "bypass": ERROR,
}

ICON_OK = "✓"
ICON_ERROR = "✗"
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
