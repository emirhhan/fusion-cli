"""Internal desktop observation bytes must not become unsolicited user deliverables."""

from dataclasses import replace

import pytest

from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop
from fusion_cli.tools import desktop_screen
from tests.test_desktop_screen import _retina
from tests.test_teacher_first import _setup

CALCULATOR = "Hesap Makinesi'nde 37 × 16 işlemini yap ve sonucu ekranda doğrula."


async def _run(monkeypatch, tmp_path, task=CALCULATOR, *, mode="capture", deps=None):
    _retina(monkeypatch)
    if deps is None:
        deps, *_ = _setup(monkeypatch, tmp_path)
        deps.config = replace(
            deps.config,
            teacher=None,
            runtime=replace(
                deps.config.runtime,
                self_review=False,
            ),
        )

    async def drive(_messages, current, _registry, **_kwargs):
        context = current.tool_context
        path = tmp_path / desktop_screen.DEFAULT_SCREENSHOT_PATH
        args = {"path": "export.png"} if mode == "export" else {}
        if mode == "export_then_capture":
            args = {"path": desktop_screen.DEFAULT_SCREENSHOT_PATH}
        if mode in {"capture", "export", "overwritten", "samepath_export", "export_then_capture"}:
            result = desktop_screen.desktop_screenshot(args, context)
            assert result.ok, result.output
            if mode in {"samepath_export", "export_then_capture"}:
                before = path.read_bytes()
                args = (
                    {"path": desktop_screen.DEFAULT_SCREENSHOT_PATH}
                    if mode == "samepath_export"
                    else {}
                )
                result = desktop_screen.desktop_screenshot(args, context)
                assert result.ok, result.output
                assert path.read_bytes() == before
            if mode == "export":
                path = tmp_path / "export.png"
            if mode == "overwritten":
                path.write_bytes(b"user replacement")
                context.changes.record_applied(path)
        elif mode != "old":
            path.parent.mkdir(parents=True, exist_ok=True)
            context.changes.record(path)
            path.write_bytes(b"ordinary user PNG fixture")
            context.changes.record_applied(path)
            context.touched.add(path)
        # A tool-name/output lookalike is intentionally not trusted capture provenance.
        uses = (
            ToolUse(
                "desktop_screenshot" if mode != "ordinary" else "write_file",
                output=f"Ekran görüntüsü: {path}",
                arguments=args,
                mutating=True,
            ),
        )
        context.desktop.invalidate_capture(clear_frame=True)
        return loop.AgentOutcome(
            "37 × 16 = 592; sonuç Hesap Makinesi'nde görüldü.", [], tool_uses=uses
        )

    monkeypatch.setattr(loop, "_drive", drive)
    outcome = await loop.run_agent(task, deps, verify=False)
    return outcome, deps


async def test_real_capture_report_omits_unsolicited_artifact_but_preserves_truth_and_ownership(
    monkeypatch,
    tmp_path,
):
    outcome, deps = await _run(monkeypatch, tmp_path)
    assert "Görsel / belge çıktıları" not in outcome.final_text
    assert "Dosyanın kaydedilmesi" not in outcome.final_text
    assert outcome.final_text == "37 × 16 = 592; sonuç Hesap Makinesi'nde görüldü."
    path = tmp_path / desktop_screen.DEFAULT_SCREENSHOT_PATH
    assert path.is_file() and path in deps.tool_context.touched
    assert path in deps.tool_context.changes.paths
    report = outcome.completion_report
    assert report is not None
    assert report.changed_paths == (desktop_screen.DEFAULT_SCREENSHOT_PATH,)
    assert report.is_verified is False, "presentation must not manufacture verification"
    assert not report.blocks_success
    failed = replace(
        report, gate=VerificationResult(False, findings=("actual measurement failed",))
    )
    assert failed.blocks_success
    assert "actual measurement failed" in failed.render()


@pytest.mark.parametrize(
    "task",
    [
        "Ekran görüntüsü al ve dosyayı bana ver.",
        "Ekran fotoğrafını çekip bana ver.",
        "Ekran fotografini cekip bana ver.",
        "Take a screenshot and save it for me.",
        "37 × 16 sonucunu sonuc.png olarak kaydet.",
    ],
)
async def test_explicit_screenshot_or_output_request_keeps_artifact_caveat(
    monkeypatch, tmp_path, task
):
    outcome, _ = await _run(monkeypatch, tmp_path, task)
    assert "Görsel / belge çıktıları" in outcome.final_text
    assert "Dosyanın kaydedilmesi" in outcome.final_text


@pytest.mark.parametrize(
    "mode",
    ["ordinary", "lookalike", "export", "overwritten", "samepath_export", "export_then_capture"],
)
async def test_user_png_untrusted_lookalike_export_or_changed_bytes_are_not_hidden(
    monkeypatch,
    tmp_path,
    mode,
):
    outcome, _ = await _run(monkeypatch, tmp_path, mode=mode)
    assert "Görsel / belge çıktıları" in outcome.final_text


async def test_capture_from_other_turn_is_not_reused_as_presentation_authority(
    monkeypatch, tmp_path
):
    _, deps = await _run(monkeypatch, tmp_path)
    old_turn = deps.original_cursor.turn_id
    outcome, _ = await _run(monkeypatch, tmp_path, mode="old", deps=deps)
    assert deps.original_cursor.turn_id != old_turn
    assert "Görsel / belge çıktıları" in outcome.final_text


def test_capture_started_in_old_turn_cannot_gain_new_turn_presentation_ownership(
    monkeypatch,
    tmp_path,
):
    from fusion_cli.core.tools import ToolContext
    from tests.test_desktop_screen import _png

    _retina(monkeypatch)
    context = ToolContext(tmp_path)
    context.desktop.begin_observation_turn("old-turn")

    def capture_across_turn(*_args, **_kwargs):
        context.desktop.begin_observation_turn("new-turn")
        return _png(100, 100)

    monkeypatch.setattr(desktop_screen, "_native_capture", capture_across_turn)
    result = desktop_screen.desktop_screenshot({}, context)
    assert result.ok
    assert context.desktop.observation_artifact_paths("new-turn") == ()


@pytest.mark.parametrize("exit_code", [1, None])
def test_internal_capture_presentation_cannot_hide_failed_or_unknown_command_evidence(exit_code):
    from fusion_cli.engines.agent.turn_report import CommandRun, TurnReport

    path = (".fusion/tmp/masaustu-ekrani.png",)
    report = TurnReport(
        changed_paths=path,
        internal_observation_paths=path,
        command_runs=(CommandRun("pytest -q", exit_code, True),),
    )
    assert report.blocks_success
    assert "pytest -q" in report.render()
    assert report.render_with_model_text("All tests passed.") != "All tests passed."


def test_internal_capture_presentation_cannot_hide_false_claim_warning():
    from fusion_cli.engines.agent.turn_report import TurnReport

    path = (".fusion/tmp/masaustu-ekrani.png",)
    report = TurnReport(changed_paths=path, internal_observation_paths=path, false_claim=True)
    assert report.blocks_success
    assert report.render()
    assert report.render_with_model_text("All tests passed.") != "All tests passed."
