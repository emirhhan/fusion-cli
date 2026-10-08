"""Hazır config ve gerçek model seçimini aynı süreçte sır taşımadan bağlar.

Kurulum açık modül nesneleriyle yapılır; loader, ortam, vault veya sağlayıcı
çağrısı yoktur. Bu saf bağlayıcı sürücüye kendiliğinden bağlanmaz.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Protocol, cast

from evals.effective_config import EffectiveConfigProof, EffectiveField, project_effective
from evals.engine_proof import ImportedEngineProof
from fusion_cli.config.models import Config
from fusion_cli.core.types import ModelSpec


class SessionAPI(Protocol):
    run_agent_task: Callable[..., object]


class SelectionAPI(Protocol):
    select_agent_spec: Callable[..., object]


@dataclass(frozen=True, slots=True)
class ConfigReceipt:
    """Import kanıtına bağlı gerçek seçim; auth/cache/context bilinmiyor kalır."""

    schema_version: int
    pid: int
    source_digest: str
    requested_revision: str
    revision_provenance: str
    effective: EffectiveConfigProof


class ConfigObserver:
    """Her async görevde ayrı bağlam; orijinal seçimi değiştirmez."""

    def __init__(
        self,
        proof: ImportedEngineProof,
        current_pid: Callable[[], int],
        emit: Callable[[ConfigReceipt], None],
    ) -> None:
        pid = current_pid()
        if isinstance(pid, bool) or not isinstance(pid, int) or pid != proof.pid:
            raise ValueError("Efektif ayar kanıtı aynı süreçte olmalı.")
        if (
            not re.fullmatch(r"[a-fA-F0-9]{64}", proof.source_digest)
            or not re.fullmatch(r"[a-fA-F0-9]{40}", proof.requested_revision)
            or proof.bootstrap_compatible is not True
            or proof.revision_provenance != "unverified"
        ):
            raise ValueError("Efektif ayar import kanıtı geçersiz.")
        self._proof = proof
        self._pid = current_pid
        self._emit = emit
        self._scope: ContextVar[tuple[object, str] | None] = ContextVar(
            "fusion_effective_config", default=None
        )

    def wrap_run(self, original: Callable[..., object]) -> Callable[..., object]:
        signature = _signature(original, {"config", "task_type"})

        @wraps(original)
        async def run(*args: object, **kwargs: object) -> object:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            task_type = bound.arguments["task_type"]
            if not isinstance(task_type, str):
                raise ValueError("Görev tipi metin olmalı.")
            token = self._scope.set((bound.arguments["config"], task_type))
            try:
                return await cast(Awaitable[object], original(*args, **kwargs))
            finally:
                self._scope.reset(token)

        return run

    def wrap_select(self, original: Callable[..., object]) -> Callable[..., object]:
        signature = _signature(original, {"config", "task_type"})

        @wraps(original)
        def select(*args: object, **kwargs: object) -> object:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            scope = self._scope.get()
            if scope is not None:
                config, task_type = scope
                if (
                    bound.arguments["config"] is not config
                    or bound.arguments["task_type"] != task_type
                ):
                    raise ValueError("Gerçek seçim görev config/tipiyle eşleşmiyor.")
                if self._pid() != self._proof.pid:
                    raise ValueError("Efektif ayar süreci değişti.")
            result = original(*args, **kwargs)
            if scope is not None:
                config, task_type = scope
                self._emit(
                    ConfigReceipt(
                        1,
                        self._proof.pid,
                        self._proof.source_digest,
                        self._proof.requested_revision,
                        self._proof.revision_provenance,
                        project_effective(cast(Config, config), cast(ModelSpec, result), task_type),
                    )
                )
            return result

        return select


def _signature(original: Callable[..., object], required: set[str]) -> inspect.Signature:
    if not callable(original):
        raise ValueError("Efektif ayar API'si desteklenmiyor.")
    signature = inspect.signature(original)
    if not required <= signature.parameters.keys():
        raise ValueError("Efektif ayar API parametreleri desteklenmiyor.")
    return signature


@dataclass(slots=True)
class ConfigBinding:
    """Yalnız kendi kurduğu wrapper'ları geri alır; sonraki kurulumu bozmaz."""

    session: SessionAPI
    engine: SelectionAPI
    original_run: Callable[..., object]
    original_select: Callable[..., object]
    wrapped_run: Callable[..., object]
    wrapped_select: Callable[..., object]

    def close(self) -> None:
        if self.session.run_agent_task is self.wrapped_run:
            self.session.run_agent_task = self.original_run
        if self.engine.select_agent_spec is self.wrapped_select:
            self.engine.select_agent_spec = self.original_select


