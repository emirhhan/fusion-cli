"""JSONL satırlarını yeniden olaya çevirir.

`JsonRenderer` olayları düz sözlüğe indiriyor; teşhis ve tekrar oynatma için ters
yön de gerekiyor. Dönüşüm TOLERANSLIDIR: tanınmayan olay adı, eksik alan ya da
fazladan anahtar satırı düşürür, koşuyu değil. Teşhis aracının kendisi kırılgan
olursa hata anında elde hiçbir şey kalmaz.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from enum import Enum
from typing import Any, cast

from ..core import events as event_module
from ..core.events import Channel, Event, ToolOutcome
from ..core.evidence import CriterionEvidence, EvidenceEnvironment, EvidenceStatus
from ..core.execution_plan import VerificationCheckKind
from ..core.types import ModelResult, ParseWarning, TokenUsage, ToolCall
from ..core.web_provenance import load_web_provenance

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
    try:
        for field in dataclasses.fields(tip):
            if field.name not in payload:
                continue
            kwargs[field.name] = _coerce(field.name, payload[field.name])
    except (TypeError, ValueError):
        return None
    # Olay kurucuları alan alan farklı tip ister; değerler yukarıda alan adına göre
    # geri kuruldu, uyumsuzluk aşağıdaki TypeError ile yakalanır.
    kurucu: Callable[..., Event] = tip
    try:
        return kurucu(**kwargs)
    except (TypeError, ValueError):
        return None


def _coerce(name: str, value: object) -> object:
    """Alan adına göre bilinen tipleri geri kur, gerisini olduğu gibi bırak."""
    if name == "outcome" and isinstance(value, str):
        return _enum(ToolOutcome, value)
    if name == "channel" and isinstance(value, str):
        # Enum değeri (`"main"`) olarak yazılır; geri çevrilmezse `event.channel is
        # Channel.MAIN` hep yanlış çıkar ve tüm akış metni tüketiciden kaybolur.
        return _enum(Channel, value)
    if name == "criteria":
        return _criteria(value)
    if name == "result" and isinstance(value, dict):
        return _model_result(value)
    if isinstance(value, list):
        return _tuple_ic_ice(value)
    return value


def _tuple_ic_ice(value: list[object]) -> tuple[object, ...]:
    """Listeyi demete çevir; iç içe listeler de demet olur (`FollowupsSuggested.items`)."""
    return tuple(_tuple_ic_ice(item) if isinstance(item, list) else item for item in value)


def _model_result(payload: dict[str, object]) -> ModelResult | dict[str, object]:
    """Model sonucunu geri kur; tanınmayan alanlar atılır."""
    alanlar = {field.name for field in dataclasses.fields(ModelResult)}
    kwargs = {key: payload[key] for key in payload if key in alanlar}
    kwargs["usage"] = _token_usage(payload.get("usage"))
    # Araç çağrıları eskiden buradan ATILIYORDU. Olay geri geliyordu ama içi
    # boşalmış oluyordu: araç kullanan bir turun kaydı, o turu yeniden
    # üretemiyordu ve kayıp sessizdi (çağrı sayısı 1 → 0).
    kwargs["tool_calls"] = _tool_calls(payload.get("tool_calls"))
    kwargs["parse_warnings"] = _parse_warnings(payload.get("parse_warnings"))
    try:
        kwargs["web_provenance"] = load_web_provenance(payload.get("web_provenance"))
        return ModelResult(**cast("Any", kwargs))
    except (TypeError, ValueError):
        return payload


def _parse_warnings(value: object) -> tuple[ParseWarning, ...]:
    """Yalnız tipli uyarıları geri kur; eski kayıtlar boş demet üretir."""
    if not isinstance(value, (list, tuple)):
        return ()
    warnings: list[ParseWarning] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        kind, message = item.get("kind"), item.get("message")
        index = item.get("call_index")
        blocks = item.get("blocks_mutation", True)
        if not isinstance(kind, str) or not isinstance(message, str):
            continue
        if index is not None and (not isinstance(index, int) or isinstance(index, bool)):
            continue
        if not isinstance(blocks, bool):
            continue
        warnings.append(ParseWarning(kind, message, index, blocks))
    return tuple(warnings)


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
    # Ölçüm bayrakları da geri kurulur: yoksa tekrar oynatılan kullanım "ölçülmemiş" görünür.
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=float(cost_usd),
        prompt_measured=value.get("prompt_measured") is True,
        completion_measured=value.get("completion_measured") is True,
        cost_known=value.get("cost_known") is True,
    )


def _enum(tip: type[Enum], value: str) -> object:
    try:
        return tip(value)
    except ValueError:
        return value


def _criteria(value: object) -> tuple[CriterionEvidence, ...]:
    """Aday trace kanıtını aynı reducer'ın beklediği frozen türlerle geri kur."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("Kriter kanıtı dizi olmalı.")
    return tuple(_criterion(item) for item in value)


def _criterion(value: object) -> CriterionEvidence:
    if not isinstance(value, dict):
        raise ValueError("Kriter kanıtı nesne olmalı.")
    fields = {field.name for field in dataclasses.fields(CriterionEvidence)}
    kwargs = {key: item for key, item in value.items() if key in fields}
    for key, item in kwargs.items():
        if key in {"behavioral", "applicable"}:
            if not isinstance(item, bool):
                raise ValueError("Kriter kanıtı bayrağı boolean olmalı.")
        elif key != "environment" and not isinstance(item, str):
            raise ValueError("Kriter kanıtı alanı metin olmalı.")
    kind, status = value.get("kind"), value.get("status")
    if not isinstance(kind, str) or not isinstance(status, str):
        raise ValueError("Kriter kanıtı türü ve durumu metin olmalı.")
    kwargs["kind"] = VerificationCheckKind(kind)
    kwargs["status"] = EvidenceStatus(status)
    kwargs["environment"] = _evidence_environment(value.get("environment"))
    constructor: Callable[..., CriterionEvidence] = CriterionEvidence
    return constructor(**kwargs)


def _evidence_environment(value: object) -> EvidenceEnvironment | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Kanıt ortamı nesne olmalı.")
    names = {field.name for field in dataclasses.fields(EvidenceEnvironment)}
    if any(not isinstance(value.get(name), str) for name in names):
        raise ValueError("Kanıt ortamı alanları metin olmalı.")
    constructor: Callable[..., EvidenceEnvironment] = EvidenceEnvironment
    return constructor(**{name: value[name] for name in names})
