"""Görev yürütücü — bir EvalTask'ı agent'la izole bir çalışma dizininde koşturur.

Her görev, boş (ya da bir tohumdan kopyalanmış) taze bir çalışma dizininde çalışır;
görevler birbirini kirletmez. Yürütücü şunları gözlemler:

- **değişen dosyalar** — çalışma öncesi/sonrası içerik özeti karşılaştırılır,
- **çıktı metni** — agent'ın nihai cevabı (keyword ölçütü için),
- **çıkış kodu** — EXIT_CODE ölçütünde, görev sonrası çalıştırılan `command`'ın kodu,
- **süre / model çağrısı** — metrikler için.

Asıl agent bir `AgentRunner` protokolünün arkasındadır: gerçek çalıştırma modeli çağırır
(ağ), ama yürütücünün gözlem mantığı sahte bir koşucuyla ağsız test edilir.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from evals.execution import TaskExecution
from evals.tasks import CriterionKind, EvalTask
from fusion_cli.core.constants import SHELL_TIMEOUT_S
from fusion_cli.core.errors import EvalError

#: Her koşunun çalışma dizinine bırakılan transkript dosyası. Çalışma dizini
#: koşu başına silinip yeniden kurulduğu için son koşunun transkripti kalır.
TRANSCRIPT_NAME = "_transkript.jsonl"


@dataclass(frozen=True, slots=True)
class AgentRunObservation:
    """Bir agent çalıştırmasından yürütücüye dönen gözlem."""

    output_text: str
    model_calls: int
    #: Sağlayıcı kotası yüzünden tur ölçülemedi mi?
    rate_limited: bool = False
    #: Kota hatasının ham metni (günlük kota / geçici sınır ayrımı için).
    rate_limit_detail: str = ""


class AgentRunner(Protocol):
    """Bir isteği belirli bir kök dizinde agent'la çalıştıran taraf."""

    async def run(
        self,
        request: str,
        *,
        root: Path,
        strict_approval: bool = False,
        transcript: Path | None = None,
    ) -> AgentRunObservation: ...


class Clock(Protocol):
    """Süre ölçümü için monoton saat (testte sahte verilebilir)."""

    def monotonic(self) -> float: ...


class AgentTaskExecutor:
    """Bir EvalTask'ı izole çalışma dizininde koşturup gözlemleri toplar."""

    def __init__(
        self,
        agent_runner: AgentRunner,
        *,
        workspace_root: Path,
        clock: Clock,
        seed_dir: Path | None = None,
    ) -> None:
        self._agent_runner = agent_runner
        self._workspace_root = workspace_root
        self._clock = clock
        self._seed_dir = seed_dir

    async def run(self, task: EvalTask) -> TaskExecution:
        workspace = self._prepare_workspace(task.id, task.setup)
        before = _snapshot(workspace)

        start = self._clock.monotonic()
        observation = await self._agent_runner.run(
            task.request,
            root=workspace,
            strict_approval=task.approval == "strict",
            transcript=workspace / TRANSCRIPT_NAME,
        )
        duration = self._clock.monotonic() - start

        changed = _changed_files(before, _snapshot(workspace))
        exit_code = await self._exit_code(task, workspace)

        return TaskExecution(
            task_id=task.id,
            exit_code=exit_code,
            changed_files=frozenset(changed),
            output_text=observation.output_text,
            rate_limited=observation.rate_limited,
            rate_limit_detail=observation.rate_limit_detail,
            model_calls=observation.model_calls,
            retries=0,
            duration_seconds=duration,
        )

    # ----------------------------------------------------------------------- #

    def _prepare_workspace(self, task_id: str, setup: Mapping[str, str] | None = None) -> Path:
        workspace = self._workspace_root / task_id
        if workspace.exists():
            shutil.rmtree(workspace)
        if self._seed_dir is not None:
            shutil.copytree(self._seed_dir, workspace)
        else:
            workspace.mkdir(parents=True)
        for relative, content in (setup or {}).items():
            _write_seed_file(workspace, relative, content)
        return workspace

    async def _exit_code(self, task: EvalTask, workspace: Path) -> int | None:
        if task.criterion.kind is not CriterionKind.EXIT_CODE or not task.criterion.command:
            return None
        try:
            process = await asyncio.create_subprocess_shell(
                task.criterion.command,
                cwd=str(workspace),
                env=_verification_env(),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return 1
        try:
            return await asyncio.wait_for(process.wait(), timeout=SHELL_TIMEOUT_S)
        except TimeoutError:
            process.kill()
            await process.wait()
            return 1


def _verification_env() -> dict[str, str]:
    """Doğrulama komutunun ortamı: PATH'e ÇALIŞAN yorumlayıcının dizini eklenir.

    Görev ölçütleri `python -c "..."` yazıyor ama `python` her sistemde PATH'te
    değildir (venv, `python3`-only kurulumlar). Ölçüldü: bu haliyle her exit_code
    görevi 127 (command not found) dönüyordu — yani ölçüt hiç çalışmadan "kaldı"
    sayılıyor, görev seti sessizce yalan söylüyordu.
    """
    env = dict(os.environ)
    yorumlayici = str(Path(sys.executable).parent)
    env["PATH"] = f"{yorumlayici}{os.pathsep}{env.get('PATH', '')}"

    # Post-run acceptance komutları scratch workspace'ten çalışır. `evals` paketi
    # wheel'in parçası değildir; repo kökünü yalnız DOĞRULAMA subprocess'ine ekle.
    # Agent'ın ToolContext kökü değişmez, dolayısıyla evaluator kaynaklarını göremez
    # veya değiştiremez.
    repo_root = str(Path(__file__).resolve().parents[1])
    mevcut_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{repo_root}{os.pathsep}{mevcut_pythonpath}"
        if mevcut_pythonpath
        else repo_root
    )
    return env


def _write_seed_file(workspace: Path, relative: str, content: str) -> None:
    """Başlangıç dosyasını çalışma dizinine yaz.

    Görev seti bir GİRDİDİR (dosyadan gelir, paylaşılabilir); `../` ile depoya ya
    da ev dizinine yazmasına izin verilemez. Yol çözülür ve çalışma dizini altında
    kalması zorunlu tutulur.
    """
    target = (workspace / relative).resolve()
    root = workspace.resolve()
    if root not in target.parents:
        raise EvalError(f"setup yolu çalışma dizini dışına çıkıyor: {relative}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _snapshot(root: Path) -> dict[str, str]:
    """Dizindeki tüm dosyaların göreli yol → içerik özeti eşlemesi."""
    snapshot: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root))
        snapshot[relative] = _hash_file(path)
    return snapshot


def _changed_files(before: dict[str, str], after: dict[str, str]) -> set[str]:
    """Eklenen ya da içeriği değişen dosyaların göreli yolları."""
    return {path for path, digest in after.items() if before.get(path) != digest}


def _hash_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        # Okunamayan dosya "değişti" sayılsın diye benzersiz bir işaret döndür.
        return "unreadable"
