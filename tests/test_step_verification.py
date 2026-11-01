"""Plan adımı post-condition doğrulaması."""

from __future__ import annotations

import pytest

from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus, ToolUse
from fusion_cli.core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    RetrySafety,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import UNVERIFIABLE_COMMAND_PREFIX, VerificationResult
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


def _degisen_deps(tmp_path, *paths: str):
    """Planın dosya YAZDIĞI koşu: kabul kapısı yalnız bu koşuda davranış kanıtı arar."""
    deps = _deps(tmp_path)
    deps.tool_context.touched.update(tmp_path / path for path in paths)
    return deps


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

    sonuc = await verify_plan_acceptance(plan, _degisen_deps(tmp_path, "main.tscn"))

    assert sonuc.ok is True
    assert any("davranış" in uyari.lower() for uyari in sonuc.warnings)


async def test_tanimli_ama_calistirilmamis_test_davranis_uyarisini_kaldirmaz(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    plan = _tamamlanmis_plan(_file_step("main.py"))

    sonuc = await verify_plan_acceptance(plan, _degisen_deps(tmp_path, "main.py"))

    assert sonuc.ok is True
    assert any("davranış" in uyari.lower() for uyari in sonuc.warnings)


async def test_pytest_surumu_davranis_uyarisini_kaldirmaz(tmp_path):
    from fusion_cli.engines.agent.verification import CommandVerifier

    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    deps = _degisen_deps(tmp_path, "main.py")
    deps.verifier = CommandVerifier(
        ("pytest --version",),
        cwd=str(tmp_path),
        timeout_s=10.0,
    )

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

    assert sonuc.ok is True
    assert any("davranış" in warning for warning in sonuc.warnings)
    assert sonuc.evidence[0].status is EvidenceStatus.PASSED


async def test_echo_pytest_davranis_uyarisini_kaldirmaz(tmp_path):
    from fusion_cli.engines.agent.verification import CommandVerifier

    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    deps = _degisen_deps(tmp_path, "main.py")
    deps.verifier = CommandVerifier(("printf pytest",), cwd=str(tmp_path), timeout_s=10.0)

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

    assert any("davranış" in warning for warning in sonuc.warnings)


async def test_gercek_kesfedilmis_test_kaniti_davranis_uyarisini_kaldirir(tmp_path):
    from fusion_cli.engines.agent.verification import CommandVerifier

    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "test_main.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    deps = _deps(tmp_path)
    deps.verifier = CommandVerifier(("pytest -q",), cwd=str(tmp_path), timeout_s=10.0)

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

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


async def test_yalniz_yinelenen_sayisi_onceki_komutu_kanitlamaz(tmp_path):
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

    assert result.ok is False
    assert any("shell_action" in finding for finding in result.findings)


async def test_hic_calismayan_komut_adimi_yine_dusurur(tmp_path):
    result = await verify_step(
        _shell_step(),
        AgentOutcome(final_text="komutu atladım", messages=[], ok=True),
        _deps(tmp_path),
    )

    assert result.ok is False


async def test_genel_arac_sayisi_git_commit_kaniti_degildir(tmp_path):
    from dataclasses import replace as _replace

    step = _replace(_file_step("x"), expected_effects=("git_commit",))

    result = await verify_step(
        step,
        AgentOutcome(final_text="tamam", messages=[], ok=True, tool_calls_made=3),
        _deps(tmp_path),
    )

    assert result.ok is False
    assert result.unverified is True
    assert any("git_commit" in bulgu for bulgu in result.findings)


async def test_git_commit_gercek_arac_argumaniyla_kanitlanir(tmp_path):
    from dataclasses import replace as _replace

    step = _replace(
        _file_step("x"),
        success_criteria=("değişiklik commit edildi",),
        expected_effects=("git_commit",),
        verification_checks=(
            VerificationCheck(
                criterion_id="değişiklik commit edildi",
                kind=VerificationCheckKind.COMMAND,
                target="git commit -m test",
            ),
        ),
    )

    result = await verify_step(
        step,
        AgentOutcome(
            final_text="tamam",
            messages=[],
            ok=True,
            tool_uses=(
                ToolUse(
                    "run_shell",
                    arguments={"command": "git commit -m test"},
                    output="[main abc123] test",
                ),
            ),
        ),
        _deps(tmp_path),
    )

    assert result.ok is True
    assert result.criteria[0].status is EvidenceStatus.PASSED
    assert "abc123" in result.criteria[0].output


async def test_git_commit_no_verify_kisa_seceneği_kaniti_engellemez(tmp_path):
    from dataclasses import replace as _replace

    for command in ("git commit -n -m test", "git commit -nm test"):
        result = await verify_step(
            _replace(_file_step("x"), expected_effects=("git_commit",)),
            AgentOutcome(
                final_text="tamam",
                messages=[],
                tool_uses=(
                    ToolUse("run_shell", arguments={"command": command}, output="[main abc123]"),
                ),
            ),
            _deps(tmp_path),
        )

        assert result.ok is True, command


async def test_echo_git_push_dis_etki_kaniti_degildir(tmp_path):
    from dataclasses import replace as _replace

    step = _replace(_file_step("x"), expected_effects=("git_push",))

    result = await verify_step(
        step,
        AgentOutcome(
            final_text="tamam",
            messages=[],
            tool_uses=(
                ToolUse(
                    "run_shell",
                    arguments={"command": "echo git push"},
                    output="git push",
                ),
            ),
        ),
        _deps(tmp_path),
    )

    assert result.ok is False
    assert any("git_push" in finding for finding in result.findings)


async def test_git_dry_run_yorum_ve_arama_dis_etki_kaniti_degildir(tmp_path):
    from dataclasses import replace as _replace

    for effect, command in (
        ("git_push", "git push --dry-run origin main"),
        ("git_push", "git push -vn origin main"),
        ("git_push", "git push -nv origin main"),
        ("git_push", "git status # push"),
        ("git_push", "git status # ; git push"),
        ("git_push", "git status # && git push"),
        ("git_push", "true || git push"),
        ("git_commit", "git log --grep=commit"),
    ):
        result = await verify_step(
            _replace(_file_step("x"), expected_effects=(effect,)),
            AgentOutcome(
                final_text="tamam",
                messages=[],
                tool_uses=(ToolUse("run_shell", arguments={"command": command}, output="ok"),),
            ),
            _deps(tmp_path),
        )

        assert result.ok is False, command


async def test_bos_dosya_hareket_kriterini_dogrulamaz(tmp_path):
    (tmp_path / "player.gd").write_text("", encoding="utf-8")
    step = PlanStep(
        step_id="movement",
        goal="oyuncu hareketini ekle",
        depends_on=(),
        expected_effects=("file:player.gd",),
        allowed_tool_families=("files",),
        success_criteria=("sağ tuş oyuncuyu hareket ettirir",),
        verification_hint="oyuncu scriptini ve testi doğrula",
        retry_safety=RetrySafety.SAFE,
    )

    result = await verify_step(
        step,
        AgentOutcome(final_text="hareket tamam", messages=[], ok=True),
        _deps(tmp_path),
    )

    assert result.ok is True
    assert result.unverified is True
    assert result.criteria[0].status is EvidenceStatus.UNVERIFIED
    assert not any("hareket doğrulandı" in item for item in result.evidence)


async def test_icerik_kontrolu_gercek_dosyayi_okur(tmp_path):
    (tmp_path / "player.gd").write_text(
        'if Input.is_action_pressed("move_right"):\n    velocity.x = 1\n',
        encoding="utf-8",
    )
    step = PlanStep(
        step_id="movement",
        goal="oyuncu hareketini ekle",
        depends_on=(),
        expected_effects=("file:player.gd",),
        allowed_tool_families=("files",),
        success_criteria=("sağ tuş girdisi işlendi",),
        verification_hint="script içeriğini doğrula",
        retry_safety=RetrySafety.SAFE,
        verification_checks=(
            VerificationCheck(
                criterion_id="sağ tuş girdisi işlendi",
                kind=VerificationCheckKind.FILE_CONTAINS,
                target="player.gd",
                expected='Input.is_action_pressed("move_right")',
            ),
        ),
    )

    result = await verify_step(
        step,
        AgentOutcome(final_text="tamam", messages=[], ok=True),
        _deps(tmp_path),
    )

    assert result.ok is True
    assert result.criteria[0].status is EvidenceStatus.PASSED
    assert result.criteria[0].artifact == "player.gd"


async def test_engellenmis_komut_kriter_icin_calistirilmaz(tmp_path):
    marker = tmp_path / "calismadi.txt"
    command = f"touch {marker}"
    step = PlanStep(
        step_id="blocked-command",
        goal="önceden engellenmiş komutu doğrula",
        depends_on=(),
        expected_effects=(),
        allowed_tool_families=("shell",),
        success_criteria=("komut çalıştı",),
        verification_hint="gerçek araç kaydını doğrula",
        retry_safety=RetrySafety.SAFE,
        verification_checks=(
            VerificationCheck(
                criterion_id="komut çalıştı",
                kind=VerificationCheckKind.COMMAND,
                target=command,
            ),
        ),
    )

    result = await verify_step(
        step,
        AgentOutcome(
            final_text="komut engellendi",
            messages=[],
            tool_uses=(
                ToolUse(
                    "run_shell",
                    ok=False,
                    arguments={"command": command},
                    output="onay verilmedi",
                ),
            ),
        ),
        _deps(tmp_path),
    )

    assert marker.exists() is False
    assert result.ok is True
    assert result.unverified is True


async def test_tool_kontrolu_beklenen_arguman_eslesmeden_gecmez(tmp_path):
    step = PlanStep(
        step_id="issue",
        goal="issue aç",
        depends_on=(),
        expected_effects=(),
        allowed_tool_families=("external",),
        success_criteria=("repo A üzerinde issue açıldı",),
        verification_hint="araç argümanını doğrula",
        retry_safety=RetrySafety.NEVER,
        verification_checks=(
            VerificationCheck(
                criterion_id="repo A üzerinde issue açıldı",
                kind=VerificationCheckKind.TOOL,
                target="github_create_issue",
                expected='{"repo": "A"}',
            ),
        ),
    )
    outcome = AgentOutcome(
        final_text="tamam",
        messages=[],
        tool_uses=(ToolUse("github_create_issue", arguments={"repo": "B"}, output="issue-1"),),
    )

    result = await verify_step(step, outcome, _deps(tmp_path))

    assert result.ok is True
    assert result.unverified is True
    assert result.criteria[0].status is EvidenceStatus.UNVERIFIED


async def test_final_kabul_file_contains_kriterini_yeniden_olcer(tmp_path):
    (tmp_path / "player.gd").write_text("", encoding="utf-8")
    step = PlanStep(
        step_id="movement",
        goal="hareket ekle",
        depends_on=(),
        expected_effects=("file:player.gd",),
        allowed_tool_families=("files",),
        success_criteria=("hareket girdisi var",),
        verification_hint="içeriği oku",
        retry_safety=RetrySafety.SAFE,
        verification_checks=(
            VerificationCheck(
                criterion_id="hareket girdisi var",
                kind=VerificationCheckKind.FILE_CONTAINS,
                target="player.gd",
                expected="move_right",
            ),
        ),
    )

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(step), _deps(tmp_path))

    assert sonuc.ok is False
    assert any(
        "move_right" in finding or "hareket girdisi" in finding for finding in sonuc.findings
    )


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


