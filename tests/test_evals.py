"""Ölçüm iskeletinin saf parçaları: ölçüt, metrik, karşılaştırma, serileştirme, yükleme.

Testler ağa/motora çıkmaz; sahte gözlem (`TaskExecution`) ve sahte yürütücü kullanır.
"""

from __future__ import annotations

import json

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


# --- Göreve başlangıç dosyası verme ------------------------------------------ #


def test_gorev_baslangic_dosyalari_tasiyabilir(tmp_path):
    """Bug fix ölçmek için bozuk kodun çalışma dizininde HAZIR olması gerekir.

    Başlangıç dosyası olmadan yalnızca "sıfırdan dosya oluştur" tipi görevler
    yazılabiliyordu; onları en zayıf model de geçer, yani ölçüm ayırt etmez.
    """
    from evals.loader import load_tasks

    yol = tmp_path / "set.yaml"
    yol.write_text(
        "tasks:\n"
        "  - id: bug-fix\n"
        "    request: hatayı düzelt\n"
        "    setup:\n"
        "      hesap.py: |\n"
        "        def topla(a, b):\n"
        "            return a - b\n"
        "    criterion:\n"
        "      kind: exit_code\n"
        "      expected_exit_code: 0\n"
        "      command: python -c \"import hesap; assert hesap.topla(1,2)==3\"\n",
        encoding="utf-8",
    )

    gorev = load_tasks(yol)[0]

    assert gorev.setup == {"hesap.py": "def topla(a, b):\n    return a - b\n"}


def test_setup_verilmezse_bos_kalir(tmp_path):
    from evals.loader import load_tasks

    yol = tmp_path / "set.yaml"
    yol.write_text(
        "tasks:\n"
        "  - id: x\n"
        "    request: y\n"
        "    criterion:\n"
        "      kind: keyword\n"
        "      keyword: z\n",
        encoding="utf-8",
    )

    assert load_tasks(yol)[0].setup == {}


def test_setup_dosyalari_calisma_dizinine_yazilir(tmp_path):
    from evals.executor import AgentTaskExecutor
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    gorev = EvalTask(
        id="ornek",
        request="düzelt",
        criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="x"),
        setup={"alt/kod.py": "print('merhaba')\n"},
    )
    yurutucu = AgentTaskExecutor(
        agent_runner=None,  # type: ignore[arg-type]
        workspace_root=tmp_path,
        clock=None,  # type: ignore[arg-type]
    )

    calisma = yurutucu._prepare_workspace(gorev.id, gorev.setup)

    assert (calisma / "alt" / "kod.py").read_text(encoding="utf-8") == "print('merhaba')\n"


def test_setup_yolu_calisma_dizini_disina_cikamaz(tmp_path):
    """Görev seti bir girdidir; `../` ile depoya yazmasına izin verilemez."""
    from evals.executor import AgentTaskExecutor

    from fusion_cli.core.errors import EvalError

    yurutucu = AgentTaskExecutor(
        agent_runner=None,  # type: ignore[arg-type]
        workspace_root=tmp_path,
        clock=None,  # type: ignore[arg-type]
    )

    with pytest.raises(EvalError, match="dışına"):
        yurutucu._prepare_workspace("kotu", {"../kacis.py": "zararli"})


async def test_dogrulama_komutu_python_bulabilir(tmp_path):
    """`python -c ...` ölçütü her sistemde çalışmalı.

    Gerçek hata: `python` PATH'te olmayan kurulumlarda (venv, python3-only) her
    exit_code görevi 127 "command not found" dönüyordu. Ölçüt hiç çalışmadan
    "kaldı" sayılıyor, görev seti sessizce yalan söylüyordu.
    """
    from evals.executor import AgentRunObservation, AgentTaskExecutor
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    class _Bos:
        async def run(self, request, *, root, strict_approval=False, transcript=None):
            return AgentRunObservation(output_text="", model_calls=0)

    class _Saat:
        def monotonic(self):
            return 0.0

    gorev = EvalTask(
        id="python-bulunur",
        request="-",
        criterion=SuccessCriterion(
            kind=CriterionKind.EXIT_CODE, expected_exit_code=0, command="python -c 'pass'"
        ),
    )
    yurutucu = AgentTaskExecutor(agent_runner=_Bos(), workspace_root=tmp_path, clock=_Saat())

    sonuc = await yurutucu.run(gorev)

    assert sonuc.exit_code == 0, f"python bulunamadı (çıkış {sonuc.exit_code})"


