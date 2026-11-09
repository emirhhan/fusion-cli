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
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from evals.acceptance_command import AcceptanceCommand, plan_acceptance
from evals.execution import ModelCallIdentity, TaskExecution
from evals.interactions import InteractionMetrics
from evals.research_evidence import prepare_acceptance_evidence
from evals.research_runtime import RUNTIME_RECEIPT, RuntimeReceipt
from evals.tasks import CriterionKind, EvalTask
from fusion_cli.core.constants import SHELL_TIMEOUT_S
from fusion_cli.core.errors import EvalError
from fusion_cli.core.events import Event
from fusion_cli.core.evidence import EvidenceEnvironment

#: Her koşunun çalışma dizinine bırakılan transkript dosyası. Çalışma dizini
#: koşu başına silinip yeniden kurulduğu için son koşunun transkripti kalır.
TRANSCRIPT_NAME = "_transkript.jsonl"
#: Doğrulama komutu ÇALIŞTIRILAMADI/zaman aşımına uğradı: gerçek bir çıkış kodu değildir. Eskiden
#: ikisi de `1` dönüyor, altyapı arızası "ajan başarısız" sayılıyor ve `expected_exit_code=1`
#: bekleyen görev yanlışlıkla geçiyordu (Q1-18). Negatif sentinel hiçbir beklenenle eşleşmez.
EXIT_VERIFICATION_TIMEOUT = -1
EXIT_VERIFICATION_UNAVAILABLE = -2
ACCEPTANCE_STDOUT_NAME = "_acceptance.stdout.txt"
ACCEPTANCE_STDERR_NAME = "_acceptance.stderr.txt"
#: Harness'in kendi bıraktığı kanıt dosyaları: agent'ın işi sayılmaz.
#:
#: Ölçüldü (30 Ekim, Q1-03): transkript koşu sırasında çalışma dizininde
#: yaratılıyor ve "değişen dosya" sayılıyordu; agent hiçbir şey yazmasa bile
#: `workspace_unchanged` ölçütü (parite setinde 5 görev) başarısız çıkıyordu.
#: Yalnız bu üç AD dışlanır; agent'ın yazdığı `_`-önekli dosyalar sayılmaya devam eder.
_HARNESS_EVIDENCE = frozenset({TRANSCRIPT_NAME, ACCEPTANCE_STDOUT_NAME, ACCEPTANCE_STDERR_NAME})