# --------------------------------------------------------------------------- #
# Sahte uyarılar: kapı kanıtladığından fazlasını da, azını da söylememeli
# --------------------------------------------------------------------------- #


class _KanitliVerifier:
    """Verilen kanıt ve uyarıları geçen bir kapı gibi döndürür."""

    def __init__(self, *, evidence=(), warnings=()):
        self._evidence = tuple(evidence)
        self._warnings = tuple(warnings)

    async def verify(self):
        return VerificationResult(ok=True, evidence=self._evidence, warnings=self._warnings)


def _komut_kaniti(command: str) -> CriterionEvidence:
    return CriterionEvidence(
        criterion_id=command,
        kind=VerificationCheckKind.COMMAND,
        status=EvidenceStatus.PASSED,
        summary="komut başarıyla çalıştı",
        command=command,
    )


async def test_gercekten_calisan_pytest_davranis_uyarisini_kaldirir(tmp_path):
    """Ölçüldü (17 Eylül denetimi): `pytest` çalıştı, dört test geçti, uyarı yine çıktı.

    Kanıt keşfedilen komutun YAZIMIYLA karşılaştırılıyordu; agent aynı testleri
    başka bir yazımla çalıştırınca kanıt görünmez oldu ve kullanıcıya doğru olmayan
    bir "davranış kanıtlanmadı" cümlesi gösterildi.
    """
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    deps = _deps(tmp_path)
    deps.verifier = _KanitliVerifier(
        evidence=(_komut_kaniti(".venv/bin/pytest -q tests/test_agent_loop.py"),)
    )

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

    assert sonuc.ok is True
    assert sonuc.warnings == ()


