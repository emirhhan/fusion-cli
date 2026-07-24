"""JSON çıktı dinleyicisi — makine okunur akış.

Olay veriyolunun ikinci sınavı: aynı olaylardan bambaşka bir çıktı biçimi üretmek,
motor koduna dokunmadan mümkün olmalıydı. Bu dosya yalnızca `EventSink` implemente
eder ve her olayı bir satır JSON olarak yazar (JSONL).

Betiklerden kullanım için tasarlandı: `fusion run "..." --json | jq`.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from enum import Enum
from typing import TextIO

from ..core.events import Event
from ..core.redaction import redact


class JsonRenderer:
    """Her olayı tek satır JSON olarak yazan dinleyici.

    Olay alanları (araç argümanı/çıktısı, hata mesajı) kullanıcı komutundan veya
    sağlayıcı istisnasından gelen sır içerebilir. Serileştirilen satır diske/akışa
    yazılmadan önce `redact`'ten geçer: JSONL çıktısına sır sızmaz.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def handle(self, event: Event) -> None:
        payload = {"event": type(event).__name__, **_fields(event)}
        line = json.dumps(payload, ensure_ascii=False, default=_encode)
        self._stream.write(redact(line) + "\n")
        self._stream.flush()


def _fields(event: Event) -> dict[str, object]:
    return {field.name: getattr(event, field.name) for field in dataclasses.fields(event)}


def _encode(value: object) -> object:
    """Dataclass ve enum'ları JSON'a çevir; gerisi metne düşer.

    `json.dumps`'ın `default` kancasıdır: yalnızca serileştirilemeyen değerler için
    çağrılır, bu yüzden "gerisi metne düşer" güvenli bir son çaredir.
    """
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
    return str(value)
