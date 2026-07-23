"""Karşılama ekranı ve durum satırı.

Tasarım kararları:

- **Ekran temizlenir.** `fusion` çalıştığında terminal geçmişi temizlenir; oturum
  temiz bir sayfada başlar.
- **Yatay düzen.** Solda ürün imzası, sağda kullanıcının ihtiyaç duyduğu iki bilgi:
  bir ipucu ve projenin ne olduğu. Dikey yığmak ekranın yarısını yiyordu.
- **Tam genişlik.** Kutu terminale yayılır; sabit genişlik geniş ekranda ortada
  asılı kalıyordu.
- **Giriş alanı en altta.** Karşılamadan sonra ekranın altına kadar boşluk
  bırakılır; yazma alanı durum çubuğunun hemen üstünde, alışılmış yerinde durur.
- **Dar terminalde küçülür.** Büyük imza sığmıyorsa tek satırlık sürümüne iner;
  hiçbir genişlikte taşma olmaz.

Renk ve simge değerleri `theme` modülünden gelir; buraya hex gömülmez.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.box import ROUNDED
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from . import messages, theme

#: Büyük imzanın çizim genişliği (en uzun satır).
LOGO_WIDTH = 47
#: Sağ sütuna okunabilir metin için gereken en az genişlik.
MIN_TEXT_WIDTH = 34
#: Bu genişliğin altında büyük imza sığmaz; tek satırlık sürüme inilir.
MIN_LOGO_WIDTH = LOGO_WIDTH + MIN_TEXT_WIDTH + 10
#: Giriş satırı + durum çubuğu için ekranın altında bırakılan yer.
BOTTOM_RESERVED_LINES = 2

_LOGO_LINES = (
    "███████╗██╗   ██╗███████╗██╗ ██████╗ ███╗   ██╗",
    "██╔════╝██║   ██║██╔════╝██║██╔═══██╗████╗  ██║",
    "█████╗  ██║   ██║███████╗██║██║   ██║██╔██╗ ██║",
    "██╔══╝  ██║   ██║╚════██║██║██║   ██║██║╚██╗██║",
    "██║     ╚██████╔╝███████║██║╚██████╔╝██║ ╚████║",
    "╚═╝      ╚═════╝ ╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝",
)


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Karşılama ekranında gösterilecek oturum bilgileri."""

    version: str
    engine: str
    approval: str
    model: str
    working_dir: str
    #: Bellek açıksa ders sayısı, kapalıysa None.
    lesson_count: int | None


def gradient(text: str, start: str = theme.ACCENT, end: str = theme.ACCENT_ALT) -> Text:
    """Metni karakter karakter iki renk arasında geçişli boya."""
    rendered = Text()
    visible = [char for char in text if char != "\n"]
    total = len(visible)
    index = 0
    for char in text:
        if char == "\n":
            rendered.append("\n")
            continue
        ratio = 0.0 if total <= 1 else index / (total - 1)
        rendered.append(char, style=_blend(start, end, ratio))
        index += 1
    return rendered


def print_welcome(console: Console, info: SessionInfo, *, clear: bool = True) -> None:
    """Ekranı temizle, karşılamayı bas ve girişi ekranın altına indir."""
    if clear:
        console.clear()

    blocks: list[RenderableType] = [
        Text(),
        _welcome_panel(info, console.width),
        _facts_line(info),
    ]
    for block in blocks:
        console.print(block)

    _pad_to_bottom(console, blocks)


def print_status(
    console: Console, *, engine: str, approval: str, task_type: str, model: str
) -> None:
    """Ayar değişikliğinden sonra basılan tek satırlık sönük özet."""
    line = Text("  ")
    fields = (
        (engine, theme.ACCENT),
        (approval, mode_color(approval)),
        (task_type, theme.ACCENT_ALT),
        (model, theme.DIM),
    )
    for index, (value, color) in enumerate(fields):
        if index:
            line.append(" · ", style=theme.DIM)
        line.append(value, style=color)
    console.print(line)


def mode_color(mode: str) -> str:
    """Onay modunun rengi — riskli mod göze çarpsın."""
    return {"auto": theme.OK, "plan": theme.WARN, "security": theme.ERROR}.get(mode, theme.DIM)


