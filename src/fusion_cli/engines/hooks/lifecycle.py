"""Kanca yaşam döngüsü gözlemi (#289 `--include-hook-events`).

Claude Code `-p --output-format stream-json --include-hook-events` her kanca komutu için
`system/hook_started` ve `system/hook_response` mesajları yayımlar. Fusion'da kancaları
`HookSession.emit` çalıştırır; bu modül her komutu gözlemcilere bildirerek çalıştırır.
Gözlemci yokken davranış `run_hook` ile aynıdır (ek iş yok).

Gözlemci listesi süreç düzeyindedir (başsız koşu tek süreçtir ve turlar iş parçacığı
değiştirebilir); `observe_hook_lifecycle` bağlam yöneticisi kaydı geri alır.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.hooks.events import HookCommand, HookEvent, HookRun
from .runner import run_hook

if TYPE_CHECKING:
    from .handlers import HookServices

HookObserver = Callable[[dict[str, object]], None]

_observers: list[HookObserver] = []

#: Claude `hook_response.outcome` değerleri.
OUTCOME_SUCCESS = "success"
OUTCOME_ERROR = "error"
OUTCOME_CANCELLED = "cancelled"


@contextmanager
def observe_hook_lifecycle(observer: HookObserver) -> Iterator[None]:
    """Blok süresince her kanca komutunun başlangıç/bitişini `observer`'a ver."""
    _observers.append(observer)
    try:
        yield
    finally:
        _observers.remove(observer)


def add_observer(observer: HookObserver) -> None:
    """Gözlemciyi kalıcı ekle; kapsamı `observer_scope` sınırlar (başsız koşu)."""
    _observers.append(observer)


@contextmanager
def observer_scope() -> Iterator[None]:
    """Blok içinde eklenen gözlemcileri blok bitince kaldır."""
    saved = list(_observers)
    try:
        yield
    finally:
        _observers[:] = saved


def hook_name(command: HookCommand, subjects: tuple[str, ...]) -> str:
    """Claude biçimi: `Olay:konu` (ör. `PreToolUse:Bash`, `SessionStart:startup`)."""
    subject = subjects[0] if subjects else ""
    return f"{command.event.value}:{subject}" if subject else command.event.value


def response_fields(run: HookRun) -> dict[str, object]:
    """`hook_response` gövdesi: çıktı, çıkış kodu ve sonuç (`success|error`)."""
    stderr = run.stderr
    if run.timed_out:
        stderr = stderr or "Hook timed out"
    elif run.error:
        stderr = stderr or run.error
    fields: dict[str, object] = {
        "output": run.stdout + stderr,
        "stdout": run.stdout,
        "stderr": stderr,
        "outcome": OUTCOME_SUCCESS if run.exit_code == 0 else OUTCOME_ERROR,
    }
    if run.exit_code is not None:
        fields["exit_code"] = run.exit_code
    return fields


def _notify(message: dict[str, object]) -> None:
    for observer in tuple(_observers):
        observer(dict(message))


async def run_observed(
    command: HookCommand,
    payload: Mapping[str, object],
    *,
    subjects: tuple[str, ...],
    cwd: Path,
    environment: Mapping[str, str],
    allow_private: bool = False,
    event: HookEvent | None = None,
    services: HookServices | None = None,
) -> HookRun:
    """`run_hook` + gözlemcilere `hook_started`/`hook_response` bildirimi."""
    if not _observers:
        return await run_hook(
            command,
            payload,
            cwd=cwd,
            environment=environment,
            allow_private=allow_private,
            event=event,
            services=services,
        )
    base: dict[str, object] = {
        "hook_id": uuid.uuid4().hex,
        "hook_name": hook_name(command, subjects),
        "hook_event": command.event.value,
    }
    _notify({"subtype": "hook_started", **base})
    try:
        run = await run_hook(
            command,
            payload,
            cwd=cwd,
            environment=environment,
            allow_private=allow_private,
            event=event,
            services=services,
        )
    except asyncio.CancelledError:
        _notify(
            {
                "subtype": "hook_response",
                **base,
                "output": "",
                "stdout": "",
                "stderr": "",
                "outcome": OUTCOME_CANCELLED,
            }
        )
        raise
    _notify({"subtype": "hook_response", **base, **response_fields(run)})
    return run
