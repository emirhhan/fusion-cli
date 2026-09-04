"""Plan adımı post-condition doğrulaması."""

from __future__ import annotations

from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
    StepStatus,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome
from fusion_cli.engines.agent.step_verification import (
    verify_plan_acceptance,
    verify_step,
)

from .fakes import AlwaysApprove, make_config


class _Publisher:
    def publish(self, event):
        del event


def _deps(tmp_path):
    return AgentDeps(
        config=make_config(),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _file_step(path: str) -> PlanStep:
    return PlanStep(
        step_id="create",
        goal="dosyayı oluştur",
        depends_on=(),
        expected_effects=(f"file:{path}",),
        allowed_tool_families=("files",),
        success_criteria=("dosya bulunuyor",),
        verification_hint="dosyayı oku",
        retry_safety=RetrySafety.SAFE,
    )


async def test_arac_basari_dese_bile_post_condition_adimi_basarisiz_yapar(tmp_path):
    result = await verify_step(
        _file_step("main.tscn"),
        AgentOutcome(final_text="tamam", messages=[], ok=True),
        _deps(tmp_path),
    )

    assert result.ok is False
    assert "beklenen dosya bulunamadı" in result.findings[0]


async def test_var_olan_dosya_post_condition_kaniti_olur(tmp_path):
    (tmp_path / "main.tscn").write_text("[scene]", encoding="utf-8")

    result = await verify_step(
        _file_step("main.tscn"),
        AgentOutcome(final_text="tamam", messages=[], ok=True),
        _deps(tmp_path),
    )

    assert result.ok is True
    assert "main.tscn" in result.evidence[0]


async def test_proje_dogrulayicisi_kirilirsa_adim_basarisizdir(tmp_path):
    class _FailingVerifier:
        async def verify(self):
            return VerificationResult(ok=False, findings=("pytest kırıldı",))

    deps = _deps(tmp_path)
    deps.verifier = _FailingVerifier()

    result = await verify_step(
        _file_step("main.tscn"),
        AgentOutcome(final_text="tamam", messages=[], ok=True),
        deps,
    )

    assert result.ok is False
    assert "pytest kırıldı" in result.findings


# --------------------------------------------------------------------------- #
# Final kabul kapısı
# --------------------------------------------------------------------------- #


def _tamamlanmis_plan(*steps: PlanStep) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p",
        task="iş",
        steps=tuple(replace_status(step) for step in steps),
    )


def replace_status(step: PlanStep) -> PlanStep:
    from dataclasses import replace

    return replace(step, status=StepStatus.COMPLETED)


async def test_kabul_kapisi_adim_ciktisinin_hala_durdugunu_olcer(tmp_path):
    """Final kapısı, her adımın post-condition'ını SONDA yeniden ölçmelidir.

    Aksi hâlde dördüncü adımın sildiği/üzerine yazdığı bir dosyayı ikinci adımın
    "doğrulandı" kaydı örtbas eder ve plan eksik çıktıyla tamamlanmış sayılır.
    """
    plan = _tamamlanmis_plan(_file_step("main.tscn"))

    sonuc = await verify_plan_acceptance(plan, _deps(tmp_path))

    assert sonuc.ok is False
    assert any("main.tscn" in bulgu for bulgu in sonuc.findings)


async def test_yalniz_yapisal_kapisi_olan_proje_davranisi_kanitlanmadi_der(tmp_path):
    """Ölçüldü: Godot planı "tamamlandı" dedi, oyun hiç çalışmıyordu.

    `godot --headless --path . --quit` projenin AÇILDIĞINI kanıtlar. Kapının
    kanıtladığı şeyle kullanıcıya söylenen şey aynı olmalıdır: iş kırılmaz ama
    davranışın kanıtlanmadığı AÇIKÇA bildirilir.
    """
    (tmp_path / "main.tscn").write_text("[scene]", encoding="utf-8")
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    plan = _tamamlanmis_plan(_file_step("main.tscn"))

    sonuc = await verify_plan_acceptance(plan, _deps(tmp_path))

    assert sonuc.ok is True
    assert any("davranış" in uyari.lower() for uyari in sonuc.warnings)