async def test_eval_onay_politikasi_urunle_ayni_karari_verir():
    """Koşucu üründen GEVŞEK olmamalı; yoksa ölçüm yanıltıcı olur.

    Gerçek hata: koşucu yalnızca `danger`a bakıyordu ve `echo x > ../y` gibi kök
    dışına yazan bir kabuk yönlendirmesi sessizce geçiyordu. Ürünün auto kipi aynı
    komutu kullanıcıya sorar.
    """
    from evals.agent_runner import _EvalApproval

    from fusion_cli.core.tools import Tool
    from fusion_cli.engines.agent.approval import Decision, build_request

    arac = Tool(name="run_shell", description="", parameters={}, run=lambda a, c: None)
    siki = _EvalApproval(strict=True)
    gevsek = _EvalApproval(strict=False)
    kacis = {"command": "echo x > ../disari.txt"}

    assert await siki.decide(build_request(arac, kacis)) is Decision.DENIED
    assert await siki.decide(build_request(arac, {"command": "ls -la"})) is Decision.ALLOW
    # Gevşek duruş yetenek ölçümü içindir: olağan işe evet diyen kullanıcıyı modeller.
    assert await gevsek.decide(build_request(arac, kacis)) is Decision.ALLOW


# --- Tekrarlı koşu: tek örnek karar veremez ---------------------------------- #


async def test_gorev_n_kez_kosturulur():
    """Tek koşu gürültülüdür ve karar desteklemez.

    Ölçüldü (2026-07-26): aynı görev aynı ayarla bir koşuda kaldı, ötekinde geçti.
    Bir ayarın (workflow_mode, kademe, verified_synthesis) işe yarayıp yaramadığı
    tek örnekle söylenemez; geçme ORANI gerekir.
    """
    from evals.runner import run_suite
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    gorev = EvalTask(
        id="x",
        request="-",
        criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="tamam"),
    )
    cagri = {"sayi": 0}

    class _Yurutucu:
        async def run(self, task):
            from evals.execution import TaskExecution

            cagri["sayi"] += 1
            return TaskExecution(task_id=task.id, output_text="tamam")

    rapor = await run_suite((gorev,), _Yurutucu(), repeat=5)

    assert cagri["sayi"] == 5
    assert rapor.results[0].runs == 5
    assert rapor.results[0].passes == 5
    assert rapor.results[0].pass_rate == 1.0


async def test_kararsiz_gorevin_orani_raporlanir():
    """Bir geçip bir kalan görev 'geçti' ya da 'kaldı' diye özetlenemez."""
    from evals.runner import run_suite
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    gorev = EvalTask(
        id="kararsiz",
        request="-",
        criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="tamam"),
    )
    sayac = {"n": 0}

    class _Kararsiz:
        async def run(self, task):
            from evals.execution import TaskExecution

            sayac["n"] += 1
            metin = "tamam" if sayac["n"] % 2 else "olmadi"
            return TaskExecution(task_id=task.id, output_text=metin)

    rapor = await run_suite((gorev,), _Kararsiz(), repeat=4)

    assert rapor.results[0].pass_rate == 0.5
    assert rapor.results[0].kararli is False