def install(observer: ConfigObserver, session: SessionAPI, engine: SelectionAPI) -> ConfigBinding:
    """İki açık API'yi önce doğrula; unsupported kaynakta kısmi kurulum yapma."""
    original_run = getattr(session, "run_agent_task", None)
    original_select = getattr(engine, "select_agent_spec", None)
    if not callable(original_run) or not callable(original_select):
        raise ValueError("Efektif ayar API'si desteklenmiyor.")
    wrapped_run = observer.wrap_run(original_run)
    wrapped_select = observer.wrap_select(original_select)
    binding = ConfigBinding(
        session, engine, original_run, original_select, wrapped_run, wrapped_select
    )
    session.run_agent_task = wrapped_run
    engine.select_agent_spec = wrapped_select
    return binding


def validate_wire(raw: object, proof: ImportedEngineProof) -> ConfigReceipt:
    """Tel kanıtını kimlik, izinli alan türü ve kanonik özetle doğrula."""
    keys = {
        "schema_version",
        "pid",
        "source_digest",
        "requested_revision",
        "revision_provenance",
        "effective",
    }
    if not isinstance(raw, dict) or set(raw) != keys:
        raise ValueError("Efektif kanıt alanları geçersiz.")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("Efektif kanıt sürümü geçersiz.")
    if type(raw["pid"]) is not int or raw["pid"] != proof.pid:
        raise ValueError("Efektif kanıt süreç kimliği geçersiz.")
    for name in ("source_digest", "requested_revision", "revision_provenance"):
        if raw[name] != getattr(proof, name):
            raise ValueError("Efektif kanıt kaynak kimliği geçersiz.")
    return ConfigReceipt(
        1,
        proof.pid,
        proof.source_digest,
        proof.requested_revision,
        proof.revision_provenance,
        _wire_snapshot(raw["effective"]),
    )


