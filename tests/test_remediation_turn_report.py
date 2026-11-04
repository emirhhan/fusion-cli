"""Toparlanan hata bütün başarı kararlarında aynı kapsamla aşılır."""

from __future__ import annotations

from fusion_cli.engines.agent.turn_report import CommandRun, TurnReport


def test_same_scope_passing_retry_supersedes_failure_in_every_decision():
    report = TurnReport(
        changed_paths=("app.py",),
        command_runs=(
            CommandRun("pytest -q", 1, True),
            CommandRun("pytest -q", 0, True),
        ),
    )
    assert report.is_verified is True
    assert report.blocks_success is False


def test_other_scope_passing_test_does_not_hide_failure():
    report = TurnReport(
        changed_paths=("app.py",),
        command_runs=(
            CommandRun("pytest tests/api.py", 1, True),
            CommandRun("pytest tests/ui.py", 0, True),
        ),
    )
    assert report.is_verified is False
    assert report.blocks_success is True


def test_unmeasured_browser_is_preserved_even_when_unrelated_pytest_passes():
    from fusion_cli.core.evidence import ToolUse
    from fusion_cli.engines.agent.browser_verify import _not_measured
    from fusion_cli.engines.agent.completion_evidence import evidence_payload
    from fusion_cli.engines.agent.turn_report import build_turn_report

    report = build_turn_report(
        ("index.html",),
        (
            ToolUse("write_file", mutating=True),
            ToolUse("run_shell", arguments={"command": "pytest -q"}, output="(çıkış kodu 0)"),
        ),
        gate=_not_measured("Playwright kurulu değil"),
    )
    payload = evidence_payload(report)
    assert payload["dogrulandi"] is False
    assert payload["engelliyor"] is False
    assert payload["criteria_status_counts"]["unverified"] == 1
    assert payload["uyarilar"] and "Playwright" in payload["uyarilar"][0]
    assert "✓ Doğrulandı" not in report.render()


def test_plain_answer_without_delivery_does_not_emit_unverified_delivery_badge():
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    assert evidence_payload(TurnReport()) is None
