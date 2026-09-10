"""JSONL satırlarını yeniden olaya çevirir.

`JsonRenderer` olayları düz sözlüğe indiriyor; teşhis ve tekrar oynatma için ters
yön de gerekiyor. Dönüşüm TOLERANSLIDIR: tanınmayan olay adı, eksik alan ya da
fazladan anahtar satırı düşürür, koşuyu değil. Teşhis aracının kendisi kırılgan
olursa hata anında elde hiçbir şey kalmaz.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, cast

from ..core import events as event_module
from ..core.events import Event, ToolOutcome
from ..core.types import ModelResult, TokenUsage, ToolCall

#: Ada göre olay sınıfları — tek kaynak `core.events` modülüdür.
_EVENT_TYPES: dict[str, type[Event]] = {
    name: value
    for name, value in vars(event_module).items()
    if isinstance(value, type) and issubclass(value, Event) and value is not Event
}


def event_from_payload(payload: object) -> Event | None:
    """Tek bir JSONL sözlüğünü olaya çevir; çeviremezse `None`."""
    if not isinstance(payload, dict):
        return None
    name = payload.get("event")
    if not isinstance(name, str):
        return None
    tip = _EVENT_TYPES.get(name)
    if tip is None:
        return None
    kwargs: dict[str, object] = {}
    for field in dataclasses.fields(tip):
        if field.name not in payload:
            continue
        kwargs[field.name] = _coerce(field.name, payload[field.name])
    try:
        return tip(**kwargs)
    except (TypeError, ValueError):
        return None


def _coerce(name: str, value: object) -> object:
    """Alan adına göre bilinen tipleri geri kur, gerisini olduğu gibi bırak."""
    if name == "outcome" and isinstance(value, str):
        return _enum(ToolOutcome, value)
    if name == "result" and isinstance(value, dict):
        return _model_result(value)
    if isinstance(value, list):
        return tuple(value)
    return value


def _model_result(payload: dict[str, object]) -> ModelResult | dict[str, object]:
    """Model sonucunu geri kur; tanınmayan alanlar atılır."""
    alanlar = {field.name for field in dataclasses.fields(ModelResult)}
    kwargs = {key: payload[key] for key in payload if key in alanlar}
    kwargs["usage"] = _token_usage(payload.get("usage"))
    # Araç çağrıları eskiden buradan ATILIYORDU. Olay geri geliyordu ama içi
    # boşalmış oluyordu: araç kullanan bir turun kaydı, o turu yeniden
    # üretemiyordu ve kayıp sessizdi (çağrı sayısı 1 → 0).
    kwargs["tool_calls"] = _tool_calls(payload.get("tool_calls"))
    try:
        return ModelResult(**cast("Any", kwargs))
    except (TypeError, ValueError):
        return payload


def _tool_calls(value: object) -> tuple[ToolCall, ...]:
    """Kayıttaki araç çağrılarını geri kur.

    Modül genelindeki TOLERANS burada da geçerlidir: eksik alanlı ya da biçimi
    bozuk tek bir çağrı yalnız KENDİSİNİ düşürür, olayın tamamını değil. Teşhis
    aracı elde hiçbir şey bırakmamaktansa eksik kayıt vermelidir.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    kurulan: list[ToolCall] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        cagri_id, name, arguments = item.get("id"), item.get("name"), item.get("arguments")
        if not (isinstance(cagri_id, str) and isinstance(name, str) and isinstance(arguments, str)):
            continue
        kurulan.append(ToolCall(id=cagri_id, name=name, arguments=arguments))
    return tuple(kurulan)


def _token_usage(value: object) -> TokenUsage:
    """Kayıttaki token ve maliyet muhasebesini toleranslı biçimde geri kur."""
    if not isinstance(value, dict):
        return TokenUsage()
    prompt_tokens = value.get("prompt_tokens")
    completion_tokens = value.get("completion_tokens")
    cost_usd = value.get("cost_usd")
    if not (
        isinstance(prompt_tokens, int)
        and not isinstance(prompt_tokens, bool)
        and isinstance(completion_tokens, int)
        and not isinstance(completion_tokens, bool)
        and isinstance(cost_usd, (int, float))
        and not isinstance(cost_usd, bool)
    ):
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=float(cost_usd),
    )


def _enum(tip: type[Enum], value: str) -> object:
    try:
        return tip(value)
    except ValueError:
        return value
