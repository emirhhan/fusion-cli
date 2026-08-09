"""Olay beslemeli çalışma satırı.

Tam-ekranda Rich `Live` kullanılamaz (spinner/imleç dizileri konuşma tamponuna
sızar). Bunun yerine bu dinleyici, model olaylarından çalışma satırının metnini
üretir: "hazırlanıyor…  Ns · token · model".

Metin olay ANINDA dondurulmaz, `render()` çağrıldığı anda üretilir. Dondurulduğu
sürece geçen süre `ModelCallStarted`'da hesaplanıp "0 ms" olarak yazılı kalıyor
ve ancak cevap gelince gerçek değere sıçrıyordu; kullanıcı turun ilerlediğini
göremiyordu. TUI her spinner karesinde `render()` çağırdığı için süre artık
akıyor.
"""

from __future__ import annotations

from ...core.clock import SystemClock
from ...core.events import (
    Event,
    ModelCallFinished,
    ModelCallStarted,
    ModelFallbackActivated,
    TurnFinished,
)
from ...core.protocols import Clock
from ...ui import messages
from ...ui.text import format_duration, format_model, format_served_model
from ...ui.work import format_tokens


class WorkLineSink:
    """Model olaylarını dinler; çalışma satırı metnini istendiği anda üretir."""

    def __init__(
        self,
        *,
        interrupt_hint: str = messages.WORK_INTERRUPT,
        clock: Clock | None = None,
    ) -> None:
        # Kesme ipucu enjekte edilir: TUI'de esc turu keser, eski tam-ekranda Ctrl-C.
        self._interrupt_hint = interrupt_hint
        self._clock = clock or SystemClock()
        self._model = ""
        self._tokens = 0
        # None = çalışan bir model çağrısı yok; satır çizilmez.
        self._started_at: float | None = None

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
            self._started_at = self._clock.monotonic()
        elif isinstance(event, ModelCallFinished):
            if event.background:
                return
            # Başlangıçta birincil yazılmıştı; cevabı gerçekte hangi model verdiyse
            # satır ona güncellenir. Yedek devraldıysa kullanıcı bunu GÖRÜR.
            if event.result.model:
                self._model = format_served_model(event.result.model, event.result.served_by)
            self._tokens += event.result.usage.total_tokens
        elif isinstance(event, ModelFallbackActivated):
            if event.background:
                return
            self._model = format_model(event.fallback_model)
        elif isinstance(event, TurnFinished):
            self._started_at = None

    def render(self) -> str:
        """Süre · token · model — boş olanları atlayarak güncel satırı üret.

        Çalışan bir çağrı yoksa boş string döner ve satır çizilmez.
        """
        if self._started_at is None:
            return ""
        elapsed_ms = int((self._clock.monotonic() - self._started_at) * 1000)
        parts = [format_duration(elapsed_ms)]
        if self._tokens:
            parts.append(messages.WORK_TOKENS.format(count=format_tokens(self._tokens)))
        if self._model:
            parts.append(self._model)
        detay = " · ".join(parts)
        return f"  {messages.WORK_THINKING}  ({detay} · {self._interrupt_hint})"
