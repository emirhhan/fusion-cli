"""Koşu izlerinin diske yazılması ve geri okunması.

Teşhis koşu BİTTİKTEN sonra yapılır: hangi adımda ne olduğu, hangi aracın
engellendiği ve turun neden durduğu ancak kalıcı bir izle sorulabilir. Biçim
JSONL'dir; `JsonRenderer` ile aynı sözleşmeyi kullanır, böylece `--json` akışı
ile dosya izi ayrışmaz.

Sır maskeleme `JsonRenderer` içinde yapılır: iz de aynı yoldan geçtiği için
diske yazılan satırda anahtar/parola bulunmaz.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

from ..core.events import Event
from .json_sink import JsonRenderer
from .replay import event_from_payload

_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


class TraceWriter:
    """Tek bir koşunun olaylarını dosyaya yazan dinleyici."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._renderer = JsonRenderer(stream)

    def handle(self, event: Event) -> None:
        self._renderer.handle(event)

    def close(self) -> None:
        self._stream.close()


class TraceStore:
    """Koşu izlerinin bulunduğu dizin."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path(self, run_id: str) -> Path:
        return self._root / f"{_SAFE_ID.sub('-', run_id)}.jsonl"

    def writer(self, run_id: str) -> TraceWriter:
        """Koşu için yazıcı aç; dizin yoksa oluştur."""
        self._root.mkdir(parents=True, exist_ok=True)
        return TraceWriter(self.path(run_id).open("w", encoding="utf-8"))

    def runs(self) -> tuple[str, ...]:
        """Kayıtlı koşu kimlikleri, eskiden yeniye."""
        if not self._root.is_dir():
            return ()
        files = sorted(self._root.glob("*.jsonl"), key=lambda item: item.stat().st_mtime)
        return tuple(item.stem for item in files)

    def latest(self) -> str | None:
        """En son yazılan koşunun kimliği."""
        kayitlar = self.runs()
        return kayitlar[-1] if kayitlar else None

    def read(self, run_id: str) -> list[Event]:
        """Kaydedilmiş olayları geri kur; tanınmayan satır atlanır.

        Bozuk tek satır bütün izi işe yaramaz kılmamalı: teşhis aracının kendisi
        kırılgan olursa hata anında elde hiçbir şey kalmaz.
        """
        return list(self._iter_events(self.path(run_id)))

    def _iter_events(self, path: Path) -> Iterator[Event]:
        if not path.is_file():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = event_from_payload(payload)
            if event is not None:
                yield event