async def test_test_paketi_olan_proje_uyari_uretmez(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\npytest\n", encoding="utf-8")
    plan = _tamamlanmis_plan(_file_step("main.py"))

    sonuc = await verify_plan_acceptance(plan, _deps(tmp_path))

    assert sonuc.ok is True
    assert sonuc.warnings == ()


def _mutation_step() -> PlanStep:
    from dataclasses import replace as _replace

    return _replace(_file_step("x"), expected_effects=("workspace_mutation",))


async def test_isi_onceki_adim_yaptiysa_adim_basarisiz_sayilmaz(tmp_path):
    """Ölçüldü (Godot koşusu): birinci adım sahneyi ve düğümleri baştan sona kurdu.

    İkinci adımın hedefi aynı işti; her çağrısı `TOOL_CALL_DUPLICATE` ile
    engellendi ve adım "beklenen çalışma alanı değişikliği gözlenmedi" diyerek
    GEÇİLEMEZ hâle geldi — kurtarma hakkı bitti, plan duraklatıldı. Zaten yapılmış
    iş bir başarısızlık değildir; tekrar yapılmaması doğrudur.
    """
    result = await verify_step(
        _mutation_step(),
        AgentOutcome(
            final_text="iş zaten yapılmış",
            messages=[],
            ok=True,
            mutating_tool_calls_made=0,
            already_done_calls=2,
        ),
        _deps(tmp_path),
    )

    assert result.ok is True
    assert any("daha önce" in kanit for kanit in result.evidence)


async def test_hicbir_sey_yapmayan_adim_hala_basarisizdir(tmp_path):
    """Kanıt yoksa "zaten yapılmıştı" savunması geçerli değildir."""
    result = await verify_step(
        _mutation_step(),
        AgentOutcome(final_text="bir şey yapmadım", messages=[], ok=True),
        _deps(tmp_path),
    )

    assert result.ok is False
    assert "beklenen çalışma alanı değişikliği gözlenmedi" in result.findings


def _shell_step() -> PlanStep:
    from dataclasses import replace as _replace

    return _replace(_file_step("x"), expected_effects=("shell_action",))


async def test_komut_onceki_adimda_calistiysa_adim_basarisiz_sayilmaz(tmp_path):
    """Ölçüldü (Godot koşusu): doğrulama komutu birinci adımda çalıştı (çıkış 0).

    Üçüncü adım o sonucu göremediği için komutu tekrar istedi; çalışma alanı
    değişmediği için `TOOL_CALL_DUPLICATE` ile engellendi ve adım kanıt
    üretemeden düştü. Aynı ilke `workspace_mutation` için uygulanmıştı; dış etki
    post-condition'ları da tutarlı olmalı.
    """
    result = await verify_step(
        _shell_step(),
        AgentOutcome(
            final_text="komut zaten çalıştı",
            messages=[],
            ok=True,
            tool_calls_made=0,
            already_done_calls=1,
        ),
        _deps(tmp_path),
    )

    assert result.ok is True


async def test_hic_calismayan_komut_adimi_yine_dusurur(tmp_path):
    result = await verify_step(
        _shell_step(),
        AgentOutcome(final_text="komutu atladım", messages=[], ok=True),
        _deps(tmp_path),
    )

    assert result.ok is False


class _KirikVerifier:
    """Her çağrıda AYNI bulguyu döndüren proje kapısı."""

    def __init__(self, finding="Error: Can't run project: no main scene defined"):
        self.finding = finding

    async def verify(self):
        from fusion_cli.core.verification import VerificationResult

        return VerificationResult(ok=False, summary=self.finding, findings=(self.finding,))


async def test_adimdan_once_de_dusen_kapi_adimi_suclamaz(tmp_path):
    """Ölçüldü: sıfırdan Godot projesi kuran plan, HER adımda 'no main scene
    defined' ile düştü.

    Proje henüz kurulmadığı için kapı zaten düşüyordu; adım o hatayı YARATMADI.
    Yarım kurulmuş bir projede her adımı suçlamak, sıfırdan proje kurmayı
    imkânsız hâle getirir. Kapının sorusu 'bozdum mu' olmalı, 'her şey bitti mi'
    değil — final kabul kapısı zaten tam temizlik ister.
    """
    from dataclasses import replace as _replace

    deps = _deps(tmp_path)
    deps.verifier = _KirikVerifier()
    adim = _replace(_file_step("x"), expected_effects=())
    (tmp_path / "x").write_text("var", encoding="utf-8")

    sonuc = await verify_step(
        adim,
        AgentOutcome(final_text="kuruldu", messages=[], ok=True),
        deps,
        baseline=("Error: Can't run project: no main scene defined",),
    )

    assert sonuc.ok is True
    assert any("ÖNCE de" in kanit for kanit in sonuc.evidence)


async def test_adimin_yeni_bozdugu_sey_yine_adimi_dusurur(tmp_path):
    """Temel bulgu görmezden gelinir; adımın EKLEDİĞİ bulgu görmezden gelinmez."""
    deps = _deps(tmp_path)
    deps.verifier = _KirikVerifier("Parse Error: main.tscn bozuldu")

    sonuc = await verify_step(
        _file_step("yok.txt"),
        AgentOutcome(final_text="tamam", messages=[], ok=True),
        deps,
        baseline=("Error: Can't run project: no main scene defined",),
    )

    assert sonuc.ok is False
    assert any("Parse Error" in b for b in sonuc.findings)
