"""Alt süreç borusunu okuyan, belleği sınırlı yakalayıcı.

Ölçüldü (30 Ekim): `communicate()` tüm çıktıyı belleğe alıyordu; 60 MB çıktıda dönen metin
60 MB, süreç belleği ≈ +276 MB. Burada her akış için yalnız ilk `limit` ve son `limit` bayt
tutulur, ortası atılıp sayılır. Okuyucu daemon iş parçacığıdır ve EOF'a kadar okumaya (atmaya)
devam eder: boruyu tutan arka plan çocuğu yazarken SIGPIPE ile ölmez, bellek de büyümez.
"""

from __future__ import annotations

import contextlib
import threading
from collections import deque
from typing import IO

_CHUNK_BYTES = 65_536


class BoundedCapture:
    """Tek bir borunun baş + son kesitini tutar."""

    def __init__(self, stream: IO[bytes], *, limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self._head = bytearray()
        self._tail: deque[bytes] = deque()
        self._tail_size = 0
        self._dropped = 0
        self._lock = threading.Lock()
        self._eof = threading.Event()
        self._thread = threading.Thread(target=self._pump, name="fusion-capture", daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        try:
            while chunk := self._stream.read1(_CHUNK_BYTES):  # type: ignore[attr-defined]
                self._add(chunk)
        except (OSError, ValueError):
            pass  # boru kapandı
        finally:
            with contextlib.suppress(OSError):
                self._stream.close()  # okuyucu sahiptir: fd sızmaz
            self._eof.set()

    def _add(self, chunk: bytes) -> None:
        with self._lock:
            room = self._limit - len(self._head)
            if room > 0:
                self._head += chunk[:room]
                chunk = chunk[room:]
            if not chunk:
                return
            self._tail.append(chunk)
            self._tail_size += len(chunk)
            while self._tail_size - len(self._tail[0]) >= self._limit:
                self._dropped += len(self._tail.popleft())
                self._tail_size = sum(map(len, self._tail))
            if self._tail_size > self._limit:
                excess = self._tail_size - self._limit
                self._tail[0] = self._tail[0][excess:]
                self._tail_size -= excess
                self._dropped += excess

    def wait_eof(self, timeout: float) -> bool:
        """EOF görüldü mü? Boruyu tutan çocuk varsa False döner."""
        return self._eof.wait(timeout)

    def text(self) -> str:
        """Şimdiye kadar okunan metin: geçersiz UTF-8 bayt `\\ufffd`, satır sonları `\\n`."""
        with self._lock:
            head, tail, dropped = bytes(self._head), b"".join(self._tail), self._dropped
        if dropped:
            marker = f"\n[… {dropped} bayt atıldı (çıktı çok uzun) …]\n"
            text = head.decode("utf-8", errors="replace") + marker
            text += tail.decode("utf-8", errors="replace")
        else:
            text = (head + tail).decode("utf-8", errors="replace")
        return text.replace("\r\n", "\n").replace("\r", "\n")
