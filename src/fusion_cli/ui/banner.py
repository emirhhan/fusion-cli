"""Karşılama ekranı ve durum satırı.

Tasarım kararları:

- **Ekran temizlenir.** `fusion` çalıştığında terminal geçmişi temizlenir; oturum
  temiz bir sayfada başlar.
- **Yatay düzen.** Solda ürün imzası, sağda kullanıcının ihtiyaç duyduğu iki bilgi:
  bir ipucu ve projenin ne olduğu. Dikey yığmak ekranın yarısını yiyordu.
- **Tam genişlik.** Kutu terminale yayılır; sabit genişlik geniş ekranda ortada
  asılı kalıyordu.
- **Giriş altta, konuşma üstte.** Açılışta kutunun altı boşlukla doldurulur;
  giriş satırı ekranın dibine oturur. Kullanıcı ilk mesajını gönderdiğinde ekran
  temizlenip karşılama DOLGUSUZ basılır: konuşma kutunun hemen altından başlar ve
  ekran doldukça doğal olarak yukarı kayar. Böylece dolgu yalnızca boş oturumda
  yaşar, konuşmanın ortasında kocaman bir boşluğa dönüşmez.
- **Dar terminalde küçülür.** Büyük imza sığmıyorsa tek satırlık sürümüne iner;
  hiçbir genişlikte taşma olmaz.

Renk ve simge değerleri `theme` modülünden gelir; buraya hex gömülmez.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.box import ROUNDED
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from . import messages, theme

#: Giriş satırı ve altındaki durum çubuğu için ekranın dibinde bırakılan yer.
PROMPT_RESERVED_LINES = 3


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
        rendered.append(char, style=theme.blend(start, end, ratio))
        index += 1
    return rendered


#: Kaydırma geçmişini (scrollback) temizleyen ANSI dizisi. `console.clear()` bunu
#: yapmaz; yalnızca görünen ekranı siler.
_CLEAR_SCROLLBACK = "\x1b[3J"


def print_welcome(
    console: Console, info: SessionInfo, *, clear: bool = True, pad: bool = True
) -> None:
    """Ekranı temizle ve karşılamayı bas.

    `pad` açıkken kutunun altı boşlukla doldurulur; giriş satırı ekranın dibine
    oturur. İlk mesajdan sonra dolgusuz basılır (bkz. modül açıklaması).
    """
    if clear:
        console.clear()
        # `console.clear()` yalnızca GÖRÜNEN ekranı siler; kaydırma geçmişi (scrollback)
        # olduğu gibi kalır ve kullanıcı yukarı kaydırınca fusion'dan önceki terminal
        # çıktısını görür — bir uygulamaya girilmiş hissi vermez. `ESC [ 3 J` geçmişi de
        # temizler. Yalnızca ilk karşılamada yapılır; sonraki yeniden çizimlerde oturumun
        # kendi geçmişi korunmalıdır.
        console.file.write(_CLEAR_SCROLLBACK)
        console.file.flush()

    blocks: list[RenderableType] = [Text(), _welcome_panel(info)]
    for block in blocks:
        console.print(block)
    if pad:
        _pad_to_bottom(console, blocks)


def _pad_to_bottom(console: Console, blocks: list[RenderableType]) -> None:
    """Girişi ekranın dibine indirecek kadar boş satır bas.

    Yükseklik ölçülerek bulunur, sabit sayı varsayılmaz: kutunun boyu terminal
    genişliğine göre değişiyor. Sığmıyorsa hiç dolgu basılmaz — taşma, dibe
    yapıştırmaktan daha kötüdür.
    """
    used = sum(len(console.render_lines(block, console.options, pad=False)) for block in blocks)
    console.print("\n" * max(0, console.height - used - PROMPT_RESERVED_LINES), end="")


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


def _welcome_panel(info: SessionInfo) -> Panel:
    """Kompakt yuvarlak karşılama kutusu (Claude Code dizilimi).

    Genişlik verilmez: kutu terminale yayılır. İçerik tek sütundur — üstte imza ve
    selamlama, altında kısa tanıtım, ipucu ve oturum bilgileri.
    """
    return Panel(
        _welcome_body(info),
        box=ROUNDED,
        border_style=theme.DIM,
        padding=(1, 2),
    )


def _welcome_body(info: SessionInfo) -> Group:
    """Kutunun tek sütunlu içeriği."""
    return Group(
        _header(info),
        Text(messages.WELCOME_ABOUT_TEXT, style=theme.DIM),
        Text(),
        _tip_line(info),
        Text(),
        _facts_line(info),
    )


def _header(info: SessionInfo) -> Text:
    """`✻ Fusion CLI  hoş geldin  v1.0` — yıldız, gradyanlı imza, selamlama, sürüm."""
    line = Text(f"{theme.ICON_SPARKLE} ", style=theme.ACCENT)
    line.append_text(gradient(messages.APP_NAME))
    line.append(f"  {messages.WELCOME_GREETING}", style=theme.DIM)
    line.append(f"  {info.version}", style=theme.DIM)
    return line


def _tip_line(info: SessionInfo) -> Text:
    """`İpucu: …` — çalışma dizinine göre kararlı seçilen tek ipucu."""
    line = Text(f"{messages.WELCOME_TIP_TITLE}: ", style=f"bold {theme.ACCENT}")
    line.append(pick_tip(info.working_dir), style=theme.DIM)
    return line


def _facts_line(info: SessionInfo) -> Text:
    """Oturum bilgileri — kutunun içinde son satır (motor · onay · model · bellek · dizin).

    Kutu içinde basıldığı için sığmazsa Rich kendiliğinden sarar; alan düşürmeye gerek
    kalmaz, her bilgi görünür kalır.
    """
    fields = [
        (messages.WELCOME_FIELD_ENGINE, info.engine, theme.ACCENT),
        (messages.WELCOME_FIELD_APPROVAL, info.approval, mode_color(info.approval)),
        (messages.WELCOME_FIELD_MODEL, info.model, theme.INFO),
        (messages.WELCOME_FIELD_MEMORY, _memory_text(info.lesson_count), theme.OK),
        (messages.WELCOME_FIELD_DIR, info.working_dir, theme.DIM),
    ]
    line = Text()
    for index, (label, value, color) in enumerate(fields):
        if index:
            line.append(" · ", style=theme.DIM)
        line.append(f"{label} ", style=theme.DIM)
        line.append(value, style=color)
    return line


def _memory_text(lesson_count: int | None) -> str:
    if lesson_count is None:
        return messages.WELCOME_MEMORY_OFF
    return messages.WELCOME_MEMORY_ON.format(count=lesson_count)