async def test_calistirilmayan_test_komutu_icin_uyari_hala_cikar(tmp_path):
    """Gerçekten doğrulanamayan durumda uyarı susturulmaz; yalnız doğru şeyi söyler."""
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    deps = _degisen_deps(tmp_path, "main.py")
    deps.verifier = _KanitliVerifier(evidence=(_komut_kaniti("ruff check ."),))

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

    assert sonuc.ok is True
    assert any("davranış kanıtlanmadı" in uyari for uyari in sonuc.warnings)
    # Projede pytest VAR; "bu projede doğrulama komutu yok" demek yanlış olurdu.
    assert any("pytest -q" in uyari for uyari in sonuc.warnings)


async def test_salt_okuma_kosusunda_kurulu_olmayan_arac_uyarisi_verilmez(tmp_path):
    """Ölçüldü (17 Eylül denetimi): açıklama turuna ruff/mypy uyarıları ekleniyordu.

    Hiçbir dosyaya dokunulmayan koşuda "kodu sınayamadım" demenin karşılığı yoktur;
    uyarı yalnızca gerçek uyarıların arasında gürültü yapar.
    """
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    deps = _deps(tmp_path)
    deps.verifier = _KanitliVerifier(
        warnings=(
            f"{UNVERIFIABLE_COMMAND_PREFIX}; sonuç doğrulanamadı: ruff check .",
            f"{UNVERIFIABLE_COMMAND_PREFIX}; sonuç doğrulanamadı: mypy src",
        )
    )

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

    assert not any(UNVERIFIABLE_COMMAND_PREFIX in uyari for uyari in sonuc.warnings)


