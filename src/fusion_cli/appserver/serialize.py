"""Olay nesnesini tel üzerinde taşınabilir bir sözlüğe çevirir.

Tek bir genel dönüştürücü kullanılır: sınıf adı `olay` alanına yazılır, alanlar
sözlüğe açılır. Böylece yeni bir olay tipi eklendiğinde burada iş çıkmaz.

`FusionCompleted` istisnadır: taşıdığı `FusionResult` düz alanlardan oluşmaz ve
elle çevrilir.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

from ..core.events import Event, FusionCompleted


def event_to_dict(event: Event) -> dict[str, object]:
    """Olayı `{"olay": <sınıf adı>, ...alanlar}` biçiminde sözlüğe çevir."""
    if isinstance(event, FusionCompleted):
        return {"olay": "FusionCompleted", **_result_to_dict(event)}
    payload: dict[str, object] = {"olay": type(event).__name__}
    if dataclasses.is_dataclass(event):
        for field in dataclasses.fields(event):
            payload[field.name] = _plain(getattr(event, field.name))
    return payload


def _result_to_dict(event: FusionCompleted) -> dict[str, object]:
    """`FusionResult`'ın uygulamanın ihtiyaç duyduğu alanlarını döndür."""
    result = event.result
    return {
        "gorev": result.task,
        "gorev_tipi": result.task_type,
        "kazanan": result.winner,
        "cevap": result.final_answer,
        "kaynak": result.source.value,
        "aday_sayisi": len(result.candidates),
    }


def _plain(value: object) -> object:
    """Değeri JSON'a uygun hale getir; desteklenmeyen tipte açıkça dur."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, type):
        raise TypeError(f"Olay alanı sınıf nesnesi taşıyor: {value!r}")
    if dataclasses.is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name)) for field in dataclasses.fields(value)
        }
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if hasattr(value, "value"):  # Enum
        return _plain(value.value)
    raise TypeError(f"Olay alanı JSON'a çevrilemiyor: {type(value).__name__}")
