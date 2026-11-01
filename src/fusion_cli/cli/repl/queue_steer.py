"""Tur sürerken kuyruğa giren mesajları aynı tura verme (#190).

Claude Code: "if you queue a message while Claude is running tool calls, Claude Code passes
it to Claude as soon as those tool calls finish, within the same turn. When the turn ends
with messages still queued, they go out without another key press." Komutlar ve `!` kabuk
satırları tur bitene kadar bekler.

Fusion motoru bunun için `SteeringQueue`'yu zaten okuyor (araç çağrıları arasında, sıradaki
model çağrısından önce). Bu köprü TUI kuyruğu ile o kuyruğu birbirine bağlar: düz mesaj
koşan agent turunun yönlendirme kuyruğuna girer; tur bittiğinde tüketilmeyenler sıradaki
tur olarak gönderilmek üzere geri verilir, tüketilenler konuşma dökümüne yazılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...core.steering import SteeringQueue, steering_text


def is_plain_message(line: str) -> bool:
    """Aynı tura verilebilir mi? Komut, `!` kabuk ve `@` anması tur sonunu bekler.

    `@dosya` anması dosya içeriğini tur başında ekler; yönlendirme notu bu adımı atlardı.
    """
    text = line.strip()
    return bool(text) and text[0] not in "/!" and "@" not in text


@dataclass
class SteerBridge:
    """Koşan agent turunun yönlendirme kuyruğu ve ona verilen mesajlar."""

    _queue: SteeringQueue | None = None
    _offered: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self._queue is not None

    @property
    def pending(self) -> bool:
        """Koşan tura verilmiş ama modele henüz gitmemiş mesaj var mı?"""
        return self._queue is not None and self._queue.pending

    def begin(self) -> SteeringQueue:
        """Yeni agent turu: boş kuyruk kur ve motora verilmek üzere döndür."""
        self._queue = SteeringQueue()
        self._offered = []
        return self._queue

    def offer(self, line: str) -> bool:
        """Düz mesajı koşan tura ver; tur yoksa ya da satır uygun değilse False."""
        if self._queue is None or not is_plain_message(line):
            return False
        self._queue.push(line)
        self._offered.append(line.strip())
        return True

    def take_back(self) -> list[str]:
        """Up ile geri alma: henüz modele gitmemiş mesajları kuyruktan çıkar."""
        if self._queue is None:
            return []
        taken = _texts(self._queue)
        for text in taken:
            if text in self._offered:
                self._offered.remove(text)
        return taken

    def end(self) -> tuple[list[str], list[str]]:
        """Tur bitti: (tüketilenler, tüketilmeyenler). Köprü yeniden boşta."""
        if self._queue is None:
            return [], []
        leftover = _texts(self._queue)
        consumed = list(self._offered)
        for text in leftover:
            if text in consumed:
                consumed.remove(text)
        self._queue = None
        self._offered = []
        return consumed, leftover


def _texts(queue: SteeringQueue) -> list[str]:
    return [text for message in queue.drain() if (text := steering_text(message)) is not None]
