"""Plan adımı post-condition doğrulaması."""

from __future__ import annotations

from fusion_cli.core.execution_plan import PlanStep, RetrySafety
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome
from fusion_cli.engines.agent.step_verification import verify_step

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
