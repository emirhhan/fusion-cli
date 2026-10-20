"""Tel biçimi: satır başına bir JSON nesnesi (JSON Lines), UTF-8.

Dört mesaj tipi vardır. `id` yalnız cevap bekleyen mesajlarda bulunur ve
eşleştirme için kullanılır:

- `istek` (uygulama → çekirdek) bir işlem çağırır
- `cevap` (uygulama → çekirdek) çekirdeğin sorusunu yanıtlar
- `olay` (çekirdek → uygulama) istenmeden akan durum bildirimi
- `sonuc` (çekirdek → uygulama) bir isteğin sonucu
- `soru` (çekirdek → uygulama) kullanıcı kararı ister
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Request:
    """Uygulamanın çağırdığı işlem."""

    id: str
    name: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Reply:
    """Uygulamanın, çekirdeğin sorusuna verdiği yanıt."""

    id: str
    data: dict[str, Any]


def decode(line: str) -> Request | Reply | None:
    """Bir satırı mesaja çevir; çözülemeyen satırda `None` döner."""
    stripped = line.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    identifier = payload.get("id")
    if not isinstance(identifier, str) or not identifier:
        return None
    data = payload.get("veri")
    data = data if isinstance(data, dict) else {}
    if payload.get("tip") == "istek":
        name = payload.get("ad")
        if not isinstance(name, str) or not name:
            return None
        return Request(id=identifier, name=name, data=data)
    if payload.get("tip") == "cevap":
        return Reply(id=identifier, data=data)
    return None


def _line(payload: dict[str, Any]) -> str:
    """Türkçe karakterleri koruyarak tek satırlık JSON üret."""
    return json.dumps(payload, ensure_ascii=False)


def encode_event(payload: dict[str, Any]) -> str:
    """Olay mesajını kodla."""
    return _line({"tip": "olay", "veri": payload})


def encode_result(request_id: str, data: dict[str, Any]) -> str:
    """İstek sonucunu kodla."""
    return _line({"tip": "sonuc", "id": request_id, "veri": data})


def encode_question(question_id: str, data: dict[str, Any]) -> str:
    """Kullanıcı sorusunu kodla."""
    return _line({"tip": "soru", "id": question_id, "veri": data})


def encode_error(message: str) -> str:
    """Protokol hatasını olay mesajı olarak kodla."""
    return encode_event({"olay": "ProtocolError", "mesaj": message})
