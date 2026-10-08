"""Tamamlanma receipt'i son kaynak ve ürün değişikliğini örtemez."""

import pytest

from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.turn_report import build_turn_report
from fusion_cli.tools import jobs, shell
from fusion_cli.tools.job_current import snapshot_current_jobs


def completed(tmp_path, source_scope="src", job_command="echo video > out.mp4"):
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src/a.tsx").write_text("original")
    context = ToolContext(root=tmp_path)
    start = shell.run_shell(
        {
            "command": job_command,
            "background": True,
            "failure_check": "render",
            "failure_sources": [source_scope],
            "expected_outputs": ["out.mp4"],
        },
        context,
    )
    done = jobs.job_status({"id": start.job_completion.job_id, "wait_s": 10}, context)
    assert done.job_completion.exit_code == 0
    uses = (
        ToolUse("run_shell", job_completion=start.job_completion),
        ToolUse("job_status", job_completion=done.job_completion),
    )
    return context, uses, done.job_completion


def test_render_sonrasi_kaynak_degisse_yeni_kare_kapisi_eski_mp4u_dogrulamaz(tmp_path):
    _, uses, _ = completed(tmp_path)
    (tmp_path / "src/a.tsx").write_text("changed after render")
    report = build_turn_report(
        (), uses, VerificationResult(ok=True), current_jobs=snapshot_current_jobs(tmp_path, uses)
    )
    assert report.blocks_success


@pytest.mark.parametrize("change", ["overwrite", "delete", "add_source", "delete_source"])
def test_tamamlanma_sonrasi_urun_ve_kapsam_mutasyonu_engellenir(tmp_path, change):
    _, uses, receipt = completed(tmp_path)
    if change == "overwrite":
        (tmp_path / "out.mp4").write_text("different video")
    elif change == "delete":
        (tmp_path / "out.mp4").unlink()
    elif change == "add_source":
        (tmp_path / "src/new.tsx").write_text("new member")
    else:
        (tmp_path / "src/a.tsx").unlink()
    report = build_turn_report((), uses, None, current_jobs=snapshot_current_jobs(tmp_path, uses))
    assert report.blocks_success
    # Kapanış ölçümü geçmiş kanıtı yeniden yazmaz.
    assert receipt == uses[-1].job_completion


def test_degismemis_kapsam_ve_legacy_surec_tamamlanmasi_korunur(tmp_path):
    from fusion_cli.core.job_evidence import JobCompletion, JobPhase

    _, uses, receipt = completed(tmp_path)
    assert receipt.source_scopes == ("src",)
    report = build_turn_report((), uses, None, current_jobs=snapshot_current_jobs(tmp_path, uses))
    assert not report.blocks_success
    legacy = (
        ToolUse("run_shell", job_completion=JobCompletion("old", "echo ok", JobPhase.STARTED)),
        ToolUse(
            "job_status", job_completion=JobCompletion("old", "echo ok", JobPhase.COMPLETED, 0)
        ),
    )
    report = build_turn_report(
        (), legacy, None, current_jobs=snapshot_current_jobs(tmp_path, legacy)
    )
    assert not report.blocks_success
    assert "görsel kalite ayrıca" in report.render()


def test_sir_ve_dis_kok_baglantisi_hash_okumadan_engellenir(tmp_path, monkeypatch):
    from pathlib import Path

    _, uses, _ = completed(tmp_path)
    secret = tmp_path / "src/.env.json"
    secret.write_text("not read")
    original = Path.read_bytes

    def guarded(path):
        assert path != secret
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    snapshot = snapshot_current_jobs(tmp_path, uses)
    assert snapshot[0].problem
    secret.unlink()
    outside = tmp_path.parent / (tmp_path.name + "-outside.tsx")
    (tmp_path / "src/link.tsx").symlink_to(outside)
    assert snapshot_current_jobs(tmp_path, uses)[0].problem


def test_taze_ayni_kapsam_retry_eski_teslimi_cozer(tmp_path):
    command = "cat src/a.tsx > out.mp4"
    _, first, _ = completed(tmp_path, job_command=command)
    (tmp_path / "src/a.tsx").write_text("updated source")
    context = ToolContext(root=tmp_path)
    start = shell.run_shell(
        {
            "command": command,
            "background": True,
            "failure_check": "render",
            "failure_sources": ["src"],
            "expected_outputs": ["out.mp4"],
        },
        context,
    )
    done = jobs.job_status({"id": start.job_completion.job_id, "wait_s": 10}, context)
    assert done.job_completion.exit_code == 0
    uses = (
        *first,
        ToolUse("run_shell", job_completion=start.job_completion),
        ToolUse("job_status", job_completion=done.job_completion),
    )
    report = build_turn_report((), uses, None, current_jobs=snapshot_current_jobs(tmp_path, uses))
    assert not report.blocks_success
    assert report.job_deliveries[0].is_superseded


async def test_gercek_agent_kapanisi_render_sonrasi_yazilan_kaynakta_eski_mp4u_engeller(
    monkeypatch, tmp_path
):
    from types import SimpleNamespace

    from fusion_cli.engines.agent import loop

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import TAM_CEVAP, _deps, _kur

    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.tsx").write_text("before")
    monkeypatch.setattr(
        jobs, "uuid", SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="abcdef12"))
    )
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        tool_call(
                            "run_shell",
                            command="cat src/a.tsx > out.mp4",
                            background=True,
                            failure_check="render",
                            failure_sources=["src"],
                            expected_outputs=["out.mp4"],
                        )
                    ]
                ),
                model_result(tool_calls=[tool_call("job_status", id="abcdef12", wait_s=10)]),
                model_result(
                    tool_calls=[tool_call("edit_file", path="src/a.tsx", old="before", new="after")]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    result = await loop.run_agent(
        "video üret", _deps(tmp_path, RecordingSink()), self_review=False, verify=False
    )
    assert not result.ok, [(use.name, use.output) for use in result.tool_uses]
    assert "tamamlandıktan sonra kaynak değişti" in result.final_text
    poll = next(use for use in result.tool_uses if use.name == "job_status")
    assert poll.job_completion.sources_before == poll.job_completion.sources_after


def test_sonraki_farkli_kaynak_kapsami_onceki_hatasi_cozemez(tmp_path):
    from dataclasses import replace

    _, uses, _ = completed(tmp_path)
    (tmp_path / "src/a.tsx").write_text("after")
    current = snapshot_current_jobs(tmp_path, uses)[0]
    fresh = tuple(
        replace(
            use,
            job_completion=replace(
                use.job_completion,
                job_id="different",
                source_scopes=("src/a.tsx",),
                sources_before=current.sources,
                sources_after=current.sources if use.job_completion.exit_code == 0 else (),
            ),
        )
        for use in uses
    )
    snapshots = (current, replace(current, job_id="different"))
    report = build_turn_report((), (*uses, *fresh), None, current_jobs=snapshots)
    assert not report.job_deliveries[1].problem
    assert report.blocks_success and not report.job_deliveries[0].is_superseded