async def test_degisiklik_yapilan_kosuda_kurulu_olmayan_arac_uyarisi_korunur(tmp_path):
    """Kod değiştiyse "sınayamadım" gerçek ve eyleme dönüştürülebilir bir uyarıdır."""
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    deps = _deps(tmp_path)
    deps.tool_context.touched.add(tmp_path / "main.py")
    deps.verifier = _KanitliVerifier(
        warnings=(f"{UNVERIFIABLE_COMMAND_PREFIX}; sonuç doğrulanamadı: ruff check .",)
    )

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

    assert any(UNVERIFIABLE_COMMAND_PREFIX in uyari for uyari in sonuc.warnings)


def _tool_step(expected: str) -> PlanStep:
    from dataclasses import replace as _replace

    return _replace(
        _file_step("x"),
        expected_effects=(),
        success_criteria=("dosya okundu",),
        verification_checks=(
            VerificationCheck(
                criterion_id="dosya okundu",
                kind=VerificationCheckKind.TOOL,
                target="read_file",
                expected=expected,
            ),
        ),
    )


async def test_yol_yazimi_farkli_arac_cagrisi_kanit_sayilir(tmp_path):
    """Plandaki `./src/a.py` ile çalışan `src/a.py` aynı dosyadır."""
    outcome = AgentOutcome(
        final_text="okudum",
        messages=[],
        tool_uses=(ToolUse("read_file", arguments={"path": "src/a.py"}, output="icerik"),),
    )

    result = await verify_step(_tool_step('{"path": "./src/a.py"}'), outcome, _deps(tmp_path))

    assert result.criteria[0].status is EvidenceStatus.PASSED


