"""Seçilmiş model önkontrolünün araç kısıtı ve açık sürücü komutu.

Araçlar boşaltılır; öğretmen/öğrenim/cache kalıcı durumunun yan etkisiz olduğu
iddia edilmez. Config, model, fallback ve retry ayarları değiştirilmez.
"""

from __future__ import annotations

import contextlib
import inspect
import os
import signal
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Protocol, cast


@dataclass(frozen=True, slots=True)
class ProbeEvidence:
    """Geçici receipt silinse de raporda sır taşımayan kimlik kanıtı kalır."""

    pid: int
    source_digest: str
    config_digests: tuple[str, ...]
    requested_revision: str
    revision_provenance: str = "unverified"
    authentication_status: str = "unknown"
    cache_initial_state: str = "unknown"
    dynamic_context_status: str = "unknown"
    persistent_state_unchanged: bool = False


class ProbeSession(Protocol):
    run_agent_task: Callable[..., object]


def install_probe_guard(session: ProbeSession) -> None:
    original = session.run_agent_task
    signature = inspect.signature(original)
    parameter = signature.parameters.get("allowed_tools")
    if parameter is None or parameter.kind is not inspect.Parameter.KEYWORD_ONLY:
        raise ValueError("Seçilmiş kaynak boş araçlı model önkontrolünü desteklemiyor.")
    if not inspect.iscoroutinefunction(original):
        raise ValueError("Seçilmiş önkontrol async görev API'si desteklenmiyor.")

    @wraps(original)
    async def run(*args: object, **kwargs: object) -> object:
        signature.bind(*args, **kwargs)
        kwargs["allowed_tools"] = set()
        return await cast(Awaitable[object], original(*args, **kwargs))

    session.run_agent_task = run


def probe_command(
    source: Path, manifest: Path, workspace: Path, task: str, timeout_s: float
) -> list[str]:
    evals_root = Path(__file__).resolve().parent.parent
    code = (
        f"import sys;sys.path.insert(0,{str(evals_root)!r});"
        "from evals.live_drive import main;main()"
    )
    return [
        sys.executable,
        "-c",
        code,
        "--kok",
        str(workspace.resolve()),
        "--gorev",
        task,
        "--sure",
        str(timeout_s),
        "--onay",
        "deny",
        "--engine-source",
        str(source.resolve()),
        "--engine-manifest",
        str(manifest.resolve()),
        "--engine-proof",
        str((workspace / "engine-proof.json").resolve()),
        "--model-probe",
    ]


def run_owned_probe(
    command: list[str], *, cwd: Path, env: dict[str, str], timeout: float
) -> subprocess.CompletedProcess[str]:
    """Yalnız yeni oturumdaki kendi süreç grubunu timeout/iptalde temizle."""
    from evals.driver_limits import DRIVER_GRACE_S

    if os.name != "posix":
        raise ValueError("Seçilmiş probe süreç grubu bu platformda desteklenmiyor.")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        # Grup kimliği yalnız start_new_session ile açılmış bu çocuğa aittir;
        # TERM'i yok sayan torunlar dahil, başka uygulama/süreç eşleştirilmez.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=DRIVER_GRACE_S)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
