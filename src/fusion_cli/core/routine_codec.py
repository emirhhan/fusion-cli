"""Plan bildirimi ile checkpoint için tek rutin tanımı çözücüsü."""

from __future__ import annotations

import json
from dataclasses import asdict

from .execution_plan import RoutineDefinition


def decode_routine(raw: object) -> RoutineDefinition | None:
    """Eski boş tanımı koru; bozuk ve bilinmeyen alanı reddet."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != {"input_schema", "preconditions", "checks"}:
        raise ValueError("Rutin tanımı şema, önkoşul ve kontrol alanlarını içermeli.")
    schema = raw["input_schema"]
    if not isinstance(schema, str):
        raise ValueError("Rutin girdi şeması JSON metni olmalı.")
    parsed = json.loads(schema)
    if not isinstance(parsed, dict) or parsed.get("type") != "object":
        raise ValueError("Rutin girdi şeması nesne olmalı.")
    roles = []
    for name in ("preconditions", "checks"):
        values = raw[name]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value.strip() for value in values)
            or len(set(values)) != len(values)
        ):
            raise ValueError("Rutin koşulları boş olmayan benzersiz kimlikler olmalı.")
        roles.append(tuple(values))
    if set(roles[0]) & set(roles[1]):
        raise ValueError("Rutin önkoşulu ve son kontrolü ayrı olmalı.")
    return RoutineDefinition(schema, roles[0], roles[1])


def encode_routine(routine: RoutineDefinition | None) -> dict[str, object] | None:
    """Tek checkpoint kaydında taşınacak JSON görünümü."""
    return asdict(routine) if routine is not None else None
