"""Yalan başarı ölçümü ve Faz 7 kabul eşikleri.

Eşikler 17 Eylül yol haritasından gelir: doğru tur oranı %70 üstü, yalan başarı
0, oturum tamamlanması tam, ortalama tur 90 saniyenin altı. Testler ağsızdır;
sahte gözlem (`TaskExecution`) kullanır.
"""

from __future__ import annotations

from pathlib import Path

from evals.acceptance import evaluate
from evals.criteria import evaluate_criterion
from evals.execution import TaskExecution
from evals.metrics import RunReport, TaskResult, merge_runs, score_task
from evals.report import report_from_dict, report_to_dict
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

_RESEARCH_ROOT = Path(__file__).resolve().parents[1]


def _task(task_id: str = "t", kind: CriterionKind = CriterionKind.FILE_CHANGED) -> EvalTask:
    return EvalTask(
        id=task_id,
        request="istek",
        criterion=SuccessCriterion(kind=kind, expected_path="a.py"),
    )


def _sonuc(task_id: str, *, basarili: bool, yalan: bool = False, sure: float = 1.0) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        success=basarili,
        first_attempt_success=basarili,
        retries=0,
        model_calls=1,
        duration_seconds=sure,
        passes=1 if basarili else 0,
        false_success=yalan,
    )


# --------------------------------------------------------------------------- #
# Olumsuz ölçütler
# --------------------------------------------------------------------------- #


def test_file_unchanged_dosya_degismediyse_basarili():
    olcut = SuccessCriterion(kind=CriterionKind.FILE_UNCHANGED, expected_path="gizli.txt")

    assert evaluate_criterion(olcut, TaskExecution(task_id="t")) is True


def test_file_unchanged_dosya_degistiyse_basarisiz():
    olcut = SuccessCriterion(kind=CriterionKind.FILE_UNCHANGED, expected_path="gizli.txt")
    gozlem = TaskExecution(task_id="t", changed_files=frozenset({"gizli.txt"}))

    assert evaluate_criterion(olcut, gozlem) is False


def test_workspace_unchanged_hicbir_dosya_yoksa_basarili():
    """Sohbet turu çalışma alanına dokunmamalı (B1)."""
    olcut = SuccessCriterion(kind=CriterionKind.WORKSPACE_UNCHANGED)

    assert evaluate_criterion(olcut, TaskExecution(task_id="t")) is True


def test_workspace_unchanged_herhangi_bir_dosyada_basarisiz():
    """Hangi adı seçtiği önemli değil: yazdıysa kaldı."""
    olcut = SuccessCriterion(kind=CriterionKind.WORKSPACE_UNCHANGED)
    gozlem = TaskExecution(task_id="t", changed_files=frozenset({"beklenmeyen.md"}))

    assert evaluate_criterion(olcut, gozlem) is False


# --------------------------------------------------------------------------- #
# Yalan başarı
# --------------------------------------------------------------------------- #


def test_agent_bitti_dedi_ama_olcut_tutmadiysa_yalan_basaridir():
    gozlem = TaskExecution(task_id="t", claimed_success=True, changed_files=frozenset())

    assert score_task(_task(), gozlem).false_success is True


def test_agent_bitirmediyse_yalan_basari_degildir():
    """Adım sınırına dayanan ya da hata veren tur bitirdiğini iddia etmiyor."""
    gozlem = TaskExecution(task_id="t", claimed_success=False, changed_files=frozenset())

    assert score_task(_task(), gozlem).false_success is False


def test_kota_yuzunden_olculemeyen_tur_yalan_basari_degildir():
    """Sağlayıcı turu kesmişse agent'ın yeteneği hiç ölçülmemiştir."""
    gozlem = TaskExecution(task_id="t", claimed_success=True, rate_limited=True)

    assert score_task(_task(), gozlem).false_success is False


def test_basarili_gorev_yalan_basari_sayilmaz():
    gozlem = TaskExecution(task_id="t", claimed_success=True, changed_files=frozenset({"a.py"}))

    sonuc = score_task(_task(), gozlem)
    assert sonuc.success is True
    assert sonuc.false_success is False


