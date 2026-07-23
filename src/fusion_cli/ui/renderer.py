"""Terminal render'ı — olayları ekrana basan tek yer.

Rich importu YALNIZCA bu dosyadadır; motor katmanı terminal kütüphanesi tanımaz.

Eski projedeki "anlamsız görüntü" hatasının çözümü buradaki iki değişmezdir:

1. **Satır bütünlüğü.** Akan metin yarım satır bırakmışken durum/hata satırı
   basılmaz; önce satır kapatılır. Eski kodda bu bayrağı set eden fonksiyon hiç
   çağrılmadığı için cümlenin ortası araç kartının altına düşüyordu.
2. **Kanal ayrımı.** Farklı kanaldan (alt-ajan, council) metin geldiğinde önce
   mevcut satır kapatılır ve kanal başlığı basılır; iki akış aynı satıra binemez.

Veriyolu olayları zaten sırayla verdiği için burada eşzamanlılık kaygısı yoktur.
"""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape

from ..core.events import (
    Channel,
    ErrorOccurred,
    Event,
    ModelCallFinished,
    ModelCallStarted,
    StatusChanged,
    TokenReceived,
    TurnFinished,
)
from . import messages, theme

_CHANNEL_LABELS = {
    Channel.SUBAGENT: "alt-ajan",
    Channel.COUNCIL: "council",
}


class ConsoleRenderer:
    """Olayları Rich konsoluna basan dinleyici."""

    def __init__(self, console: Console | None = None, *, show_progress: bool = True) -> None:
        self._console = console or Console()
        self._show_progress = show_progress
        self._line_open = False
        self._active_channel: Channel | None = None

    # -- EventSink ---------------------------------------------------------- #

    def handle(self, event: Event) -> None:
        if isinstance(event, TokenReceived):
            self._write_stream(event.channel, event.text)
        elif isinstance(event, StatusChanged):
            self._status(event.message)
        elif isinstance(event, ModelCallStarted):
            self._status(messages.MODEL_CALL_STARTED.format(role=event.role, model=event.model))
        elif isinstance(event, ModelCallFinished):
            self._model_finished(event)
        elif isinstance(event, ErrorOccurred):
            self._error(event.message)
        elif isinstance(event, TurnFinished):
            self._close_line()
            self._active_channel = None

    # -- Akış --------------------------------------------------------------- #

    def _write_stream(self, channel: Channel, text: str) -> None:
        if not text:
            return
        if channel is not self._active_channel:
            self._close_line()
            self._channel_header(channel)
            self._active_channel = channel
        # `out` ham yazar: model çıktısındaki köşeli parantezler Rich markup'ı
        # sanılıp yorumlanmaz, çıktı bozulmaz.
        self._console.out(text, end="", highlight=False)
        self._line_open = not text.endswith("\n")

    def _channel_header(self, channel: Channel) -> None:
        label = _CHANNEL_LABELS.get(channel)
        if label is not None:
            self._console.print(f"[{theme.ACCENT_ALT}]┌ {label}[/{theme.ACCENT_ALT}]")

    def _close_line(self) -> None:
        """Yarım kalmış akış satırını kapat. Panel/durum satırı asla metnin üstüne binmez."""
        if self._line_open:
            self._console.out("")
            self._line_open = False

    # -- Diğer olaylar ------------------------------------------------------- #

    def _status(self, message: str) -> None:
        if not self._show_progress:
            return
        self._close_line()
        body = escape(message)
        self._console.print(f"[{theme.DIM}]{theme.ICON_STATUS} {body}[/{theme.DIM}]")

    def _model_finished(self, event: ModelCallFinished) -> None:
        result = event.result
        if result.ok:
            self._status(
                messages.MODEL_CALL_OK.format(
                    role=event.role,
                    latency=result.latency_ms,
                    tokens=result.usage.total_tokens,
                )
            )
            return
        self._error(messages.MODEL_CALL_FAILED.format(role=event.role, error=result.error or ""))

    def _error(self, message: str) -> None:
        self._close_line()
        label = f"[{theme.ERROR}]{theme.ICON_ERROR} {messages.ERROR_PREFIX}[/{theme.ERROR}]"
        self._console.print(f"{label} {escape(message)}")
