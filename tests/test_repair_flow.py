"""Üretim araç kanıtı mevcut tur bütçesiyle tek kayıtta yönetilir."""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.budget import BudgetStop, TurnBudget
from fusion_cli.core.repair_ledger import FailureEvidence, FailureOrigin, SourceFingerprint
from fusion_cli.core.tools import ToolResult
from fusion_cli.engines.agent.repair_flow import record_failure_evidence


class Clock:
    def monotonic(self) -> float:
        return 0.0

    def now(self) -> float:
        return 0.0


def budget() -> TurnBudget:
    return TurnBudget(Clock(), None, 2, 1, 1, 1, 3)


def failure(attempt: str) -> ToolResult:
    return ToolResult(
        "ölçüm düştü",
        ok=False,
        failure_evidence=(
            FailureEvidence(
                "video/layout", "overflow", attempt, (SourceFingerprint("src/a.tsx", "hash"),)
            ),
        ),
    )


def test_new_job_same_sources_gets_compact_note_and_existing_budget_cap() -> None:
    turn = budget()
    assert record_failure_evidence(failure("1"), turn).is_new_failure
    repeated = record_failure_evidence(failure("2"), turn)
    assert "yaklaşımı değiştir" in repeated.note
    assert turn.verify_rounds == 2
    assert record_failure_evidence(failure("3"), turn).is_exhausted
    assert turn.stop is BudgetStop.NO_PROGRESS


def test_poll_dedup_does_not_consume_budget_or_supply_progress() -> None:
    turn = budget()
    record_failure_evidence(failure("1"), turn)
    assert not record_failure_evidence(failure("1"), turn).is_new_failure
    assert turn.verify_rounds == 1


def test_legacy_or_provider_result_does_not_change_repair_budget() -> None:
    turn = budget()
    record_failure_evidence(ToolResult.failure("generic shell"), turn)
    item = failure("1").failure_evidence[0]
    result = replace(failure("1"), failure_evidence=(replace(item, origin=FailureOrigin.PROVIDER),))
    assert not record_failure_evidence(result, turn).is_new_failure
    assert turn.verify_rounds == 0


def test_multiple_families_in_same_execution_consume_one_repair_round() -> None:
    turn = budget()
    item = failure("1").failure_evidence[0]
    result = replace(failure("1"), failure_evidence=(item, replace(item, family="overlap")))
    record_failure_evidence(result, turn)
    assert turn.verify_rounds == 1


def test_observation_keeps_call_evidence_but_does_not_refresh_progress(tmp_path) -> None:
    from fusion_cli.engines.agent import loop

    from .fakes import RecordingSink
    from .test_turn_budget import _deps

    deps = _deps(tmp_path, RecordingSink())
    state = loop._State(tool_calls_made=3, observation_calls=3)
    assert loop._progress_marker(deps, state)[0] == 0
    assert state.tool_calls_made == 3


async def test_real_loop_halts_before_fourth_model_call_with_unverified_delivery(
    monkeypatch, tmp_path
) -> None:
    from fusion_cli.core.events import ToolOutcome
    from fusion_cli.engines.agent import loop

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import _deps, _kur

    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("run_shell", command=f"render-{number}")])
            for number in range(4)
        ]
    )
    _kur(monkeypatch, provider)
    executed: list[str] = []

    async def execute(call, args, deps, registry, **kwargs):
        executed.append(call.id)
        return failure(str(len(executed))), ToolOutcome.FAILED

    monkeypatch.setattr(loop, "_execute", execute)
    deps = _deps(tmp_path, RecordingSink())
    result = await loop.run_agent("videoyu üret", deps, self_review=False, verify=False)
    assert len(executed) == 3
    assert not result.ok and "ürün sonucu doğrulanmadı" in result.final_text
    assert any("yaklaşımı değiştir" in item.content for item in result.messages)


async def test_real_loop_duplicate_launch_cannot_spawn_second_process(
    monkeypatch, tmp_path
) -> None:
    from types import SimpleNamespace

    from fusion_cli.engines.agent import loop
    from fusion_cli.tools import jobs

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import TAM_CEVAP, _deps, _kur

    (tmp_path / "a.tsx").write_text("fixture")
    spawned = []
    original_popen = jobs.subprocess.Popen

    def popen(*args, **kwargs):
        if not isinstance(args[0], str):
            return original_popen(*args, **kwargs)
        spawned.append(args)
        # Yeni sahiplik sözleşmesi tamamlanmış süreçte bile wait/poll kullanır.
        return SimpleNamespace(pid=123456789, wait=lambda timeout=None: 0, poll=lambda: 0)

    monkeypatch.setattr(jobs.subprocess, "Popen", popen)
    arguments = {
        "command": "echo fixture",
        "background": True,
        "failure_check": "layout",
        "failure_sources": ["a.tsx"],
    }
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("run_shell", **arguments)]),
            model_result(tool_calls=[tool_call("run_shell", **arguments)]),
            model_result(TAM_CEVAP),
        ]
    )
    _kur(monkeypatch, provider)
    await loop.run_agent(
        "video üret", _deps(tmp_path, RecordingSink()), self_review=False, verify=False
    )
    assert len(spawned) == 1


def test_changed_padding_family_note_keeps_existing_budget() -> None:
    turn = budget()
    record_failure_evidence(failure("1"), turn)
    item = failure("2").failure_evidence[0]
    changed = replace(item, sources=(SourceFingerprint("src/a.tsx", "padding-change"),))
    result = replace(failure("2"), failure_evidence=(changed,))
    feedback = record_failure_evidence(result, turn)
    assert "kök nedeni" in feedback.note
    assert "aynı hata ailesi" in feedback.note
    assert turn.verify_rounds == 2
    assert not record_failure_evidence(result, turn).is_new_failure
    assert turn.verify_rounds == 2
    assert record_failure_evidence(failure("3"), turn).is_exhausted
    assert turn.stop is BudgetStop.NO_PROGRESS