async def test_calisan_arac_cagrisi_icin_kayit_yok_denmez(tmp_path):
    """Ölçüldü (17 Eylül denetimi): adım `read_file` çağırmışken kanıt "kayıt yok" dedi.

    Kanıt metni yanlış olunca kullanıcı gerçek uyarıyı sahtesinden ayıramıyor.
    Koşul hâlâ doğrulanmamıştır, ama gerekçe doğru yazılmalıdır.
    """
    outcome = AgentOutcome(
        final_text="okudum",
        messages=[],
        tool_uses=(ToolUse("read_file", arguments={"path": "src/b.py"}, output="icerik"),),
    )

    result = await verify_step(_tool_step('{"path": "src/a.py"}'), outcome, _deps(tmp_path))

    ozet = result.criteria[0].summary
    assert result.criteria[0].status is EvidenceStatus.UNVERIFIED
    assert "kaydı yok" not in ozet
    assert "src/b.py" in ozet


async def test_hic_cagrilmayan_arac_icin_kayit_yok_denir(tmp_path):
    """Araç gerçekten hiç çalışmadıysa kanıt bunu açıkça söyler."""
    outcome = AgentOutcome(final_text="okumadım", messages=[])

    result = await verify_step(_tool_step('{"path": "src/a.py"}'), outcome, _deps(tmp_path))

    assert result.criteria[0].status is EvidenceStatus.UNVERIFIED
    assert "kaydı yok" in result.criteria[0].summary


async def test_mutlak_yolla_yapilan_arac_cagrisi_kanit_sayilir(tmp_path):
    """Model yolu çalışma köküne göre değil mutlak yazabilir; aynı dosyadır."""
    outcome = AgentOutcome(
        final_text="okudum",
        messages=[],
        tool_uses=(
            ToolUse("read_file", arguments={"path": str(tmp_path / "src" / "a.py")}, output="x"),
        ),
    )

    result = await verify_step(_tool_step('{"path": "src/a.py"}'), outcome, _deps(tmp_path))

    assert result.criteria[0].status is EvidenceStatus.PASSED


def _pytest_kosusu(*, ok: bool) -> AgentOutcome:
    return AgentOutcome(
        final_text="testleri çalıştırdım",
        messages=[],
        tool_uses=(
            ToolUse(
                "run_shell",
                ok=ok,
                mutating=True,
                arguments={"command": ".venv/bin/pytest -q tests/test_main.py"},
                output="4 passed" if ok else "1 failed",
            ),
        ),
    )


async def test_adimda_calisan_pytest_final_kabulde_davranis_kaniti_sayilir(tmp_path):
    """Ölçüldü (17 Eylül denetimi): adımda pytest çalışıp dört test geçti, uyarı yine çıktı.

    Planda o komuta bağlı bir kontrol yoktu; gerçek koşu adım kanıtına hiç girmediği
    için final kabul kapısı onu göremedi.
    """
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    deps = _degisen_deps(tmp_path, "main.py")
    adim = _file_step("main.py")

    adim_sonucu = await verify_step(adim, _pytest_kosusu(ok=True), deps)
    sonuc = await verify_plan_acceptance(
        _tamamlanmis_plan(adim), deps, evidence=adim_sonucu.criteria
    )

    assert any(
        item.command == ".venv/bin/pytest -q tests/test_main.py"
        and item.status is EvidenceStatus.PASSED
        for item in adim_sonucu.criteria
    )
    assert sonuc.ok is True
    assert not any("davranış kanıtlanmadı" in uyari for uyari in sonuc.warnings)


async def test_kirmizi_biten_pytest_davranis_kaniti_sayilmaz(tmp_path):
    """Çıkış kodu sıfır olmayan koşu kanıt değildir; uyarı yerinde kalır."""
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    deps = _degisen_deps(tmp_path, "main.py")
    adim = _file_step("main.py")

    adim_sonucu = await verify_step(adim, _pytest_kosusu(ok=False), deps)
    sonuc = await verify_plan_acceptance(
        _tamamlanmis_plan(adim), deps, evidence=adim_sonucu.criteria
    )

    assert not any(item.kind is VerificationCheckKind.COMMAND for item in adim_sonucu.criteria)
    assert any("davranış kanıtlanmadı" in uyari for uyari in sonuc.warnings)


