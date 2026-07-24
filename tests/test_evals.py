"""Ölçüm iskeletinin saf parçaları: ölçüt, metrik, karşılaştırma, serileştirme, yükleme.

Testler ağa/motora çıkmaz; sahte gözlem (`TaskExecution`) ve sahte yürütücü kullanır.
"""

from __future__ import annotations

import pytest
from evals.compare import compare_reports
from evals.criteria import evaluate_criterion
from evals.execution import TaskExecution
from evals.loader import load_tasks
from evals.metrics import RunReport, score_task
from evals.report import read_report, report_from_dict, report_to_dict, write_report
from evals.runner import run_suite
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

from fusion_cli.core.errors import EvalError


def _task(task_id: str, criterion: SuccessCriterion) -> EvalTask:
    return EvalTask(id=task_id, request="istek", criterion=criterion)


# --------------------------------------------------------------------------- #
# Ölçüt değerlendirmesi
# --------------------------------------------------------------------------- #


def test_exit_code_kriteri_eslesince_basarili():
    criterion = SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0)
    execution = TaskExecution(task_id="t", exit_code=0)
    assert evaluate_criterion(criterion, execution) is True


def test_exit_code_kriteri_farkli_kodda_basarisiz():
    criterion = SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0)
    execution = TaskExecution(task_id="t", exit_code=1)
    assert evaluate_criterion(criterion, execution) is False


def test_file_changed_kriteri_yol_degistiyse_basarili():
    criterion = SuccessCriterion(kind=CriterionKind.FILE_CHANGED, expected_path="a.py")
    execution = TaskExecution(task_id="t", changed_files=frozenset({"a.py", "b.py"}))
    assert evaluate_criterion(criterion, execution) is True


def test_file_changed_kriteri_yol_degismediyse_basarisiz():
    criterion = SuccessCriterion(kind=CriterionKind.FILE_CHANGED, expected_path="a.py")
    execution = TaskExecution(task_id="t", changed_files=frozenset({"b.py"}))
    assert evaluate_criterion(criterion, execution) is False


def test_keyword_kriteri_metinde_gecerse_basarili():
    criterion = SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="cosine")
    execution = TaskExecution(task_id="t", output_text="calculate_cosine_similarity")
    assert evaluate_criterion(criterion, execution) is True


def test_keyword_kriteri_metinde_gecmezse_basarisiz():
    criterion = SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="cosine")
    execution = TaskExecution(task_id="t", output_text="dosya yazıldı")
    assert evaluate_criterion(criterion, execution) is False


# --------------------------------------------------------------------------- #
# Görev puanlama ve metrik toplama
# --------------------------------------------------------------------------- #


def test_first_attempt_success_yeniden_deneme_yoksa_dogru():
    task = _task("t", SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0))
    result = score_task(task, TaskExecution(task_id="t", exit_code=0, retries=0))
    assert result.success is True
    assert result.first_attempt_success is True


def test_first_attempt_success_yeniden_denemeyle_yanlis():
    task = _task("t", SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0))
    result = score_task(task, TaskExecution(task_id="t", exit_code=0, retries=2))
    assert result.success is True
    assert result.first_attempt_success is False


def test_bos_rapor_oranlari_sifir():
    report = RunReport(results=())
    assert report.task_success_rate == 0.0
    assert report.first_attempt_success_rate == 0.0
    assert report.mean_model_calls == 0.0
    assert report.mean_duration_seconds == 0.0


def _sample_report() -> RunReport:
    exit_ok = SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0)
    results = (
        score_task(
            _task("a", exit_ok),
            TaskExecution(task_id="a", exit_code=0, retries=0, model_calls=2, duration_seconds=1.0),
        ),
        score_task(
            _task("b", exit_ok),
            TaskExecution(task_id="b", exit_code=1, retries=1, model_calls=4, duration_seconds=3.0),
        ),
    )
    return RunReport(results=results)


def test_metrik_toplama_orta_degerleri_dogru():
    report = _sample_report()
    assert report.task_count == 2
    assert report.task_success_rate == 0.5
    assert report.first_attempt_success_rate == 0.5
    assert report.total_retries == 1
    assert report.mean_model_calls == 3.0
    assert report.mean_duration_seconds == 2.0


# --------------------------------------------------------------------------- #
# Karşılaştırma
# --------------------------------------------------------------------------- #


def _report_from_success(mapping: dict[str, bool]) -> RunReport:
    exit_ok = SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0)
    results = tuple(
        score_task(
            _task(task_id, exit_ok),
            TaskExecution(task_id=task_id, exit_code=0 if success else 1),
        )
        for task_id, success in mapping.items()
    )
    return RunReport(results=results)


