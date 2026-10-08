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

from evals.effective_config import EffectiveConfigProof, project_effective
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
