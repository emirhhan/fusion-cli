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
from ...ui.text import format_duration
from ...ui.work import format_tokens


class WorkLineSink:
    """Model olaylarını dinleyip çalışma satırı metnini besler."""

    def __init__(
        self, on_update: Callable[[str], None], on_clear: Callable[[], None]
    ) -> None:
        self._on_update = on_update
        self._on_clear = on_clear
        self._model = ""
        self._tokens = 0
        self._started_at = 0.0

    def handle(self, event: Event) -> None:
        if isinstance(event, ModelCallStarted):
            # Arka plan çağrıları (hakem, sentez, öz-denetim…) kullanıcıya çalışma
            # satırı olarak GÖSTERİLMEZ; yalnızca muhasebeye girer.
            if event.background:
                return
            self._model = event.role
            self._tokens = 0
            self._started_at = time.monotonic()
            self._yayınla()
        elif isinstance(event, ModelCallFinished):
            if event.background:
                return
            self._tokens += event.result.usage.total_tokens
            self._yayınla()
        elif isinstance(event, TurnFinished):
            self._on_clear()

    def _yayınla(self) -> None:
        """Süre · token · model — boş olanları atlayarak çalışma satırını yayınla."""
        elapsed_ms = int((time.monotonic() - self._started_at) * 1000)
        parcalar = [format_duration(elapsed_ms)]
        if self._tokens:
            parcalar.append(
                messages.WORK_TOKENS.format(count=format_tokens(self._tokens))
            )
        if self._model:
            parcalar.append(self._model)
        detay = " · ".join(parcalar)
        self._on_update(f"  {messages.WORK_THINKING}  {detay}")
