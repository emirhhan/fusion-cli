"""Olay beslemeli çalışma satırı.

Tam-ekranda Rich `Live` kullanılamaz (spinner/imleç dizileri konuşma tamponuna
sızar). Bunun yerine bu dinleyici, model olaylarından layout çalışma satırının
metnini üretir: "hazırlanıyor…  Ns · token · model". Spinner yoktur; süre/token
olaylarla güncellenir (animasyon Faz 4 cilasıdır).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ...core.events import Event, ModelCallFinished, ModelCallStarted, TurnFinished
from ...ui import messages
from ...ui.text import format_duration, format_model
from ...ui.work import format_tokens


class WorkLineSink:
    """Model olaylarını dinleyip çalışma satırı metnini besler."""

    def __init__(
        self,
        on_update: Callable[[str], None],
        on_clear: Callable[[], None],
        *,
        interrupt_hint: str = messages.WORK_INTERRUPT,
    ) -> None:
        self._on_update = on_update
        self._on_clear = on_clear
        # Kesme ipucu enjekte edilir: TUI'de esc turu keser, eski tam-ekranda Ctrl-C.
        self._interrupt_hint = interrupt_hint
        self._model = ""
        self._tokens = 0
        self._started_at = 0.0

    def handle(self, event: Event) -> None:
        if isinstance(event, ModelCallStarted):
            # Arka plan çağrıları (hakem, sentez, öz-denetim…) kullanıcıya çalışma
            # satırı olarak GÖSTERİLMEZ; yalnızca muhasebeye girer.
            if event.background:
                return
            # Rol adı DEĞİL model kimliği gösterilir. Rol, yapılandırmada yazan
            # addır ve yedeğe düşülse bile değişmez; ekran o zaman kullanıcının
            # SEÇTİĞİ modeli göstermeye devam eder, oysa cevabı başka bir model
            # üretmiştir. Ne çalıştığı görünmezse yanlış model sessizce çalışır.
            self._model = format_model(event.model)
            self._tokens = 0
            self._started_at = time.monotonic()
            self._publish()
        elif isinstance(event, ModelCallFinished):
            if event.background:
                return
            # Başlangıçta birincil yazılmıştı; cevabı gerçekte hangi model verdiyse
            # satır ona güncellenir. Yedek devraldıysa kullanıcı bunu GÖRÜR.
            if event.result.model:
                self._model = format_model(event.result.model)
            self._tokens += event.result.usage.total_tokens
            self._publish()
        elif isinstance(event, TurnFinished):
            self._on_clear()

    def _publish(self) -> None:
        """Süre · token · model — boş olanları atlayarak çalışma satırını yayınla."""
        elapsed_ms = int((time.monotonic() - self._started_at) * 1000)
        parts = [format_duration(elapsed_ms)]
        if self._tokens:
            parts.append(messages.WORK_TOKENS.format(count=format_tokens(self._tokens)))
        if self._model:
            parts.append(self._model)
        detay = " · ".join(parts)
        # Live spinner ile aynı dizilim: ayrıntı ve kesme ipucu parantez içinde.
        self._on_update(f"  {messages.WORK_THINKING}  ({detay} · {self._interrupt_hint})")
