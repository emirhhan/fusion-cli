"""Eval yürütücüsü — gözlem mantığı sahte bir agent koşucusuyla ağsız test edilir.

Değişen dosya tespiti, çıktı taşınması, EXIT_CODE komutu, dizin izolasyonu ve tohum
dizini kopyalama doğrulanır. Gerçek agent (ağ) hiç çağrılmaz.
"""

from __future__ import annotations

from pathlib import Path

from evals.criteria import evaluate_criterion
from evals.executor import AgentRunObservation, AgentTaskExecutor
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion


class _FakeRunner:
    """Kök dizine önceden belirlenmiş dosyalar yazan ve sabit gözlem döndüren koşucu."""

    def __init__(
        self, *, files: dict[str, str] | None = None, output: str = "", model_calls: int = 1
    ) -> None:
        self._files = files or {}
        self._output = output
        self._model_calls = model_calls
        self.roots: list[Path] = []

    async def run(
        self,
        request: str,
        *,
        root: Path,
        strict_approval: bool = False,
        transcript: Path | None = None,
    ) -> AgentRunObservation:
        self.roots.append(root)
        for name, content in self._files.items():
            (root / name).write_text(content, encoding="utf-8")
        return AgentRunObservation(output_text=self._output, model_calls=self._model_calls)


class _FakeClock:
    def __init__(self, *times: float) -> None:
        self._times = list(times)

    def monotonic(self) -> float:
        return self._times.pop(0)


def _task(task_id: str, criterion: SuccessCriterion) -> EvalTask:
    return EvalTask(id=task_id, request="bir şey yap", criterion=criterion)


async def test_degisen_dosyalari_yakalar(tmp_path):
    runner = _FakeRunner(files={"hello.py": "print('x')"})
    executor = AgentTaskExecutor(runner, workspace_root=tmp_path, clock=_FakeClock(0.0, 1.0))
    task = _task("t", SuccessCriterion(kind=CriterionKind.FILE_CHANGED, expected_path="hello.py"))

    execution = await executor.run(task)
    assert "hello.py" in execution.changed_files
    assert evaluate_criterion(task.criterion, execution) is True


async def test_ciktiyi_ve_model_cagrisini_tasir(tmp_path):
    runner = _FakeRunner(output="uzantı .py olur", model_calls=3)
    executor = AgentTaskExecutor(runner, workspace_root=tmp_path, clock=_FakeClock(0.0, 1.0))
    task = _task("t", SuccessCriterion(kind=CriterionKind.KEYWORD, keyword=".py"))

    execution = await executor.run(task)
    assert execution.output_text == "uzantı .py olur"
    assert execution.model_calls == 3
    assert evaluate_criterion(task.criterion, execution) is True


async def test_sureyi_saatten_olcer(tmp_path):
    runner = _FakeRunner()
    executor = AgentTaskExecutor(runner, workspace_root=tmp_path, clock=_FakeClock(2.0, 5.5))
    execution = await executor.run(
        _task("t", SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="x"))
    )
    assert execution.duration_seconds == 3.5


async def test_exit_code_komutu_calistirir_basari(tmp_path):
    runner = _FakeRunner()
    executor = AgentTaskExecutor(runner, workspace_root=tmp_path, clock=_FakeClock(0.0, 1.0))
    task = _task(
        "t", SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0, command="true")
    )
    execution = await executor.run(task)
    assert execution.exit_code == 0
    assert evaluate_criterion(task.criterion, execution) is True


async def test_exit_code_komutu_calistirir_basarisiz(tmp_path):
    runner = _FakeRunner()
    executor = AgentTaskExecutor(runner, workspace_root=tmp_path, clock=_FakeClock(0.0, 1.0))
    task = _task(
        "t", SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0, command="false")
    )
    execution = await executor.run(task)
    assert execution.exit_code == 1
    assert evaluate_criterion(task.criterion, execution) is False


async def test_komutu_calisma_dizininde_kosturur(tmp_path):
    # Komut, agent'ın yazdığı dosyayı çalışma dizininde görmeli.
    runner = _FakeRunner(files={"hazir.txt": "var"})
    executor = AgentTaskExecutor(runner, workspace_root=tmp_path, clock=_FakeClock(0.0, 1.0))
    task = _task(
        "t",
        SuccessCriterion(
            kind=CriterionKind.EXIT_CODE, expected_exit_code=0, command="test -f hazir.txt"
        ),
    )
    execution = await executor.run(task)
    assert execution.exit_code == 0


async def test_gorevler_izole_dizinlerde_calisir(tmp_path):
    runner = _FakeRunner(files={"a.txt": "x"})
    executor = AgentTaskExecutor(runner, workspace_root=tmp_path, clock=_FakeClock(0, 1, 2, 3))
    await executor.run(_task("gorev1", SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="x")))
    await executor.run(_task("gorev2", SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="x")))
    # Her görev kendi alt dizinini aldı.
    assert runner.roots[0] != runner.roots[1]
    assert runner.roots[0].name == "gorev1"


async def test_tohum_dizini_kopyalanir_ve_degisiklik_sayilmaz(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "mevcut.txt").write_text("onceden burada", encoding="utf-8")
    workspace_root = tmp_path / "ws"

    runner = _FakeRunner(files={"yeni.txt": "eklendi"})
    executor = AgentTaskExecutor(
        runner, workspace_root=workspace_root, clock=_FakeClock(0.0, 1.0), seed_dir=seed
    )
    execution = await executor.run(
        _task("t", SuccessCriterion(kind=CriterionKind.FILE_CHANGED, expected_path="yeni.txt"))
    )
    # Tohum dosyası "değişti" sayılmaz; yalnızca agent'ın eklediği sayılır.
    assert execution.changed_files == frozenset({"yeni.txt"})