def pick_tip(seed: str) -> str:
    """Gösterilecek ipucunu seç.

    Seçim çalışma dizinine göre KARARLIDIR: aynı projede hep aynı ipucu görünür
    (ekran her açılışta değişip dikkat dağıtmaz), farklı projede farklı ipucu
    gelir. Rastgelelik yok; bu yüzden test edilebilir.
    """
    tips = messages.WELCOME_TIPS
    return tips[sum(seed.encode("utf-8")) % len(tips)]


# --------------------------------------------------------------------------- #


def _welcome_panel(info: SessionInfo, width: int) -> Panel:
    """Tam genişlikte karşılama kutusu. Genişlik verilmez: terminale yayılır."""
    return Panel(
        _layout(info, width),
        box=ROUNDED,
        border_style=theme.DIM,
        title=Text(f" {messages.APP_NAME} {info.version} ", style=theme.ACCENT),
        title_align="left",
        padding=(1, 2),
    )


def _layout(info: SessionInfo, width: int) -> RenderableType:
    """Solda imza, sağda ipucu ve tanıtım.

    Dar terminalde büyük imza sağ sütuna okunabilir yer bırakmaz; orada tek
    satırlık imzaya inilir ve bölümler alt alta dizilir.
    """
    if width < MIN_LOGO_WIDTH:
        return Group(_wordmark(), Text(), _sidebar(info))

    columns = Table.grid(padding=(0, 4))
    columns.add_column(width=LOGO_WIDTH)
    columns.add_column(overflow="fold")
    columns.add_row(_logo(), _sidebar(info))
    return columns


def _logo() -> Text:
    """Gradyanlı büyük imza."""
    return gradient("\n".join(_LOGO_LINES))


def _wordmark() -> Text:
    """Dar terminalde kullanılan tek satırlık imza."""
    mark = Text("✦ ", style=theme.ACCENT)
    mark.append_text(gradient("FUSION"))
    return mark


def _sidebar(info: SessionInfo) -> Group:
    """Sağ sütun: üstte ipucu, altta projenin ne olduğu."""
    return Group(
        _section(messages.WELCOME_TIP_TITLE, pick_tip(info.working_dir)),
        Rule(style=theme.DIM),
        _section(messages.WELCOME_ABOUT_TITLE, messages.WELCOME_ABOUT_TEXT),
    )


def _section(title: str, body: str) -> Group:
    return Group(Text(title, style=f"bold {theme.ACCENT}"), Text(body, style=theme.DIM))


def _facts_line(info: SessionInfo) -> Text:
    """Oturum bilgileri — kutunun altında tek, yatay satır."""
    line = Text("  ")
    fields = (
        (messages.WELCOME_FIELD_ENGINE, info.engine, theme.ACCENT),
        (messages.WELCOME_FIELD_APPROVAL, info.approval, mode_color(info.approval)),
        (messages.WELCOME_FIELD_MODEL, info.model, theme.INFO),
        (messages.WELCOME_FIELD_DIR, info.working_dir, theme.DIM),
        (messages.WELCOME_FIELD_MEMORY, _memory_text(info.lesson_count), theme.OK),
    )
    for index, (label, value, color) in enumerate(fields):
        if index:
            line.append("  ·  ", style=theme.DIM)
        line.append(f"{label} ", style=theme.DIM)
        line.append(value, style=color)
    return line


def _memory_text(lesson_count: int | None) -> str:
    if lesson_count is None:
        return messages.WELCOME_MEMORY_OFF
    return messages.WELCOME_MEMORY_ON.format(count=lesson_count)


def _pad_to_bottom(console: Console, blocks: list[RenderableType]) -> None:
    """Giriş satırı ekranın altına insin diye boşluk bırak.

    Yalnızca gerçek terminalde yapılır: boru hattında ya da testte ekran
    yüksekliği anlamsızdır ve çıktı boş satırlarla kirlenir.
    """
    if not console.is_terminal:
        return
    used = sum(len(console.render_lines(block, console.options, pad=False)) for block in blocks)
    remaining = console.size.height - used - BOTTOM_RESERVED_LINES
    if remaining > 1:
        console.print("\n" * (remaining - 1), end="")


def _blend(start: str, end: str, ratio: float) -> str:
    """İki #RRGGBB rengi arasında doğrusal geçiş."""
    left, right = start.lstrip("#"), end.lstrip("#")
    channels = []
    for offset in (0, 2, 4):
        start_value = int(left[offset : offset + 2], 16)
        end_value = int(right[offset : offset + 2], 16)
        channels.append(round(start_value + (end_value - start_value) * ratio))
    return "#" + "".join(f"{value:02X}" for value in channels)