async def test_salt_okuma_kosusunda_davranis_uyarisi_verilmez(tmp_path):
    """Test komutu olmayan projede açıklama turu "doğrulama komutu yok" demez.

    Uyarı yalnız bir şey DEĞİŞTİYSE anlamlıdır; hiçbir dosyaya dokunulmadıysa
    kanıtlanacak bir davranış da yoktur.
    """
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    deps = _deps(tmp_path)

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

    assert sonuc.ok is True
    assert sonuc.warnings == ()


async def test_degisiklik_yapilan_kosuda_komutsuz_proje_uyarisi_korunur(tmp_path):
    """Karşı taraf: kod değiştiyse ve projede test komutu yoksa uyarı çıkar."""
    from fusion_cli.engines.agent.step_verification import UNPROVEN_BEHAVIOR_WARNING

    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    deps = _degisen_deps(tmp_path, "main.py")

    sonuc = await verify_plan_acceptance(_tamamlanmis_plan(_file_step("main.py")), deps)

    assert UNPROVEN_BEHAVIOR_WARNING in sonuc.warnings


def test_zincirli_ve_yonlendirmeli_git_commit_kanit_sayilir():
    """Ölçüldü (29 Ekim): `&&`/`;`/`&` token'ı görülünce `False` dönüyordu; modelin
    yazdığı `git add -A && git commit -m x` gerçek commit olsa da kanıt sayılmıyordu."""
    from fusion_cli.engines.agent.step_verification import _contains_git_action

    for command in (
        "git add -A && git commit -m x",
        "cd repo && git commit -m x",
        "git commit -m x 2>&1",
        "git add . && git commit -m 'a b' 2>&1",
        "git add -A; git commit -m x",
        'git commit -m "başlık\n\ngövde"',
        "git add -A\ngit commit -m x",
        "git commit -m x &> /dev/null",
    ):
        assert _contains_git_action(command, "commit"), command


def test_maskelenen_ya_da_sonu_belirsiz_git_commit_kanit_degildir():
    from fusion_cli.engines.agent.step_verification import _contains_git_action

    for command in (
        "git commit -m x || true",
        "git commit -m x | tail",
        "git commit -m x &",
        "git commit -m x; echo bitti",  # son komutun kodu commit'i gizler
        "git commit --dry-run -m x && echo ok",
        "git add -A && git commit --dry-run",
        "cat <<EOF\ngit commit\nEOF",
        "echo 'git commit' && ls",
    ):
        assert not _contains_git_action(command, "commit"), command


async def test_final_full_gate_cannot_mask_missing_second_typed_criterion(tmp_path):
    from dataclasses import replace

    class FullGate:
        calls = 0

        async def verify(self):
            self.calls += 1
            return VerificationResult(
                True,
                evidence=(
                    CriterionEvidence(
                        "first",
                        VerificationCheckKind.COMMAND,
                        EvidenceStatus.PASSED,
                        "ilk kontrol geçti",
                        command="pytest -q test_first.py",
                    ),
                ),
            )

    deps = _deps(tmp_path)
    deps.verifier = FullGate()
    checks = tuple(
        VerificationCheck(name, VerificationCheckKind.COMMAND, f"pytest -q test_{name}.py")
        for name in ("first", "second")
    )
    step = replace(
        _file_step("app.py"),
        expected_effects=(),
        status=StepStatus.COMPLETED,
        success_criteria=("first", "second"),
        verification_checks=checks,
    )
    result = await verify_plan_acceptance(ExecutionPlan("p", "feature", (step,)), deps)
    assert deps.verifier.calls == 1
    assert not result.ok
    assert any("second" in finding for finding in result.findings)
    assert any(
        item.criterion_id == "second" and item.status is EvidenceStatus.UNVERIFIED
        for item in result.evidence
    )