async def test_tek_tekrar_varsayilan_davranisi_korur():
    from evals.runner import run_suite
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    gorev = EvalTask(
        id="x",
        request="-",
        criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="tamam"),
    )

    class _Yurutucu:
        async def run(self, task):
            from evals.execution import TaskExecution

            return TaskExecution(task_id=task.id, output_text="tamam")

    rapor = await run_suite((gorev,), _Yurutucu())

    assert rapor.results[0].runs == 1
    assert rapor.results[0].success is True


# --- Başarısızlık teşhisi: transkript ---------------------------------------- #


def test_transkript_arac_cagrilarini_ve_sonuclarini_kaydeder(tmp_path):
    """Geç/kal ölçümü "agent neden hiçbir şey yapmadı" sorusunu cevaplamıyor.

    Ölçüldü: zor görevlerde agent bimodal davranıyor — ya işi yapıyor ya hiç
    dokunmuyor. Sebebi ancak turda NE OLDUĞUNA bakarak bulunabilir; eval yalnızca
    sonucu kaydettiği için her teşhis elle canlı koşum gerektiriyordu.
    """
    from evals.transcript import TranscriptRecorder

    from fusion_cli.core.events import ModelCallFinished, ToolExecuted, ToolOutcome
    from fusion_cli.core.types import ModelResult

    yol = tmp_path / "transkript.jsonl"
    kayit = TranscriptRecorder(yol)

    kayit.publish(
        ToolExecuted(
            name="write_file",
            args={"path": "a.py"},
            outcome=ToolOutcome.DENIED,
            output="onaylanmadı",
        )
    )
    kayit.publish(
        ModelCallFinished(
            role="agent",
            result=ModelResult(name="a", model="m", text="bitti", latency_ms=5, ok=True),
        )
    )
    kayit.close()

    satirlar = [json.loads(s) for s in yol.read_text(encoding="utf-8").splitlines()]

    assert satirlar[0]["event"] == "ToolExecuted"
    assert satirlar[0]["outcome"] == "denied"
    assert satirlar[0]["name"] == "write_file"
    assert satirlar[1]["event"] == "ModelCallFinished"
    assert satirlar[1]["ok"] is True
    # Yedek devreye girdiyse cevabı beklenen model vermemiştir; teşhiste ilk
    # sorulan soru "hangi model cevapladı" olur.
    assert satirlar[1]["model"] == "m"


def test_transkript_token_gurultusunu_yazmaz(tmp_path):
    """Akış parçaları binlerce satır üretir ve teşhise katkısı yoktur."""
    from evals.transcript import TranscriptRecorder

    from fusion_cli.core.events import Channel, TokenReceived

    yol = tmp_path / "t.jsonl"
    kayit = TranscriptRecorder(yol)

    for _ in range(100):
        kayit.publish(TokenReceived(channel=Channel.MAIN, text="x"))
    kayit.close()

    assert yol.read_text(encoding="utf-8") == ""


def test_transkript_arac_cikti_ozetini_kirpar(tmp_path):
    """Uzun araç çıktısı transkripti kullanılamaz hale getirir."""
    from evals.transcript import TranscriptRecorder

    from fusion_cli.core.events import ToolExecuted, ToolOutcome

    yol = tmp_path / "t.jsonl"
    kayit = TranscriptRecorder(yol)

    kayit.publish(
        ToolExecuted(name="read_file", args={}, outcome=ToolOutcome.OK, output="x" * 50_000)
    )
    kayit.close()

    satir = json.loads(yol.read_text(encoding="utf-8"))
    assert len(satir["output"]) < 2_000


# --- Kota tükenmesi görev başarısızlığı DEĞİLDİR ----------------------------- #


