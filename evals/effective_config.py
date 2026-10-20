"""Çözülmüş ayardan sır taşımayan saf karşılaştırma kanıtı üretir.

Bu modül yapılandırma yüklemez, ortam/dosya/kimlik deposuna erişmez. Kaynak
revizyonların dinamik provider context'i, authentication ve cache başlangıcı
bu kanıttan çıkarılamaz; açıkça bilinmiyor kalır.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from fusion_cli.config.models import Config
from fusion_cli.core.types import ModelSpec


@dataclass(frozen=True, slots=True)
class EffectiveField:
    """Serbest metin yerine özet; sayısal ayarlar açık ve tipli kalır."""

    path: str
    kind: str
    value: str | bool | int | float | None
    count: int | None = None


@dataclass(frozen=True, slots=True)
class EffectiveConfigProof:
    """Yalnız izinli alanların sürümlü, kanonik kanıtı."""

    schema_version: int
    fields: tuple[EffectiveField, ...]
    missing_fields: tuple[str, ...]
    digest: str
    authentication_status: str = "unknown"
    cache_initial_state: str = "unknown"
    dynamic_context_status: str = "unknown"


_NUMBERS = (
    "request_timeout_s",
    "temperature",
    "judge_temperature",
    "utility_temperature",
    "judge_timeout_s",
    "circuit_cooldown_s",
    "reliability_alpha",
    "straggler_grace_s",
    "candidate_hard_cap_s",
    "rate_pace_max_wait_s",
)
_COUNTS = (
    "max_retries",
    "max_tokens",
    "judge_max_tokens",
    "circuit_failure_threshold",
    "min_successful_candidates",
    "agent_max_steps",
    "agent_max_idle_rounds",
    "agent_teacher_takeover_tools",
    "model_retry_attempts",
    "workflow_max_model_calls",
    "workflow_planning_calls",
    "workflow_step_calls",
    "workflow_recovery_calls",
    "workflow_final_verification_calls",
    "workflow_attempt_calls",
    "max_parallel_agents",
)
_FLAGS = (
    "self_review",
    "reflexion",
    "lessons",
    "teacherless",
    "teacher_lesson_sync",
    "gateway_cache",
    "gateway_compression",
    "gateway_mask_secrets",
    "web_verification",
    "browser_verification",
    "visual_verification",
    "playbooks",
    "verified_synthesis",
    "synthesis",
    "restrict_to_root",
)
_ENUMS = ("reasoning_effort", "routing_strategy", "workflow_mode")
_TEXT_LISTS = ("disabled_tools", "verification_commands", "post_edit_commands")
_MISSING = object()


def _digest(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _number(value: object, *, integer: bool = False, optional: bool = False) -> int | float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Efektif sayısal alan geçersiz.")
    if integer and not isinstance(value, int):
        raise ValueError("Efektif sayaç tam sayı olmalı.")
    try:
        finite = math.isfinite(value)
    except OverflowError as error:
        raise ValueError("Efektif sayısal alan sonlu olmalı.") from error
    if not finite or value < 0:
        raise ValueError("Efektif sayısal alan sonlu ve negatif olmayan değer olmalı.")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Efektif metin alanı geçersiz.")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple | list) or not all(isinstance(item, str) for item in value):
        raise ValueError("Efektif metin dizisi geçersiz.")
    return tuple(_text(item) for item in value)


def _entry(path: str, value: object, kind: str) -> EffectiveField:
    if value is _MISSING:
        return EffectiveField(path, "missing", None)
    if kind == "count":
        return EffectiveField(
            path, kind, _number(value, integer=True, optional=path.endswith("agent_max_steps"))
        )
    if kind == "number":
        return EffectiveField(path, kind, _number(value))
    if kind == "flag":
        if not isinstance(value, bool):
            raise ValueError("Efektif bayrak boolean olmalı.")
        return EffectiveField(path, kind, value)
    if kind == "enum":
        if not isinstance(value, Enum):
            raise ValueError("Efektif enum alanı geçersiz.")
        return EffectiveField(path, "enum_digest", _digest(_text(value.value)), 1)
    if kind == "text":
        return EffectiveField(path, "text_digest", _digest(_text(value)), 1)
    if kind == "strings":
        texts = _strings(value)
        return EffectiveField(path, "strings_digest", _digest(texts), len(texts))
    if kind == "numbers":
        if not isinstance(value, tuple | list):
            raise ValueError("Efektif sayı dizisi geçersiz.")
        numbers = tuple(_number(item) for item in value)
        return EffectiveField(path, "numbers_digest", _digest(numbers), len(numbers))
    raise ValueError("Efektif alan türü bilinmiyor.")


def _field(owner: object, name: str, path: str, kind: str) -> EffectiveField:
    # Alan adları yalnız yukarıdaki sabit listelerden gelir; genel keşif yapılmaz.
    return _entry(path, getattr(owner, name, _MISSING), kind)


def _model(owner: object, prefix: str) -> tuple[EffectiveField, ...]:
    if owner is _MISSING:
        return (EffectiveField(prefix, "missing", None),)
    if owner is None:
        return (EffectiveField(prefix, "absent", None),)
    return tuple(
        _field(owner, name, f"{prefix}.{name}", kind)
        for name, kind in (
            ("name", "text"),
            ("model", "text"),
            ("tags", "strings"),
            ("fallback", "strings"),
        )
    )


def _mapping_field(value: object, path: str, *, numeric: bool = False) -> EffectiveField:
    if value is _MISSING:
        return EffectiveField(path, "missing", None)
    if not isinstance(value, Mapping):
        raise ValueError("Efektif eşleme alanı geçersiz.")
    entries = [
        (_text(key), _number(item) if numeric else _text(item)) for key, item in value.items()
    ]
    return EffectiveField(path, "mapping_digest", _digest(sorted(entries)), len(entries))


def _runtime(owner: object) -> tuple[EffectiveField, ...]:
    if owner is _MISSING:
        return (EffectiveField("runtime", "missing", None),)
    fields = [
        _field(owner, name, f"runtime.{name}", kind)
        for names, kind in (
            (_NUMBERS, "number"),
            (_COUNTS, "count"),
            (_FLAGS, "flag"),
            (_ENUMS, "enum"),
            (_TEXT_LISTS, "strings"),
        )
        for name in names
    ]
    fields.extend(
        (
            _field(owner, "provider", "runtime.provider", "text"),
            _field(owner, "retry_delays_s", "runtime.retry_delays_s", "numbers"),
            _mapping_field(
                getattr(owner, "rate_limit_per_minute", _MISSING),
                "runtime.rate_limit_per_minute",
                numeric=True,
            ),
        )
    )
    return tuple(fields)


def project_effective(
    config: Config, selected_agent: ModelSpec, task_type: str
) -> EffectiveConfigProof:
    """Hazır dataclass'ı özetle; hiçbir yapılandırma veya dinamik durum yükleme."""
    fields = list(_runtime(getattr(config, "runtime", _MISSING)))
    fields.extend(_model(selected_agent, "selected_agent"))
    fields.append(_entry("task_type", task_type, "text"))
    for name in ("agent", "judge", "vision", "teacher"):
        fields.extend(_model(getattr(config, name, _MISSING), name))
    candidates = getattr(config, "candidates", _MISSING)
    if candidates is _MISSING:
        fields.append(EffectiveField("candidates", "missing", None))
    elif isinstance(candidates, tuple | list):
        fields.append(EffectiveField("candidates.count", "count", len(candidates)))
        for index, candidate in enumerate(candidates):
            fields.extend(_model(candidate, f"candidates.{index}"))
    else:
        raise ValueError("Efektif model havuzu geçersiz.")
    fields.append(_mapping_field(getattr(config, "task_model_map", _MISSING), "task_model_map"))
    embedding = getattr(config, "embedding", _MISSING)
    for name in ("provider", "model"):
        fields.append(_field(embedding, name, f"embedding.{name}", "text"))
    ordered = tuple(sorted(fields, key=lambda item: item.path))
    missing = tuple(item.path for item in ordered if item.kind == "missing")
    canonical = [(item.path, item.kind, item.value, item.count) for item in ordered]
    return EffectiveConfigProof(1, ordered, missing, _digest({"schema": 1, "fields": canonical}))