def test_tekrarlarda_tek_yalan_basari_bile_gorevi_isaretler():
    """Eşiği sıfır olan metrik çoğunluğa yuvarlanamaz."""
    birlesik = merge_runs([_sonuc("t", basarili=True), _sonuc("t", basarili=False, yalan=True)])

    assert birlesik.false_success is True


def test_yalan_basari_rapora_yazilir_ve_geri_okunur():
    rapor = RunReport(results=(_sonuc("t", basarili=False, yalan=True),))

    geri = report_from_dict(report_to_dict(rapor))

    assert geri.false_success_tasks == ("t",)
    assert report_to_dict(rapor)["summary"]["false_success_count"] == 1


# --------------------------------------------------------------------------- #
# Kabul eşikleri
# --------------------------------------------------------------------------- #


def test_esikleri_gecen_kosu_kabul_edilir():
    rapor = RunReport(results=tuple(_sonuc(f"t{i}", basarili=True) for i in range(10)))

    assert evaluate(rapor).passed is True


def test_tek_yalan_basari_kosuyu_dusurur():
    """Başarı oranı yüksek olsa bile yalan başarı eşiği sıfırdır."""
    sonuclar = [_sonuc(f"t{i}", basarili=True) for i in range(9)]
    sonuclar.append(_sonuc("yalanci", basarili=False, yalan=True))
    rapor = RunReport(results=tuple(sonuclar))

    hukum = evaluate(rapor)

    assert hukum.passed is False
    assert [k.name for k in hukum.failures] == ["yalan başarı"]
    assert "yalanci" in hukum.checks[1].detail


def test_yetmis_yuzdenin_altindaki_basari_dusurur():
    sonuclar = [_sonuc(f"t{i}", basarili=i < 6) for i in range(10)]

    hukum = evaluate(RunReport(results=tuple(sonuclar)))

    assert hukum.passed is False
    assert "doğru tur oranı" in [k.name for k in hukum.failures]


def test_tam_yetmis_yuzde_yeterli_degildir():
    """Eşik '%70 üstü'; tam %70 geçmez."""
    sonuclar = [_sonuc(f"t{i}", basarili=i < 7) for i in range(10)]

    assert evaluate(RunReport(results=tuple(sonuclar))).passed is False


def test_uzun_turlar_kosuyu_dusurur():
    sonuclar = [_sonuc(f"t{i}", basarili=True, sure=120.0) for i in range(10)]

    hukum = evaluate(RunReport(results=tuple(sonuclar)))

    assert hukum.passed is False
    assert "ortalama tur süresi" in [k.name for k in hukum.failures]


def test_kotaya_takilan_tur_oturumu_tamamlanmamis_sayar():
    """'21/21 tamamlanma' ölçütü: ölçülemeyen tur oturumu böler."""
    sonuclar = [_sonuc(f"t{i}", basarili=True) for i in range(9)]
    kesilen = TaskResult(
        task_id="kesilen",
        success=False,
        first_attempt_success=False,
        retries=0,
        model_calls=0,
        duration_seconds=0.0,
        passes=0,
        rate_limited=True,
    )
    rapor = RunReport(results=(*sonuclar, kesilen))

    hukum = evaluate(rapor)

    assert rapor.measured_task_count == 9
    assert hukum.passed is False
    assert "oturum tamamlanması" in [k.name for k in hukum.failures]