def _wire_snapshot(value: object) -> EffectiveConfigProof:
    import hashlib
    import json
    import math

    effective_keys = {
        "schema_version",
        "fields",
        "missing_fields",
        "digest",
        "authentication_status",
        "cache_initial_state",
        "dynamic_context_status",
    }
    if not isinstance(value, dict) or set(value) != effective_keys:
        raise ValueError("Efektif snapshot sözleşmesi geçersiz.")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Efektif snapshot sürümü geçersiz.")
    if any(
        value[name] != "unknown"
        for name in ("authentication_status", "cache_initial_state", "dynamic_context_status")
    ):
        raise ValueError("Bilinmeyen dinamik durum doğrulanmış sayılamaz.")
    if not isinstance(value["fields"], list) or not value["fields"]:
        raise ValueError("Efektif alan listesi boş/geçersiz.")
    fields = tuple(_wire_field(item, math.isfinite) for item in value["fields"])
    if tuple(sorted(fields, key=lambda item: item.path)) != fields or len(
        {item.path for item in fields}
    ) != len(fields):
        raise ValueError("Efektif alan sırası/yinelenmesi geçersiz.")
    missing = tuple(item.path for item in fields if item.kind == "missing")
    if value["missing_fields"] != list(missing):
        raise ValueError("Efektif eksik alan listesi tutarsız.")
    canonical = [(item.path, item.kind, item.value, item.count) for item in fields]
    digest = hashlib.sha256(
        json.dumps(
            {"schema": 1, "fields": canonical},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    if value["digest"] != digest:
        raise ValueError("Efektif snapshot özeti eşleşmiyor.")
    return EffectiveConfigProof(1, fields, missing, digest)


def _wire_field(raw: object, finite: Callable[[float], bool]) -> EffectiveField:
    from evals.effective_config import (
        EffectiveField,
    )

    if not isinstance(raw, dict) or set(raw) != {"path", "kind", "value", "count"}:
        raise ValueError("Efektif alan sözleşmesi geçersiz.")
    path, kind, value, count = (raw[name] for name in ("path", "kind", "value", "count"))
    if not isinstance(kind, str):
        raise ValueError("Efektif alan tür adı metin olmalı.")
    _check_path(path)
    if kind not in {"missing", "absent"} and kind != _path_kind(path):
        raise ValueError("Efektif alan türü yoluyla eşleşmiyor.")
    if count is not None and (type(count) is not int or count < 0):
        raise ValueError("Efektif alan sayısı geçersiz.")
    if kind in {"missing", "absent"}:
        valid = value is None and count is None
    elif kind == "flag":
        valid = type(value) is bool and count is None
    elif kind in {"count", "number"}:
        try:
            valid = (value is None and path == "runtime.agent_max_steps") or (
                type(value) in {int, float}
                and finite(value)
                and value >= 0
                and (kind != "count" or type(value) is int)
            )
        except OverflowError as error:
            raise ValueError("Efektif sayı sonlu değil.") from error
        valid = valid and count is None
    else:
        valid = (
            kind
            in {"enum_digest", "text_digest", "strings_digest", "numbers_digest", "mapping_digest"}
            and isinstance(value, str)
            and re.fullmatch(r"[a-f0-9]{64}", value) is not None
            and type(count) is int
        )
    if not valid:
        raise ValueError("Efektif alan türü/değeri geçersiz.")
    return EffectiveField(path, kind, value, count)


def _check_path(path: object) -> None:
    from evals.effective_config import _COUNTS, _ENUMS, _FLAGS, _NUMBERS, _TEXT_LISTS

    allowed = {
        "runtime",
        "candidates",
        "candidates.count",
        "task_type",
        "task_model_map",
        "embedding.provider",
        "embedding.model",
    }
    allowed.update(
        "runtime." + name
        for name in (
            *_COUNTS,
            *_ENUMS,
            *_FLAGS,
            *_NUMBERS,
            *_TEXT_LISTS,
            "provider",
            "retry_delays_s",
            "rate_limit_per_minute",
        )
    )
    if not isinstance(path, str) or not (
        path in allowed
        or re.fullmatch(
            r"(agent|judge|vision|teacher|selected_agent|candidates\.[0-9]+)(\.(name|model|tags|fallback))?",
            path,
        )
    ):
        raise ValueError("Efektif alan yolu izinli değil.")


def _path_kind(path: str) -> str:
    from evals.effective_config import _COUNTS, _ENUMS, _FLAGS, _NUMBERS, _TEXT_LISTS

    if path == "candidates.count":
        return "count"
    if path.startswith("runtime."):
        name = path.removeprefix("runtime.")
        for names, kind in (
            (_COUNTS, "count"),
            (_NUMBERS, "number"),
            (_FLAGS, "flag"),
            (_ENUMS, "enum_digest"),
            (_TEXT_LISTS, "strings_digest"),
        ):
            if name in names:
                return kind
        return {
            "provider": "text_digest",
            "retry_delays_s": "numbers_digest",
            "rate_limit_per_minute": "mapping_digest",
        }[name]
    if path == "task_model_map":
        return "mapping_digest"
    if path.endswith((".tags", ".fallback")):
        return "strings_digest"
    return "text_digest"
