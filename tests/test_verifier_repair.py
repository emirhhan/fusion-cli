"""Final doğrulayıcı mevcut hakkı ikinci kez tüketmeden onarım kanıtını taşır."""

from dataclasses import replace

from fusion_cli.core.repair_ledger import FailureEvidence, FailureOrigin, SourceFingerprint
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.verification import CompositeVerifier
from fusion_cli.engines.agent.verifier_repair import observe_verifier_failures
from tests.test_repair_flow import budget


def result(attempt, digest="first", origin=FailureOrigin.PRODUCT):
    return VerificationResult(
        ok=False,
        failure_evidence=(
            FailureEvidence(
                "audit", "layout_audit", attempt, (SourceFingerprint("scene.tsx", digest),), origin
            ),
        ),
    )


def test_last_reserved_round_keeps_correction_and_does_not_consume_twice():
    turn = budget()
    assert turn.take_verify_round()
    assert observe_verifier_failures(result("one"), turn) == ""
    assert turn.take_verify_round()
    note = observe_verifier_failures(result("two", "padding"), turn)
    assert "kök nedeni" in note
    assert turn.verify_rounds == 2 and turn.stop is None
    assert observe_verifier_failures(result("two", "padding"), turn) == ""
    assert not turn.take_verify_round()


def test_unknown_and_infrastructure_do_not_create_product_recurrence():
    turn = budget()
    assert observe_verifier_failures(VerificationResult(ok=False), turn) == ""
    assert observe_verifier_failures(result("one", origin=FailureOrigin.PROVIDER), turn) == ""
    assert turn.repair_ledger.snapshot().failures == ()


async def test_composite_preserves_typed_failure_without_generic_inference():
    class Verifier:
        async def verify(self):
            return result("one")

    combined = await CompositeVerifier((Verifier(),)).verify()
    assert combined.failure_evidence == result("one").failure_evidence
    assert observe_verifier_failures(replace(combined, ok=True), budget()) == ""


async def test_real_agent_passes_recurrence_note_to_last_correction(monkeypatch, tmp_path):
    from fusion_cli.engines.agent import loop

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import TAM_CEVAP, _deps, _kur

    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("write_file", path="scene.tsx", content="scene")]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, RecordingSink())
    deps.budget = budget()
    calls = []

    class Verifier:
        async def verify(self):
            return result(str(len(calls)), str(len(calls)))

    async def correction(verification, outcome, deps):
        calls.append(verification)
        return outcome

    deps.verifier = Verifier()
    monkeypatch.setattr(loop, "_fix_findings", correction)
    await loop.run_agent("sahne yaz", deps, self_review=False, verify=True)
    assert len(calls) == 2
    assert any("kök nedeni" in finding for finding in calls[-1].findings)
    assert deps.budget.verify_rounds == 2