def test_karsilastirma_gerileme_ve_iyilesmeyi_ayirir():
    baseline = _report_from_success({"a": True, "b": False, "c": True})
    candidate = _report_from_success({"a": False, "b": True, "c": True})
    comparison = compare_reports(baseline, candidate)
    assert comparison.regressions == ("a",)
    assert comparison.improvements == ("b",)


def test_karsilastirma_yalniz_tek_tarafta_olan_gorevi_saymaz():
    baseline = _report_from_success({"a": True})
    candidate = _report_from_success({"b": False})
    comparison = compare_reports(baseline, candidate)
    assert comparison.regressions == ()
    assert comparison.improvements == ()


def test_karsilastirma_metrik_deltasi_dogru():
    baseline = _report_from_success({"a": False, "b": False})
    candidate = _report_from_success({"a": True, "b": True})
    comparison = compare_reports(baseline, candidate)
    success_delta = next(m for m in comparison.metrics if m.name == "task_success_rate")
    assert success_delta.baseline == 0.0
    assert success_delta.candidate == 1.0
    assert success_delta.delta == 1.0


# --------------------------------------------------------------------------- #
# Serileştirme (JSON tur turu)
# --------------------------------------------------------------------------- #


def test_rapor_json_tur_turu_korunur():
    report = _sample_report()
    restored = report_from_dict(report_to_dict(report))
    assert restored.results == report.results


def test_rapor_diske_yazilip_okununca_ayni(tmp_path):
    report = _sample_report()
    path = tmp_path / "rapor.json"
    write_report(report, path)
    restored = read_report(path)
    assert restored.results == report.results
    assert restored.task_success_rate == report.task_success_rate


# --------------------------------------------------------------------------- #
# Yükleme (YAML doğrulama)
# --------------------------------------------------------------------------- #


def _write_yaml(tmp_path, text: str):
    path = tmp_path / "set.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_gecerli_set_yuklenir(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
tasks:
  - id: t1
    request: bir dosya oluştur
    criterion:
      kind: file_changed
      expected_path: hello.py
  - id: t2
    request: testleri çalıştır
    criterion:
      kind: exit_code
      expected_exit_code: 0
""",
    )
    tasks = load_tasks(path)
    assert len(tasks) == 2
    assert tasks[0].criterion.expected_path == "hello.py"
    assert tasks[1].criterion.expected_exit_code == 0


def test_bilinmeyen_olcut_turu_reddedilir(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
tasks:
  - id: t1
    request: istek
    criterion:
      kind: uzayli_olcut
      keyword: x
""",
    )
    with pytest.raises(EvalError):
        load_tasks(path)


def test_eksik_alan_reddedilir(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
tasks:
  - id: t1
    criterion:
      kind: keyword
      keyword: x
""",
    )
    with pytest.raises(EvalError):
        load_tasks(path)


def test_yinelenen_kimlik_reddedilir(tmp_path):
    path = _write_yaml(
        tmp_path,
        """
tasks:
  - id: ayni
    request: a
    criterion: {kind: keyword, keyword: x}
  - id: ayni
    request: b
    criterion: {kind: keyword, keyword: y}
""",
    )
    with pytest.raises(EvalError):
        load_tasks(path)


def test_bos_tasks_reddedilir(tmp_path):
    path = _write_yaml(tmp_path, "tasks: []\n")
    with pytest.raises(EvalError):
        load_tasks(path)


def test_gercek_baslangic_seti_yuklenir():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "evals" / "suite" / "starter.yaml"
    tasks = load_tasks(path)
    assert len(tasks) >= 6
    assert all(task.id for task in tasks)


# --------------------------------------------------------------------------- #
# Runner (sahte yürütücüyle, ağsız)
# --------------------------------------------------------------------------- #


class _FakeExecutor:
    """Görev kimliğine göre önceden belirlenmiş gözlem döndüren sahte yürütücü."""

    def __init__(self, executions: dict[str, TaskExecution]) -> None:
        self._executions = executions
        self.calls: list[str] = []

    async def run(self, task: EvalTask) -> TaskExecution:
        self.calls.append(task.id)
        return self._executions[task.id]


async def test_runner_gorevleri_sirayla_kosturur_ve_puanlar():
    exit_ok = SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0)
    tasks = (_task("a", exit_ok), _task("b", exit_ok))
    executor = _FakeExecutor(
        {
            "a": TaskExecution(task_id="a", exit_code=0),
            "b": TaskExecution(task_id="b", exit_code=1),
        }
    )
    report = await run_suite(tasks, executor)
    assert executor.calls == ["a", "b"]
    assert report.task_success_rate == 0.5
