"""Çalışma göstergesi — model çalışırken görünen canlı satır.

Kullanıcı bir istek gönderdikten sonra ilk token gelene kadar saniyeler geçebilir.
Boş ekran "takıldı mı?" hissi verir; bu satır ne olduğunu ve ne kadar sürdüğünü
gösterir:

    ⠋ hazırlanıyor…  3s · 231 token · nemotron-super

Tur bitince gösterge silinir ve yerine tek satırlık özet kalır:

    ✦ 4.1s · 1.2k token · nemotron-super

Neden burada Rich `Live` güvenli: REPL tasarımı gereği tur çalışırken giriş satırı
KAPALIDIR. prompt_toolkit ile aynı anda imleç yönetme sorunu doğmaz — eski projede
satırların birbirini bozmasının sebebi tam olarak buydu.

Gösterge yalnızca gerçek terminalde çalışır; boru hattında ve testte sessizdir.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from rich.console import Console
from rich.live import Live
from rich.text import Text

from . import messages, theme
from .text import format_duration

#: Nabız gibi büyüyüp küçülen yıldız kareleri (Claude Code'un `✻` işaretine yakın
#: twinkle). Hepsi tek hücre genişliğindedir; kare değişince satır kaymaz.
FRAMES = "·✢✳✶✷✸✹✺✹✸✷✶✳✢"
FRAMES_PER_SECOND = 10
#: Canlı satırın yeniden çizim sıklığı.
REFRESH_PER_SECOND = 10
#: Bu sayının üstündeki token değerleri kısaltılır (1234 → 1.2k).
TOKEN_SHORTEN_THRESHOLD = 1_000


@dataclass(slots=True)
class WorkState:
    """Turun o anki ilerlemesi. Gösterge her çizimde buradan okur."""

    label: str = ""
    model: str = ""
    tokens: int = 0
    started_at: float = field(default_factory=time.monotonic)

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def __rich__(self) -> Text:
        """Canlı satırı çiz. Rich her yenilemede çağırır; kare ve süre böyle akar."""
        frame = FRAMES[int((time.monotonic() - self.started_at) * FRAMES_PER_SECOND) % len(FRAMES)]
        line = Text("  ")
        line.append(f"{frame} ", style=theme.ACCENT)
        line.append(self.label, style=theme.ACCENT)
        # Claude Code dizilimi: süre/token/model ve kesme ipucu parantez içinde, sönük.
        detail = _details(self.elapsed_ms, self.tokens, self.model)
        line.append(f"  ({detail} · {messages.WORK_INTERRUPT})", style=theme.DIM)
        return line


class WorkIndicator:
    """Canlı çalışma satırını yöneten gösterge.

    Çıktı basılmadan önce `pause()`, yeni bir bekleme başlayınca `resume()` çağrılır;
    böylece gösterge hiçbir zaman akan metnin üstüne binmez.
    """

    def __init__(self, console: Console, *, enabled: bool = True) -> None:
        self._console = console
        # Terminal değilse animasyon anlamsızdır ve çıktıyı kirletir.
        self._enabled = enabled and console.is_terminal
        self._state: WorkState | None = None
        self._live: Live | None = None

    @property
    def running(self) -> bool:
        return self._state is not None

    def start(self, label: str, *, model: str = "") -> None:
        """Yeni bir tur başlat. Süre buradan itibaren sayılır."""
        self._state = WorkState(label=label, model=model)
        self._show()

    def update(
        self, *, label: str | None = None, tokens: int | None = None, model: str | None = None
    ) -> None:
        """Devam eden turun bilgisini güncelle.

        `model` güncellenebilir olmalıdır: tur birincil modelin adıyla başlar ama
        cevabı yedek verebilir. Etiket başlangıçtaki adda donarsa kullanıcı,
        SEÇTİĞİ modelin çalıştığını sanır — hangi modelin gerçekten cevap verdiği
        yalnızca sonuçta bilinir. Token'ın aksine model DEĞİŞTİRİLİR, biriktirilmez.
        """
        if self._state is None:
            return
        if label is not None:
            self._state.label = label
        if tokens is not None:
            self._state.tokens += tokens
        if model is not None:
            self._state.model = model

    def pause(self) -> None:
        """Canlı satırı gizle. Ekrana bir şey basılmadan ÖNCE çağrılmalıdır."""
        if self._live is not None:
            self._live.stop()
            self._live = None

    def resume(self) -> None:
        """Bekleme sürüyorsa canlı satırı tekrar göster."""
        if self._state is not None and self._live is None:
            self._show()

    def finish(self) -> str | None:
        """Turu bitir ve özet metnini döndür. Hiç çalışmadıysa None.

        Metin döner, biçimlenmiş satır değil: çağıran taraf bunu ister tek başına
        bir özet satırı olarak, ister bir durum satırının sonuna parantez içinde
        basar. Sunum kararı göstergenin işi değil.
        """
        self.pause()
        state, self._state = self._state, None
        # Hiç iş yapılmadıysa (token da model de yok) özet basmaya değmez.
        if state is None or (not state.tokens and not state.model):
            return None
        return _details(state.elapsed_ms, state.tokens, state.model)

    def _show(self) -> None:
        if not self._enabled or self._state is None:
            return
        self._live = Live(
            self._state,
            console=self._console,
            refresh_per_second=REFRESH_PER_SECOND,
            transient=True,
        )
        self._live.start()


def format_tokens(tokens: int) -> str:
    """Token sayısını kısa yaz: 840 → 840, 1234 → 1.2k."""
    if tokens < TOKEN_SHORTEN_THRESHOLD:
        return str(tokens)
    return f"{tokens / 1000:.1f}k"


def _details(elapsed_ms: int, tokens: int, model: str) -> str:
    """Süre · token · model — boş olanlar atlanır."""
    parts = [format_duration(elapsed_ms)]
    if tokens:
        parts.append(messages.WORK_TOKENS.format(count=format_tokens(tokens)))
    if model:
        parts.append(model)
    return " · ".join(parts)