async def test_final_gate_rejects_stale_reproduction_source(tmp_path):
    from dataclasses import replace

    from fusion_cli.core.evidence import EvidenceEnvironment

    check = VerificationCheck("bug", VerificationCheckKind.REPRODUCTION, "pytest -q")
    step = replace(
        _file_step("app.py"),
        expected_effects=(),
        status=StepStatus.COMPLETED,
        success_criteria=("bug",),
        verification_checks=(check,),
    )
    proof = CriterionEvidence(
        "bug",
        VerificationCheckKind.REPRODUCTION,
        EvidenceStatus.PASSED,
        "geçmiş kanıt",
        source_digest="old",
        source_after_digest="old",
        call_id="green",
        environment=EvidenceEnvironment("pytest -q", str(tmp_path), "python", "deps", "config"),
    )
    result = await verify_plan_acceptance(
        ExecutionPlan("p", "bugfix", (step,)), _deps(tmp_path), evidence=(proof,)
    )
    assert not result.ok
    assert any(item.status is EvidenceStatus.UNVERIFIED for item in result.evidence)


async def test_final_out_of_scope_discovery_check_is_explicit_and_not_success(tmp_path):
    from dataclasses import replace

    check = VerificationCheck("discovery", VerificationCheckKind.FILE_EXISTS, "unknown.py")
    step = replace(
        _file_step("unknown.py"),
        expected_effects=(),
        status=StepStatus.COMPLETED,
        success_criteria=("discovery",),
        verification_checks=(check,),
    )
    result = await verify_plan_acceptance(
        ExecutionPlan("p", "Dosyaları incele", (step,)), _deps(tmp_path)
    )
    assert result.ok
    criterion = next(item for item in result.evidence if item.criterion_id == "discovery")
    assert criterion.status is EvidenceStatus.UNVERIFIED
    assert criterion.applicable is False