async def test_research_pilot_reference_and_seed_negative_controls(tmp_path):
    """İlk sekiz gerçek dosya görevinin bağımsız kabulü ve negatif kontrolü."""
    import json

    from evals.executor import AgentRunObservation, AgentTaskExecutor
    from evals.loader import load_tasks

    root = _RESEARCH_ROOT
    fixtures = root / "evals/fixtures/fusion_research"
    pilots = {"T01", "T02", "T05", "T06", "T07", "T09", "T10", "T11"}
    tasks = tuple(
        task
        for suite in ("dev", "validation")
        for task in load_tasks(root / f"evals/suite/fusion-research-{suite}.yaml")
        if task.id in pilots
    )
    assert {task.id for task in tasks} == pilots

    class LocalRunner:
        def __init__(self, use_reference):
            self.use_reference = use_reference

        async def run(self, request, *, root, **kwargs):
            task_id = root.name
            assert not (root / "acceptance.json").exists()
            assert not (root / "reference").exists()
            if self.use_reference:
                reference = fixtures / task_id / "reference"
                for source in reference.rglob("*"):
                    if source.is_file():
                        target = root / source.relative_to(reference).with_suffix("")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(source.read_bytes())
                response = (fixtures / task_id / "response.txt").read_text()
            else:
                response = ""
            return AgentRunObservation(response, 0)

    class Clock:
        def monotonic(self):
            return 0.0

    for task in tasks:
        for use_reference in (False, True):
            execution = await AgentTaskExecutor(
                LocalRunner(use_reference), workspace_root=tmp_path, clock=Clock()
            ).run(task)
            assert (execution.exit_code == 0) is use_reference, (task.id, execution)
    manifest = json.loads((fixtures / "manifest.json").read_text())
    assert len(manifest["tasks"]) == 32
    assert manifest["live_baseline"] is None


async def test_research_remaining_file_references_and_negatives(tmp_path):

    from evals.executor import AgentRunObservation, AgentTaskExecutor
    from evals.loader import load_tasks

    root = _RESEARCH_ROOT
    fixtures = root / "evals/fixtures/fusion_research"
    expected = {"T12", "T14", "T29", "T30", "T31", "T32"}
    tasks = tuple(
        task
        for split in ("dev", "validation", "blind")
        for task in load_tasks(root / f"evals/suite/fusion-research-{split}.yaml")
        if task.id in expected
    )
    assert {task.id for task in tasks} == expected

    class Runner:
        def __init__(self, reference, weaken=False):
            self.reference = reference
            self.weaken = weaken

        async def run(self, request, *, root, **kwargs):
            if self.reference:
                reference = fixtures / root.name / "reference"
                for source in reference.rglob("*"):
                    if source.is_file():
                        target = root / source.relative_to(reference).with_suffix("")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(source.read_bytes())
                if self.weaken:
                    (root / "test_calcul.py").write_text("assert True\n")
            return AgentRunObservation("tamam", 0)

    class Clock:
        def monotonic(self):
            return 0.0

    for task in tasks:
        for reference in (False, True):
            execution = await AgentTaskExecutor(
                Runner(reference),
                workspace_root=tmp_path,
                clock=Clock(),
            ).run(task)
            assert (execution.exit_code == 0) is reference, (task.id, execution)
        if task.id == "T14":
            execution = await AgentTaskExecutor(
                Runner(True, weaken=True),
                workspace_root=tmp_path,
                clock=Clock(),
            ).run(task)
            assert execution.exit_code != 0


def test_research_manifest_freezes_split_assets_and_setup_bytes():
    import hashlib
    import json

    from evals.loader import load_tasks

    fixtures = _RESEARCH_ROOT / "evals/fixtures/fusion_research"
    manifest = json.loads((fixtures / "manifest.json").read_text())
    records = manifest["tasks"]
    assert [
        sum(record["split"] == split for record in records)
        for split in ("development", "validation", "blind")
    ] == [16, 8, 8]
    assert len({record["id"] for record in records}) == 32
    tasks = {
        task.id: task
        for split in ("dev", "validation", "blind")
        for task in load_tasks(_RESEARCH_ROOT / f"evals/suite/fusion-research-{split}.yaml")
    }
    assert len(tasks) == 32
    for record in records:
        if record["id"] not in tasks:
            assert record["status"] == "pending-runtime-scenario"
            continue
        for relative, expected in record["asset_digests"].items():
            assert hashlib.sha256((fixtures / relative).read_bytes()).hexdigest() == expected
        for source in (fixtures / record["id"] / "seed").rglob("*.asset"):
            relative = source.relative_to(fixtures / record["id"] / "seed").with_suffix("")
            assert tasks[record["id"]].setup[str(relative)].encode() == source.read_bytes()
