"""Ok tuşlarıyla gezilen tek seçimli liste — Claude Code CLI'daki seçim ekranı gibi.

Kullanıcı yukarı/aşağı ile gezer, Enter ile seçer, Esc ile vazgeçer. Seçili satır
`❯` işaretçisiyle ve parlak yazılır; diğerleri sönük kalır.

İki tasarım kararı:

1. **Renk `banner.gradient()`'ten gelir.** Kademe satırları ürünün imzasıyla AYNI
   turuncu→pembe geçişini kullanır; ikinci bir renk yolu açılmaz. Geçiş satır
   satır dağıtılır: listenin tamamı tek bir gradyan üzerinde okunur.

2. **TTY yoksa düz listeye düşülür.** Boru hattında, CI'da ve testte prompt_toolkit
   hiç kurulmaz; numaralı liste basılır ve `input()` ile seçim alınır. Otomasyon
   kırılmaz (bkz. `repl.input` aynı deseni kullanır).

3. **Ekran ayrı bir iş parçacığında çalışır.** Bu modül senkrondur ve senkron
   kalmalıdır: komut işleyicileri saftır. Ayrıntı için `_pick_interactive`.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from . import messages, theme

if TYPE_CHECKING:
    # Yalnızca tip denetimi için: prompt_toolkit'in beklediği parça listesi tipi.
    # `list[tuple[str, str]]` invariant olduğundan doğrudan atanamıyor; bu alias
    # union'lu üye tipini taşır ve `FormattedTextControl`'e sorunsuz geçer.
    from prompt_toolkit.formatted_text import StyleAndTextTuples

#: Seçim ekranında liste DIŞINDA kullanılan satırlar: başlık, boşluk, ipucu ve
#: iki kaydırma göstergesi. Terminal yüksekliğinden bu kadarı düşülür.
RESERVED_ROWS = 6

#: Terminal ne kadar kısa olursa olsun gösterilecek en az satır sayısı. Tek satırlık
#: bir liste gezilemez; kullanıcı nerede olduğunu göremez.
MIN_VIEWPORT_ROWS = 5


class TextStream(Protocol):
    """Düz modda listenin basıldığı çıktı. `sys.stdout` ve testteki tampon uyar."""

    def write(self, text: str, /) -> int: ...

    def flush(self) -> None: ...


class KeyEvent(Protocol):
    """prompt_toolkit tuş olayının kullandığımız kadarı.

    Kütüphane tipi doğrudan yazılamaz: `prompt_toolkit` yalnızca gerçekten
    gerektiğinde (fonksiyon içinde) import edilir, modül seviyesinde import
    edilseydi TTY olmayan ortamda gereksiz yere yüklenirdi.
    """

    @property
    def app(self) -> RunningPicker: ...


class RunningPicker(Protocol):
    """Çalışan seçim uygulamasının kullandığımız kadarı."""

    def exit(self, *, result: str | None) -> None: ...


@dataclass(frozen=True, slots=True)
class Choice:
    """Seçim listesindeki tek bir satır."""

    #: Seçildiğinde çağırana dönen değer.
    value: str
    #: Satırın solunda kalın yazılan ad.
    label: str
    #: Adın yanında sönük yazılan açıklama. Boş olabilir.
    description: str = ""


def pick(
    choices: Sequence[Choice],
    *,
    title: str,
    gradient_rows: bool = False,
    stream: TextStream | None = None,
) -> str | None:
    """Bir seçim al. Vazgeçilirse `None` döner.

    `gradient_rows` açıkken satırlar turuncudan pembeye boyanır (kademe merdiveni);
    kapalıyken tek vurgu rengi kullanılır (kaynak listesi, model listesi).
    """
    if not choices:
        return None
    if not sys.stdin.isatty():
        return _pick_plain(choices, title=title, stream=stream)
    picked = _pick_interactive(choices, title=title, gradient_rows=gradient_rows)
    return picked


def row_colors(count: int, *, gradient_rows: bool) -> tuple[str, ...]:
    """Her satırın rengi. Gradyan açıksa turuncudan pembeye eşit aralıklı dağılır.

    Renk hesabı imzayla AYNI karıştırıcıdan geçer; burada ikinci bir geçiş
    formülü tanımlanmaz.
    """
    if not gradient_rows:
        return (theme.ACCENT,) * count
    if count == 1:
        return (theme.ACCENT,)
    return tuple(
        theme.blend(theme.ACCENT, theme.ACCENT_ALT, index / (count - 1)) for index in range(count)
    )


# --------------------------------------------------------------------------- #
# TTY olmayan ortam
# --------------------------------------------------------------------------- #


def _pick_plain(choices: Sequence[Choice], *, title: str, stream: TextStream | None) -> str | None:
    """Numaralı liste + `input()`. Renk yok, gezinme yok; otomasyon için."""
    target = stream if stream is not None else sys.stdout
    target.write(f"{title}\n")
    for index, choice in enumerate(choices, 1):
        suffix = f" — {choice.description}" if choice.description else ""
        target.write(f"  {index}. {choice.label}{suffix}\n")
    target.write(messages.PICKER_PLAIN_PROMPT)
    target.flush()
    try:
        answer = input().strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return resolve_plain(choices, answer)


def resolve_plain(choices: Sequence[Choice], answer: str) -> str | None:
    """Düz moddaki cevabı çöz: 1-tabanlı sıra ya da satırın adı/değeri.

    Boş cevap vazgeçmektir. Tanınmayan cevap da vazgeçme sayılır: burada tekrar
    sormak boru hattında sonsuz döngüye girerdi.
    """
    wanted = answer.strip().lower()
    if not wanted:
        return None
    if wanted.isdigit():
        index = int(wanted) - 1
        return choices[index].value if 0 <= index < len(choices) else None
    for choice in choices:
        if wanted in (choice.value.lower(), choice.label.lower()):
            return choice.value
    return None


# --------------------------------------------------------------------------- #
# İnteraktif
# --------------------------------------------------------------------------- #


def _pick_interactive(
    choices: Sequence[Choice], *, title: str, gradient_rows: bool
) -> str | None:  # pragma: no cover - gerçek terminal gerektirir
    """prompt_toolkit tam-ekran seçim. Kurulamazsa düz listeye düşülür."""
    try:
        from prompt_toolkit.application import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import HSplit, Layout, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
    except ImportError:
        return _pick_plain(choices, title=title, stream=None)

    state = PickerState(len(choices))
    colors = row_colors(len(choices), gradient_rows=gradient_rows)
    bindings = KeyBindings()

    @bindings.add("up")
    @bindings.add("c-p")
    def _up(event: KeyEvent) -> None:
        state.move(-1)

    @bindings.add("down")
    @bindings.add("c-n")
    def _down(event: KeyEvent) -> None:
        state.move(1)

    @bindings.add("enter")
    def _accept(event: KeyEvent) -> None:
        event.app.exit(result=choices[state.index].value)

    @bindings.add("escape", eager=True)
    @bindings.add("c-c")
    def _cancel(event: KeyEvent) -> None:
        event.app.exit(result=None)

    # Pencere yüksekliği terminalden gelir; başlık, boşluk, ipucu ve iki gösterge
    # satırı için yer ayrılır. Ayrılmasaydı liste ipucu satırını ekrandan iterdi.
    viewport = max(MIN_VIEWPORT_ROWS, shutil.get_terminal_size().lines - RESERVED_ROWS)
    body = FormattedTextControl(lambda: fragments(choices, state.index, colors, height=viewport))
    layout = Layout(
        HSplit(
            [
                Window(
                    FormattedTextControl([(f"bold {theme.ACCENT}", title)]),
                    height=1,
                ),
                Window(height=1),
                Window(body, height=viewport + 2),
                Window(
                    FormattedTextControl([(theme.DIM, messages.PICKER_HINT)]),
                    height=1,
                ),
            ]
        )
    )
    application: Application[str | None] = Application(
        layout=layout, key_bindings=bindings, full_screen=False
    )
    # `in_thread=True`: seçim ekranı KENDİ event loop'unda, ayrı bir iş parçacığında
    # çalışır. REPL'in kendisi zaten bir event loop içinde döner (`repl.loop`); düz
    # `run()` çağrılsaydı asyncio iç içe loop'a izin vermediği için tur çöker, komut
    # işleyicilerini async yapmak ise "işleyiciler saf ve senkrondur" kuralını bozardı.
    # Çağıran iş parçacığı seçim bitene kadar bloklanır — kullanıcı zaten seçim
    # yaparken başka bir şey beklemiyor.
    picked = application.run(in_thread=True)
    # `Application.run()` kütüphane tarafında gevşek tiplenmiştir; sınırda daraltılır.
    return None if picked is None else str(picked)


@dataclass(slots=True)
class PickerState:
    """İmlecin hangi satırda olduğu. Uçlarda sarar: listenin sonundan başa geçilir."""

    count: int
    index: int = 0

    def move(self, delta: int) -> None:
        self.index = (self.index + delta) % self.count


def window_bounds(total: int, selected: int, height: int) -> tuple[int, int]:
    """Görünecek satır aralığı `[start, end)`.

    Seçili satır HER ZAMAN pencerenin içindedir ve pencere imleci ortalar; uçlarda
    listeye yaslanır. Katalog listeleri 300 satırı geçebiliyor (`/development`
    ücretli kaynakta 327 model); tamamını basmak ekranı taşırır ve üst satırlar
    terminalin geçmişine kaçar — kullanıcı listenin başını hiç göremez.
    """
    if height <= 0:
        return selected, selected + 1
    if total <= height:
        return 0, total
    start = selected - height // 2
    start = max(0, min(start, total - height))
    return start, start + height


def fragments(
    choices: Sequence[Choice],
    selected: int,
    colors: Sequence[str],
    *,
    height: int | None = None,
) -> StyleAndTextTuples:
    """Listeyi prompt_toolkit parçalarına çevir.

    Saf fonksiyondur: terminal olmadan test edilir. Seçili satır işaretçi alır ve
    kalın yazılır; seçili olmayanlar sönük kalır ve girinti hizası korunur.

    `height` verilirse yalnızca o kadar satır basılır ve gizli kalan satır sayısı
    yukarı/aşağı göstergeleriyle bildirilir. Gösterge olmadan kullanıcı listenin
    tamamını gördüğünü sanır ve aradığı modelin olmadığına karar verir.
    """
    total = len(choices)
    start, end = window_bounds(total, selected, height) if height is not None else (0, total)

    rendered: StyleAndTextTuples = []
    if start > 0:
        rendered.append((theme.DIM, messages.PICKER_MORE_ABOVE.format(count=start)))
        rendered.append(("", "\n"))
    for index in range(start, end):
        choice = choices[index]
        is_selected = index == selected
        marker = f" {theme.ICON_PROMPT} " if is_selected else "   "
        color = colors[index] if index < len(colors) else theme.ACCENT
        rendered.append((f"bold {color}" if is_selected else theme.DIM, marker))
        rendered.append((f"bold {color}" if is_selected else color, choice.label))
        if choice.description:
            rendered.append((theme.DIM, f"  {choice.description}"))
        rendered.append(("", "\n"))
    if end < total:
        rendered.append((theme.DIM, messages.PICKER_MORE_BELOW.format(count=total - end)))
        rendered.append(("", "\n"))
    return rendered