@dataclass(frozen=True, slots=True)
class AgentRunObservation:
    """Bir agent çalıştırmasından yürütücüye dönen gözlem."""

    output_text: str
    model_calls: int
    #: Turda açılan KURTARMA turu sayısı (`ExecutionRetryScheduled`).
    #:
    #: Sağlayıcı arızasından gelen yedek-zincir geçişi ve araç sözleşmesi onarımı
    #: BURAYA girmez: üçü ayrı arıza sınıfıdır ve tek sayıda toplanınca altyapı
    #: arızası ajan başarısızlığı gibi okunur.
    retries: int = 0
    #: Sağlayıcı kotası yüzünden tur ölçülemedi mi?
    rate_limited: bool = False
    #: Kota hatasının ham metni (günlük kota / geçici sınır ayrımı için).
    rate_limit_detail: str = ""
    #: Agent turu BİTTİĞİNİ beyan etti mi?
    #
    # "Yalan başarı" ölçümünün girdisi: agent temiz bitirdiğini söylediği hâlde
    # ölçüt tutmuyorsa, bu sıradan bir başarısızlık değildir — kullanıcıya iş
    # bitti denmiştir. Kota hatası ve adım sınırına dayanma beyan SAYILMAZ:
    # ikisinde de agent bitirdiğini iddia etmiyor.
    claimed_success: bool = True
    calls: tuple[ModelCallIdentity, ...] = ()
    trace_events: tuple[Event, ...] = ()
    runtime_receipt: RuntimeReceipt | None = None
    environments: tuple[EvidenceEnvironment, ...] = ()
    effective_config_digest: str | None = None
    interactions: InteractionMetrics | None = None


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
        runner_factory: Callable[[EvalTask, int], AgentRunner] | None = None,
    ) -> None:
        self._agent_runner = agent_runner
        self._workspace_root = workspace_root.resolve()
        self._clock = clock
        self._seed_dir = seed_dir
        self._runner_factory = runner_factory
        self.executions: list[TaskExecution] = []

    async def run(self, task: EvalTask) -> TaskExecution:
        return await self.run_sample(task, sample_index=None)

    async def run_sample(self, task: EvalTask, *, sample_index: int | None) -> TaskExecution:
        acceptance = plan_acceptance(task.criterion.command or "true")
        workspace = self._prepare_workspace(task.id, task.setup, sample_index=sample_index)
        before = _snapshot(workspace)

        start = self._clock.monotonic()
        with tempfile.TemporaryDirectory(prefix="fusion-clean-acceptance-") as directory:
            clean = Path(directory) / "workspace"
            shutil.copytree(workspace, clean)
            return await self._run_candidate(
                task, workspace, clean, before, start, acceptance, sample_index=sample_index
            )

    async def _run_candidate(
        self,
        task: EvalTask,
        workspace: Path,
        clean: Path,
        before: dict[str, str],
        start: float,
        acceptance: AcceptanceCommand,
        *,
        sample_index: int | None,
    ) -> TaskExecution:
        runner = (
            self._runner_factory(task, sample_index or 1)
            if self._runner_factory
            else self._agent_runner
        )
        observation = await runner.run(
            task.request,
            root=workspace,
            strict_approval=task.approval == "strict",
            transcript=workspace / TRANSCRIPT_NAME,
        )
        duration = self._clock.monotonic() - start

        changed = _changed_files(before, _snapshot(workspace))
        _apply_candidate(workspace, clean, changed, acceptance.frozen_inputs | {RUNTIME_RECEIPT})
        (clean / "_candidate_changes.json").write_text(
            json.dumps(sorted(changed), ensure_ascii=False), encoding="utf-8"
        )
        (clean / "_agent_response.txt").write_text(observation.output_text, encoding="utf-8")
        environment = await prepare_acceptance_evidence(
            clean, task, acceptance, observation.runtime_receipt
        )
        exit_code = await self._exit_code(task, clean, acceptance)
        if exit_code in {EXIT_VERIFICATION_TIMEOUT, EXIT_VERIFICATION_UNAVAILABLE}:
            environment = None
        for name in (ACCEPTANCE_STDOUT_NAME, ACCEPTANCE_STDERR_NAME):
            if (clean / name).is_file():
                shutil.copyfile(clean / name, workspace / name)

        execution = TaskExecution(
            sample_index=sample_index if sample_index is not None else 1,
            interactions=observation.interactions,
            effective_config_digest=observation.effective_config_digest,
            environments=observation.environments + ((environment,) if environment else ()),
            runtime_receipt=observation.runtime_receipt,
            calls=observation.calls,
            trace_events=observation.trace_events,
            task_id=task.id,
            exit_code=exit_code,
            changed_files=frozenset(changed),
            output_text=observation.output_text,
            rate_limited=observation.rate_limited,
            rate_limit_detail=observation.rate_limit_detail,
            model_calls=observation.model_calls,
            retries=observation.retries,
            claimed_success=observation.claimed_success,
            duration_seconds=duration,
        )
        self.executions.append(execution)
        return execution

    # ----------------------------------------------------------------------- #

    def _prepare_workspace(
        self,
        task_id: str,
        setup: Mapping[str, str] | None = None,
        *,
        sample_index: int | None = None,
    ) -> Path:
        if not task_id or Path(task_id).name != task_id or task_id in {".", ".."}:
            raise EvalError("Görev kimliği tek bir güvenli dizin adı olmalı.")
        workspace = self._workspace_root / task_id
        if workspace.is_symlink() or not workspace.resolve().is_relative_to(
            self._workspace_root.resolve()
        ):
            raise EvalError("Görev çalışma dizini kök dışına çıkamaz.")
        if sample_index is not None:
            workspace = workspace / f"run-{sample_index:02d}"
        if workspace.exists():
            shutil.rmtree(workspace)
        if self._seed_dir is not None:
            _snapshot(self._seed_dir)
            shutil.copytree(self._seed_dir, workspace)
        else:
            workspace.mkdir(parents=True)
        for relative, content in (setup or {}).items():
            _write_seed_file(workspace, relative, content)
        return workspace

    async def _exit_code(
        self, task: EvalTask, workspace: Path, acceptance: AcceptanceCommand
    ) -> int | None:
        if task.criterion.kind is not CriterionKind.EXIT_CODE or not task.criterion.command:
            return None
        if acceptance.command is None:
            _write_acceptance_evidence(
                workspace, b"", (acceptance.unavailable_reason or "").encode("utf-8")
            )
            return EXIT_VERIFICATION_UNAVAILABLE
        try:
            process = await asyncio.create_subprocess_shell(
                acceptance.command,
                cwd=str(workspace),
                env=_verification_env(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError:
            return EXIT_VERIFICATION_UNAVAILABLE
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=SHELL_TIMEOUT_S)
        except TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
            _write_acceptance_evidence(workspace, stdout, stderr)
            return EXIT_VERIFICATION_TIMEOUT
        _write_acceptance_evidence(workspace, stdout, stderr)
        return process.returncode


def _write_acceptance_evidence(workspace: Path, stdout: bytes, stderr: bytes) -> None:
    (workspace / ACCEPTANCE_STDOUT_NAME).write_text(
        stdout.decode("utf-8", errors="replace"), encoding="utf-8"
    )
    (workspace / ACCEPTANCE_STDERR_NAME).write_text(
        stderr.decode("utf-8", errors="replace"), encoding="utf-8"
    )


def _verification_env() -> dict[str, str]:
    """Doğrulama komutunun ortamı: PATH'e ÇALIŞAN yorumlayıcının dizini eklenir.

    Görev ölçütleri `python -c "..."` yazıyor ama `python` her sistemde PATH'te
    değildir (venv, `python3`-only kurulumlar). Ölçüldü: bu haliyle her exit_code
    görevi 127 (command not found) dönüyordu — yani ölçüt hiç çalışmadan "kaldı"
    sayılıyor, görev seti sessizce yalan söylüyordu.
    """
    env = dict(os.environ)
    env["PYTHONOPTIMIZE"] = "0"
    env["PYTHONSAFEPATH"] = "1"
    yorumlayici = str(Path(sys.executable).parent)
    env["PATH"] = f"{yorumlayici}{os.pathsep}{env.get('PATH', '')}"

    # Post-run acceptance komutları scratch workspace'ten çalışır. `evals` paketi
    # wheel'in parçası değildir; repo kökünü yalnız DOĞRULAMA subprocess'ine ekle.
    # Agent'ın ToolContext kökü değişmez, dolayısıyla evaluator kaynaklarını göremez
    # veya değiştiremez.
    repo_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join((repo_root, str(Path(repo_root) / "src")))
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
    target.write_text(content, encoding="utf-8", newline="\n")


def _snapshot(root: Path) -> dict[str, str]:
    """Dizindeki tüm dosyaların göreli yol → içerik özeti eşlemesi."""
    snapshot: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise EvalError("Değerlendirme çalışma dizini sembolik bağlantı içeremez.")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in _HARNESS_EVIDENCE:
            continue
        snapshot[relative] = _hash_file(path)
    return snapshot


def _changed_files(before: dict[str, str], after: dict[str, str]) -> set[str]:
    """Eklenen ya da içeriği değişen dosyaların göreli yolları."""
    return {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}


def _hash_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        # Okunamayan dosya "değişti" sayılsın diye benzersiz bir işaret döndür.
        return "unreadable"


def _is_acceptance_asset(relative: str) -> bool:
    """Tohumdaki test ve test çalıştırma ayarları adaydan bağımsız kalır."""
    path = Path(relative)
    return (
        any(part in {"tests", "test", ".pytest_cache", "__pycache__"} for part in path.parts)
        or path.name.startswith(("test_", "test."))
        or ".test." in path.name
        or ".spec." in path.name
        or path.name.endswith("_test.py")
        or path.name in {"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"}
    )


def _apply_candidate(
    workspace: Path, clean: Path, changed: set[str], frozen_inputs: frozenset[str]
) -> None:
    """Aday ürün farkını temiz tohumu bozmadan uygula; test farkını aktarma."""
    for relative in sorted(changed):
        if _is_acceptance_asset(relative) or any(
            relative == name or Path(name) in Path(relative).parents for name in frozen_inputs
        ):
            continue
        source = workspace / relative
        target = clean / relative
        parts = [
            workspace.joinpath(*Path(relative).parts[:index])
            for index in range(1, len(Path(relative).parts) + 1)
        ]
        if any(part.is_symlink() for part in parts):
            raise EvalError(f"Aday farkı sembolik bağlantı içeremez: {relative}")
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        elif target.is_file():
            target.unlink()
