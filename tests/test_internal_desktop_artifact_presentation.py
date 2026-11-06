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


async def _verified_capture_chain(
    monkeypatch, tmp_path, task=CALCULATOR, *, export=False, last_region=False
):
    import io

    from PIL import Image

    from fusion_cli.engines.agent.verification import build_verifier

    _retina(monkeypatch)
    payloads = []
    for color in ("red", "green", "blue"):
        buffer = io.BytesIO()
        Image.new("RGB", (16, 16), color).save(buffer, format="PNG")
        payloads.append(buffer.getvalue())
    monkeypatch.setattr(desktop_screen, "_native_capture", lambda *a, **kw: payloads.pop(0))
    monkeypatch.setattr(desktop_screen, "_shrink", lambda *a: None)
    deps, *_ = _setup(monkeypatch, tmp_path)
    deps.config = replace(
        deps.config,
        teacher=None,
        runtime=replace(
            deps.config.runtime,
            self_review=False,
        ),
    )
    deps.verifier = build_verifier(deps.config, root=tmp_path, tool_context=deps.tool_context)

    async def drive(_messages, current, _registry, **kwargs):
        uses = []
        for args in (
            {},
            {"region": "0,0,1,1"},
            {"path": desktop_screen.DEFAULT_SCREENSHOT_PATH}
            if export
            else ({"region": "0,0,1,1"} if last_region else {}),
        ):
            result = desktop_screen.desktop_screenshot(args, current.tool_context)
            assert result.ok, result.output
            uses.append(
                ToolUse("desktop_screenshot", output=result.output, arguments=args, mutating=True)
            )
        return loop.AgentOutcome(
            "83 + 29 = 112; sonuç ekranda doğrulandı.",
            [],
            tool_uses=tuple(uses),
            tool_calls_made=3,
            mutating_tool_calls_made=3,
        )

    monkeypatch.setattr(loop, "_drive", drive)
    outcome = await loop.run_agent(task, deps, verify=True)
    return outcome, deps


async def test_full_region_full_real_verifier_does_not_turn_internal_capture_into_deliverable(
    monkeypatch,
    tmp_path,
):
    from fusion_cli.engines.agent.turn_evidence import evidence_from_turn
    from fusion_cli.engines.agent.turn_report import summarize_evidence

    outcome, deps = await _verified_capture_chain(monkeypatch, tmp_path)
    report = outcome.completion_report
    assert report is not None
    assert not report.gate.evidence and not report.gate.warnings
    assert outcome.final_text == "83 + 29 = 112; sonuç ekranda doğrulandı."
    assert report.is_verified is False  # no formal behavioral verification manufactured
    assert not summarize_evidence(report).unmeasured
    assert not evidence_from_turn(outcome, deps.tool_context).changed_files
    path = tmp_path / desktop_screen.DEFAULT_SCREENSHOT_PATH
    assert path in deps.tool_context.changes.paths and path in deps.tool_context.touched


@pytest.mark.parametrize("export", [False, True])
async def test_real_verifier_keeps_requested_screenshot_or_explicit_samepath_export(
    monkeypatch,
    tmp_path,
    export,
):
    task = CALCULATOR if export else "Ekran görüntüsünü al ve bana ver."
    outcome, _ = await _verified_capture_chain(monkeypatch, tmp_path, task, export=export)
    assert "Görsel / belge dosyası kaydı" in outcome.final_text
    assert outcome.completion_report.gate.evidence


async def test_default_then_region_recapture_keeps_latest_bytes_internal(monkeypatch, tmp_path):
    outcome, deps = await _verified_capture_chain(monkeypatch, tmp_path, last_region=True)
    assert outcome.final_text == "83 + 29 = 112; sonuç ekranda doğrulandı."
    assert not outcome.completion_report.gate.evidence
    path = tmp_path / desktop_screen.DEFAULT_SCREENSHOT_PATH
    assert deps.tool_context.desktop.observation_artifact_paths(deps.original_cursor.turn_id) == (
        path,
    )


@pytest.mark.parametrize("replace_capture", [False, True])
async def test_delivery_projection_keeps_real_artifact_failure_and_changed_capture(
    monkeypatch,
    tmp_path,
    replace_capture,
):
    from fusion_cli.engines.agent.artifact_verify import ArtifactChangeVerifier
    from fusion_cli.engines.agent.observation_delivery import delivery_change_paths

    _, deps = await _verified_capture_chain(monkeypatch, tmp_path)
    context = deps.tool_context
    path = (
        tmp_path / desktop_screen.DEFAULT_SCREENSHOT_PATH
        if replace_capture
        else tmp_path / "user.png"
    )
    context.changes.record(path)
    path.write_bytes(b"invalid user replacement")
    context.changes.record_applied(path)
    context.touched.add(path)
    result = await ArtifactChangeVerifier(context).verify()
    assert not result.ok and any(path.name in finding for finding in result.findings)
    assert path in delivery_change_paths(context)
    if not replace_capture:
        assert tmp_path / desktop_screen.DEFAULT_SCREENSHOT_PATH not in delivery_change_paths(
            context
        )
