"""Karşılama ekranı ve durum satırı.

Tasarım kararları:

- **Ekran temizlenir.** `fusion` çalıştığında terminal geçmişi temizlenir ve
  oturum temiz bir sayfada başlar; önceki komutların artıkları karışmaz.
- **İki sütunlu karşılama.** Solda "neredeyim, neyle çalışıyorum", sağda
  "ne yapabilirim". Tek blok metin okunmaz; iki sütun göz taramasını kolaylaştırır.
- **Kutu genişliği terminale uyar.** Sabit genişlik dar terminalde taşar, geniş
  terminalde ortada asılı kalır.

Renk ve simge değerleri `theme` modülünden gelir; buraya hex gömülmez.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.box import ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import messages, theme

#: Karşılama kutusunun en fazla genişliği. Çok geniş terminalde satırlar uzayıp
#: okunmaz hale gelmesin.
MAX_WELCOME_WIDTH = 100
#: Sol sütunun genişliği; sağ sütun kalanı alır.
LEFT_COLUMN_WIDTH = 30
#: Bu genişliğin altında iki sütun sığmaz; alt alta dizilir.
MIN_TWO_COLUMN_WIDTH = 88


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
    """Ekranı temizle ve karşılama kutusunu bas."""
    if clear:
        console.clear()

    console.print()
    console.print(
        Panel(
            _layout(info, console.width),
            box=ROUNDED,
            border_style=theme.DIM,
            title=Text(f" {messages.APP_NAME} {info.version} ", style=theme.ACCENT),
            title_align="left",
            width=min(MAX_WELCOME_WIDTH, console.width),
            padding=(1, 2),
        )
    )


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


# --------------------------------------------------------------------------- #


def _layout(info: SessionInfo, width: int) -> Group | Table:
    """Terminal genişliğine göre iki sütun ya da alt alta diz.

    Dar terminalde iki sütun zorlamak her satırı üç kere sardırır ve okunmaz hale
    getirir; orada dikey dizilim doğru olandır.
    """
    if width < MIN_TWO_COLUMN_WIDTH:
        return Group(_identity(info), Text(), _guide())
    columns = Table.grid(padding=(0, 3))
    columns.add_column(width=LEFT_COLUMN_WIDTH)
    columns.add_column(overflow="fold")
    columns.add_row(_identity(info), _guide())
    return columns


def _identity(info: SessionInfo) -> Group:
    """Sol sütun: kimlik ve "şu an neredeyim" bilgisi."""
    header = Text()
    header.append("✦ ", style=theme.ACCENT)
    header.append_text(gradient("FUSION"))

    facts = Table.grid(padding=(0, 1))
    facts.add_column(style=theme.DIM, justify="right")
    facts.add_column()
    facts.add_row(messages.WELCOME_FIELD_ENGINE, Text(info.engine, style=theme.ACCENT))
    facts.add_row(
        messages.WELCOME_FIELD_APPROVAL, Text(info.approval, style=mode_color(info.approval))
    )
    facts.add_row(messages.WELCOME_FIELD_MODEL, Text(info.model, style=theme.INFO))
    facts.add_row(messages.WELCOME_FIELD_DIR, Text(info.working_dir, style=theme.DIM))
    facts.add_row(messages.WELCOME_FIELD_MEMORY, _memory_text(info.lesson_count))

    return Group(header, Text(messages.REPL_TAGLINE, style=theme.DIM), Text(), facts)


def _guide() -> Group:
    """Sağ sütun: ne yapabileceğin."""
    return Group(
        _section(messages.WELCOME_START_TITLE, messages.WELCOME_START_ITEMS),
        Text(),
        _section(messages.WELCOME_ABILITY_TITLE, messages.WELCOME_ABILITY_ITEMS),
    )


def _section(title: str, items: tuple[tuple[str, str], ...]) -> Group:
    heading = Text(title, style=f"bold {theme.ACCENT}")
    table = Table.grid(padding=(0, 2))
    table.add_column(style=theme.INFO, no_wrap=True)
    table.add_column(style=theme.DIM, overflow="fold")
    for label, description in items:
        table.add_row(label, description)
    return Group(heading, table)


def _memory_text(lesson_count: int | None) -> Text:
    if lesson_count is None:
        return Text(messages.WELCOME_MEMORY_OFF, style=theme.WARN)
    return Text(messages.WELCOME_MEMORY_ON.format(count=lesson_count), style=theme.OK)


def _blend(start: str, end: str, ratio: float) -> str:
    """İki #RRGGBB rengi arasında doğrusal geçiş."""
    left, right = start.lstrip("#"), end.lstrip("#")
    channels = []
    for offset in (0, 2, 4):
        start_value = int(left[offset : offset + 2], 16)
        end_value = int(right[offset : offset + 2], 16)
        channels.append(round(start_value + (end_value - start_value) * ratio))
    return "#" + "".join(f"{value:02X}" for value in channels)
