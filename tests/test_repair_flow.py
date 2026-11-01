"""Üretim araç kanıtı mevcut tur bütçesiyle tek kayıtta yönetilir."""

from __future__ import annotations

from dataclasses import replace

import pytest

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


async def test_real_infrastructure_failure_cannot_consume_repair_budget(tmp_path):
    from fusion_cli.engines.agent.verification import CommandVerifier
    from fusion_cli.engines.agent.verifier_repair import observe_verifier_failures

    result = await CommandVerifier(
        ("fusion_fixture_missing_runner",), cwd=str(tmp_path), timeout_s=3
    ).verify()
    assert result.failure_evidence
    turn = budget()
    tool_result = ToolResult("ölçüm yapılamadı", ok=False, failure_evidence=result.failure_evidence)
    assert not record_failure_evidence(tool_result, turn).is_new_failure
    assert observe_verifier_failures(result, turn) == ""
    assert turn.verify_rounds == 0
    assert turn.repair_ledger.snapshot().failures == ()


async def test_selected_missing_python_runner_is_infrastructure_but_product_import_is_not(tmp_path):
    import shlex
    import sys

    from fusion_cli.engines.agent.verification import CommandVerifier

    python = shlex.quote(sys.executable)
    missing = await CommandVerifier(
        (f"{python} -I -S -m pytest",), cwd=str(tmp_path), timeout_s=3
    ).verify()
    assert missing.failure_evidence[0].origin is FailureOrigin.INFRASTRUCTURE
    turn = budget()
    result = ToolResult("koşucu yok", ok=False, failure_evidence=missing.failure_evidence)
    assert not record_failure_evidence(result, turn).is_new_failure
    assert turn.verify_rounds == 0
    source = tmp_path / "product.py"
    source.write_text("import fixture_missing_product_dependency\n")
    product = await CommandVerifier(
        (f"{python} product.py",), cwd=str(tmp_path), timeout_s=3
    ).verify()
    assert product.failure_evidence[0].origin is FailureOrigin.PRODUCT


@pytest.mark.parametrize("origin", ("infrastructure", "provider"))
async def test_real_loop_infrastructure_has_no_product_correction_or_budget_charge(
    monkeypatch, tmp_path, origin
):
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.verification import CommandVerifier

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import TAM_CEVAP, _deps, _kur

    provider = ScriptedProvider(
        [
            model_result(
                tool_calls=[tool_call("write_file", path="initial.txt", content="fixture")]
            ),
            model_result(TAM_CEVAP),
        ]
    )
    _kur(monkeypatch, provider)
    deps = _deps(tmp_path, RecordingSink())
    deps.verifier = (
        CommandVerifier(("true",), cwd=str(tmp_path / "wrong"), timeout_s=3)
        if origin == "infrastructure"
        else CommandVerifier(
            ("printf 'provider quota exceeded HTTP 429'; exit 1",), cwd=str(tmp_path), timeout_s=3
        )
    )
    result = await loop.run_agent("değişikliği yap", deps, internal=True, self_review=False)
    assert not result.ok
    assert (tmp_path / "initial.txt").read_text() == "fixture"
    assert provider.calls == result.model_calls_made == 2
    assert deps.require_budget().verify_rounds == 0
    assert deps.require_budget().repair_ledger.snapshot().failures == ()


async def test_real_loop_product_failure_still_gets_existing_correction_budget(
    monkeypatch, tmp_path
):
    import shlex
    import sys

    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.verification import CommandVerifier

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import TAM_CEVAP, _deps, _kur

    provider = ScriptedProvider(
        [
            model_result(
                tool_calls=[tool_call("write_file", path="initial.txt", content="fixture")]
            ),
            model_result(TAM_CEVAP),
            model_result(tool_calls=[tool_call("write_file", path="fixed.txt", content="fixed")]),
            model_result(TAM_CEVAP),
        ]
    )
    _kur(monkeypatch, provider)
    script = "from pathlib import Path; assert Path('fixed.txt').is_file()"
    deps = _deps(tmp_path, RecordingSink())
    deps.verifier = CommandVerifier(
        (f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}",), cwd=str(tmp_path), timeout_s=3
    )
    result = await loop.run_agent("değişikliği yap", deps, internal=True, self_review=False)
    assert result.ok
    assert (tmp_path / "fixed.txt").read_text() == "fixed"
    assert provider.calls == result.model_calls_made == 4
    assert deps.require_budget().verify_rounds == 1


@pytest.mark.parametrize("origin", ("infrastructure", "provider"))
async def test_composite_keeps_real_web_product_failure_repairable_with_nonproduct_failure(
    tmp_path, origin
):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.verification import (
        CommandVerifier,
        CompositeVerifier,
        WebVerifier,
    )
    from fusion_cli.engines.agent.verifier_repair import should_repair_verifier

    context = ToolContext(root=tmp_path)
    html = tmp_path / "index.html"
    html.write_text(
        "<!doctype html><html><head><title>Fixture</title></head>"
        '<body><script src="missing.js"></script></body></html>'
    )
    context.touched.add(html)
    command = (
        CommandVerifier(("true",), cwd=str(tmp_path / "wrong"), timeout_s=3)
        if origin == "infrastructure"
        else CommandVerifier(
            ("printf 'provider quota exceeded HTTP 429'; exit 1",), cwd=str(tmp_path), timeout_s=3
        )
    )
    result = await CompositeVerifier((WebVerifier(context), command)).verify()
    assert not result.ok
    assert any("missing.js" in finding for finding in result.findings)
    assert should_repair_verifier(result)
    assert any(item.origin is FailureOrigin.PRODUCT for item in result.failure_evidence)


@pytest.mark.parametrize("origin", ("infrastructure", "provider"))
async def test_real_loop_repairs_web_product_failure_in_nonproduct_composite(
    monkeypatch, tmp_path, origin
):
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.verification import (
        CommandVerifier,
        CompositeVerifier,
        WebVerifier,
    )

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import TAM_CEVAP, _deps, _kur

    html = (
        "<!doctype html><html><head><title>Fixture</title></head>"
        '<body><script src="missing.js"></script></body></html>'
    )
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("write_file", path="index.html", content=html)]),
            model_result(TAM_CEVAP),
            model_result(
                tool_calls=[tool_call("write_file", path="missing.js", content="void 0;")]
            ),
            model_result(TAM_CEVAP),
        ]
    )
    _kur(monkeypatch, provider)
    deps = _deps(tmp_path, RecordingSink())
    command = (
        CommandVerifier(("true",), cwd=str(tmp_path / "wrong"), timeout_s=3)
        if origin == "infrastructure"
        else CommandVerifier(
            ("printf 'provider quota exceeded HTTP 429'; exit 1",), cwd=str(tmp_path), timeout_s=3
        )
    )
    deps.verifier = CompositeVerifier((WebVerifier(deps.tool_context), command))
    result = await loop.run_agent("sayfayı oluştur", deps, internal=True, self_review=False)
    assert not result.ok  # Altyapı ölçümü hâlâ başarısız; ürün kusuru düzeltildi.
    assert (tmp_path / "missing.js").read_text() == "void 0;"
    assert provider.calls == result.model_calls_made == 4
    assert deps.require_budget().verify_rounds == 1
    assert any(
        item.family == "unclassified_verifier_failure"
        for item in deps.require_budget().repair_ledger.snapshot().failures
    )