async def test_final_reproduction_rejects_environment_changed_after_green(tmp_path):
    import sys
    from dataclasses import replace

    from fusion_cli.engines.agent.verify_discovery import evidence_environment, source_digest

    command = "python -m pytest -q"
    check = VerificationCheck("bug", VerificationCheckKind.REPRODUCTION, command)
    step = replace(
        _file_step("app.py"),
        expected_effects=(),
        status=StepStatus.COMPLETED,
        success_criteria=("bug",),
        verification_checks=(check,),
    )
    (tmp_path / "app.py").write_text("value = 1\n")
    identity = evidence_environment(tmp_path, (command,), runtime=sys.version)
    source = source_digest(tmp_path)
    proof = CriterionEvidence(
        "bug",
        VerificationCheckKind.REPRODUCTION,
        EvidenceStatus.PASSED,
        "geçmiş ölçüm",
        command=command,
        source_digest=source,
        source_after_digest=source,
        call_id="green",
        environment=identity,
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts=-x\n")
    result = await verify_plan_acceptance(
        ExecutionPlan("p", "bugfix", (step,)), _deps(tmp_path), evidence=(proof,)
    )
    assert not result.ok
    assert result.evidence[-1].status is EvidenceStatus.UNVERIFIED


@pytest.mark.parametrize("mixed", [True, False])
async def test_shared_checks_survive_step_checkpoint_and_final(tmp_path, monkeypatch, mixed):
    from dataclasses import replace

    from fusion_cli.core.checkpoint import StepCheckpointEvidence
    from fusion_cli.engines.agent.loop import run_agent
    from fusion_cli.engines.agent.turn_report import TurnReport, evidence_payload
    from fusion_cli.memory.checkpoint_evidence import evidence_payload as checkpoint_payload
    from fusion_cli.memory.checkpoint_evidence import parse_evidence
    from tests.fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from tests.test_agent_loop import _deps as loop_deps
    from tests.test_agent_loop import _kur

    (tmp_path / "a.txt").write_text("ölçülen içerik\n")
    first = tool_call("run_shell", command="true")
    second = (
        tool_call("read_file", path="a.txt")
        if mixed
        else replace(tool_call("run_shell", command="printf second"), id="second-command")
    )
    deps = loop_deps(tmp_path, RecordingSink())
    _kur(
        monkeypatch,
        ScriptedProvider(
            [model_result(tool_calls=(first, second)), model_result("İki kontrol çalıştırıldı.")]
        ),
    )
    outcome = await run_agent("İki kontrolü çalıştır ve sonucu bildir.", deps)
    assert len(outcome.tool_uses) == 2
    checks = (
        VerificationCheck("all", VerificationCheckKind.COMMAND, "true"),
        VerificationCheck("all", VerificationCheckKind.TOOL, "read_file", '{"path":"a.txt"}')
        if mixed
        else VerificationCheck("all", VerificationCheckKind.COMMAND, "printf second"),
    )
    step = replace(
        _file_step("a.txt"),
        expected_effects=(),
        success_criteria=("all",),
        verification_checks=checks,
        status=StepStatus.COMPLETED,
    )
    checked = await verify_step(step, outcome, _deps(tmp_path))
    proofs = tuple(item for item in checked.criteria if item.criterion_id == "all")
    assert checked.ok
    assert len(proofs) == 2
    loaded = parse_evidence(
        checkpoint_payload(
            (StepCheckpointEvidence(step.step_id, criteria=proofs, tool_uses=outcome.tool_uses),)
        )
    )
    assert len(loaded[0].criteria) == 2
    final = await verify_plan_acceptance(
        ExecutionPlan("p", "iki kontrol", (step,)), _deps(tmp_path), evidence=loaded[0].criteria
    )
    assert final.ok
    payload = evidence_payload(TurnReport(criteria=loaded[0].criteria, gate=final))
    assert payload["criteria_count"] == 1
    assert payload["criteria"][0]["criterion_id"] == "all"
    assert payload["criteria"][0]["status"] == "passed"


@pytest.mark.parametrize(
    "kind",
    [VerificationCheckKind.COMMAND, VerificationCheckKind.TOOL, VerificationCheckKind.REPRODUCTION],
)
@pytest.mark.parametrize("changed", ["check_target", "check_expected"])
def test_bound_check_rejects_other_target_or_expected_reference(kind, changed):
    from dataclasses import replace

    from fusion_cli.core.evidence import EvidenceEnvironment
    from fusion_cli.engines.agent.step_verification import _bound_check_evidence

    target = "read_file" if kind is VerificationCheckKind.TOOL else "pytest -q test_first.py"
    check = VerificationCheck("all", kind, target, "expected")
    proof = CriterionEvidence(
        "all",
        kind,
        EvidenceStatus.PASSED,
        "ölçüm",
        command=target,
        source_digest="source",
        source_after_digest="source",
        call_id="run",
        environment=EvidenceEnvironment(target, "/repo", "python", "deps", "cfg"),
        check_target=target,
        check_expected="expected",
    )
    assert _bound_check_evidence(check, (proof,), "step", "source").status is EvidenceStatus.PASSED
    wrong = replace(proof, **{changed: "different"})
    assert (
        _bound_check_evidence(check, (wrong,), "step", "source").status is EvidenceStatus.UNVERIFIED
    )


@pytest.mark.parametrize(
    "field,value,passed",
    [
        ("command", "pytest -q test_second.py", False),
        ("command", "", False),
        ("check_target", "", True),
        ("environment_command", "pytest -q test_second.py", False),
        ("legacy_wrong_command", "pytest -q test_second.py", False),
        ("cosmetic_command", "pytest  -q 'test_first.py'", True),
    ],
)
def test_reproduction_binding_requires_its_recorded_command(field, value, passed):
    from dataclasses import replace

    from fusion_cli.core.evidence import EvidenceEnvironment
    from fusion_cli.engines.agent.step_verification import _bound_check_evidence

    command = "pytest -q test_first.py"
    check = VerificationCheck("all", VerificationCheckKind.REPRODUCTION, command)
    proof = CriterionEvidence(
        "all",
        check.kind,
        EvidenceStatus.PASSED,
        "ölçüm",
        command=command,
        source_digest="source",
        source_after_digest="source",
        call_id="run",
        environment=EvidenceEnvironment(command, "/repo", "python", "deps", "cfg"),
        check_target=command,
    )
    if field == "environment_command":
        proof = replace(proof, environment=replace(proof.environment, command=value))
    elif field in {"legacy_wrong_command", "cosmetic_command"}:
        proof = replace(
            proof,
            check_target="",
            command=value,
            environment=replace(proof.environment, command=value),
        )
    else:
        proof = replace(proof, **{field: value})
    result = _bound_check_evidence(check, (proof,), "step", "source")
    assert result.status is (EvidenceStatus.PASSED if passed else EvidenceStatus.UNVERIFIED)
