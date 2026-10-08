"""Seçilmiş motorun açık host tarayıcısını bağlar; import/kurulum/render yapmaz.

Kaynak/PID receipt yetkisini çağıran doğrular. Bu adaptör verilen modüllerin
aynı kaynağa ve gerekli opsiyonel API'ye ait olduğunu ayrıca denetler.
"""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from evals.engine_proof import ImportedEngineProof

BrowserMode = Literal["headless-shell", "chrome-for-testing"]


@dataclass(frozen=True, slots=True)
class HostBrowserSelection:
    """Model/RPC dışında host tarafından verilen mevcut executable seçimi."""

    executable: Path
    mode: BrowserMode

    def __post_init__(self) -> None:
        path = self.executable
        if (
            self.mode not in ("headless-shell", "chrome-for-testing")
            or not path.is_absolute()
            or any(
                part.lower().startswith(".env")
                for item in (path, path.resolve())
                for part in item.parts
            )
            or not path.is_file()
            or not os.access(path, os.X_OK)
        ):
            raise ValueError("Host tarayıcı seçimi mevcut mutlak executable olmalı; fallback yok.")


class ObserverAPI(Protocol):
    __file__: str
    ExistingBrowser: Callable[..., object]
    observe_frame: Callable[..., Awaitable[object]]
    browser_transport: Callable[[object], Callable[[object], Awaitable[object]]]


class HostAPI(Protocol):
    __file__: str
    AppHostDependencies: Callable[..., object]


class EntryAPI(Protocol):
    __file__: str
    main: Callable[..., object]


def _check_api(api: object, expected: Path, function: object, **kwargs: object) -> None:
    source = getattr(api, "__file__", None)
    if not isinstance(source, str) or Path(source).resolve() != expected.resolve():
        raise ValueError("Host tarayıcı adaptörünün kaynak modülü seçilmiş motorla eşleşmiyor.")
    if not callable(function):
        raise ValueError("Seçilmiş motor host tarayıcı API'si desteklenmiyor.")
    try:
        inspect.signature(function).bind(**kwargs)
    except (TypeError, ValueError) as error:
        raise ValueError("Seçilmiş motor host tarayıcı API'si desteklenmiyor.") from error


def bind_browser(
    selection: HostBrowserSelection | None,
    proof: ImportedEngineProof | None,
    *,
    observer: ObserverAPI | None,
    host: HostAPI | None,
    entry: EntryAPI | None,
    process_id: int,
) -> object | None:
    """Tembel taşıma closure'ını seçilmiş AppHostDependencies içine koy."""
    if selection is None:
        return None
    if proof is None or proof.pid != process_id or proof.bootstrap_compatible is not True:
        raise ValueError("Host tarayıcı adaptörü aynı süreç import kanıtını gerektirir.")
    if observer is None or host is None or entry is None:
        raise ValueError("Seçilmiş motor host tarayıcı API'si desteklenmiyor.")
    for api, name in (
        (entry, "main"),
        (host, "AppHostDependencies"),
        (observer, "observe_frame"),
        (observer, "ExistingBrowser"),
        (observer, "browser_transport"),
    ):
        if not callable(getattr(api, name, None)):
            raise ValueError("Seçilmiş motor host tarayıcı API'si desteklenmiyor.")
    root = Path(proof.source_root) / "src/fusion_cli"
    _check_api(entry, root / "cli/app.py", entry.main, host_dependencies=None)
    _check_api(
        host,
        root / "cli/app_host.py",
        host.AppHostDependencies,
        remotion_transport=None,
        remotion_browser=None,
    )
    _check_api(
        observer,
        root / "tools/remotion_observe.py",
        observer.observe_frame,
        request=None,
        browser=None,
    )
    _check_api(
        observer,
        root / "tools/remotion_observe.py",
        observer.ExistingBrowser,
        executable=selection.executable,
        mode=selection.mode,
    )
    browser = observer.ExistingBrowser(executable=selection.executable, mode=selection.mode)

    transport = observer.browser_transport(browser)
    return host.AppHostDependencies(remotion_transport=transport, remotion_browser=browser)