def test_kota_hatasi_gorev_basarisizligindan_ayrilir():
    """Sağlayıcı 429 verdiğinde agent'ın yeteneği ölçülmemiştir.

    Gerçek olay: kota tükenirken ölçüm sessizce bozuldu. Model çağrısı 8.6'dan
    5.8'e, sonra 1.0'a düştü ve set "başarısız" raporladı. O sayılar yetenek
    hakkında hiçbir şey söylemiyordu ama rapor bunu ayırt etmiyordu — üstelik
    aradaki düşüş bir kod değişikliğine bağlanmıştı.
    """
    from evals.execution import TaskExecution
    from evals.metrics import score_task
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    gorev = EvalTask(
        id="x", request="-", criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="a")
    )
    calisma = TaskExecution(task_id="x", output_text="", rate_limited=True)

    sonuc = score_task(gorev, calisma)

    assert sonuc.rate_limited is True
    assert sonuc.success is False


async def test_kota_israrla_devam_ederse_kosu_durur():
    """Sınır yeniden denemelerde de aşılamıyorsa devam etmek çöp veri üretir."""
    from evals.execution import TaskExecution
    from evals.runner import RateLimitedError, run_suite
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    gorevler = tuple(
        EvalTask(
            id=f"g{i}",
            request="-",
            criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="a"),
        )
        for i in range(5)
    )
    cagri = {"n": 0}

    class _KotaBitmis:
        async def run(self, task):
            cagri["n"] += 1
            return TaskExecution(task_id=task.id, output_text="", rate_limited=True)

    with pytest.raises(RateLimitedError, match="hız sınırı"):
        await run_suite(gorevler, _KotaBitmis(), sleep=_bekleme_yok)

    # 1 ilk deneme + MAX_RATE_LIMIT_RETRIES; sonraki görevlere GEÇİLMEZ.
    assert cagri["n"] == 3, f"tek görevde durmalıydı, {cagri['n']} çağrı yapıldı"


async def test_gecici_sinirda_bekleyip_tekrar_dener():
    """Dakikalık sınır için tüm koşuyu iptal etmek kotayı boşa harcar.

    NIM çıplak 429 döner; dakikalık sınır da olabilir. Ayırt edemediğimizde
    geçici varsayıp sınırlı sayıda yeniden denemek doğrudur.
    """
    from evals.execution import TaskExecution
    from evals.runner import run_suite
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    gorev = EvalTask(
        id="g", request="-", criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="a")
    )
    sayac = {"n": 0}
    beklemeler: list[float] = []

    class _IlkDenemeSinirli:
        async def run(self, task):
            sayac["n"] += 1
            if sayac["n"] == 1:
                return TaskExecution(task_id=task.id, output_text="", rate_limited=True)
            return TaskExecution(task_id=task.id, output_text="a")

    async def _kaydet(seconds: float) -> None:
        beklemeler.append(seconds)

    rapor = await run_suite((gorev,), _IlkDenemeSinirli(), sleep=_kaydet)

    assert sayac["n"] == 2, "geçici sınırda bir kez daha denenmeli"
    assert beklemeler, "yeniden denemeden önce beklenmeli"
    assert rapor.results[0].success is True


async def test_gunluk_kotada_beklemeden_durur():
    """Günlük kota o gün için biter; beklemek kullanıcıyı boşuna oyalar."""
    from evals.execution import TaskExecution
    from evals.runner import RateLimitedError, run_suite
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    gorev = EvalTask(
        id="g", request="-", criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="a")
    )
    beklemeler: list[float] = []

    class _GunlukKota:
        async def run(self, task):
            return TaskExecution(
                task_id=task.id,
                output_text="",
                rate_limited=True,
                rate_limit_detail="Rate limit exceeded: free-models-per-day",
            )

    async def _kaydet(seconds: float) -> None:
        beklemeler.append(seconds)

    with pytest.raises(RateLimitedError, match="günlük"):
        await run_suite((gorev,), _GunlukKota(), sleep=_kaydet)

    assert beklemeler == [], "günlük kotada beklenmemeli"


async def _bekleme_yok(seconds: float) -> None:
    """Testte gerçek zaman harcanmaz."""
    return None
