"""Yalan başarı ölçümü ve Faz 7 kabul eşikleri.

Eşikler 17 Eylül yol haritasından gelir: doğru tur oranı %70 üstü, yalan başarı
0, oturum tamamlanması tam, ortalama tur 90 saniyenin altı. Testler ağsızdır;
sahte gözlem (`TaskExecution`) kullanır.
"""

from __future__ import annotations

from evals.acceptance import evaluate
from evals.criteria import evaluate_criterion
from evals.execution import TaskExecution
from evals.metrics import RunReport, TaskResult, merge_runs, score_task
from evals.report import report_from_dict, report_to_dict
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion


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
    gozlem = TaskExecution(
        task_id="t", claimed_success=True, changed_files=frozenset({"a.py"})
    )

    sonuc = score_task(_task(), gozlem)
    assert sonuc.success is True
    assert sonuc.false_success is False


def test_tekrarlarda_tek_yalan_basari_bile_gorevi_isaretler():
    """Eşiği sıfır olan metrik çoğunluğa yuvarlanamaz."""
    birlesik = merge_runs(
        [_sonuc("t", basarili=True), _sonuc("t", basarili=False, yalan=True)]
    )

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
