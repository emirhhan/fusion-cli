"""Gerçek teslimat kanıtı ile iç onarım açıklamasını birbirinden ayır."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop, review
from fusion_cli.engines.agent.browser_verify import PageObservation, browser_verification_result
from fusion_cli.engines.agent.contact_form_probe import ContactObservation
from fusion_cli.engines.agent.turn_report import TurnReport
from tests.fakes import RecordingSink
from tests.test_agent_loop import _deps


def partial_report():
    items = (
        CriterionEvidence(
            "cikti:site.html", VerificationCheckKind.TOOL, EvidenceStatus.PASSED, "site.html açıldı"
        ),
        CriterionEvidence(
            "tarayici_sayfalari",
            VerificationCheckKind.TOOL,
            EvidenceStatus.PASSED,
            "1 sayfa tarayıcıda açılıp denetlendi",
        ),
        CriterionEvidence(
            "contact_receipt_truth",
            VerificationCheckKind.TOOL,
            EvidenceStatus.UNVERIFIED,
            "Mesaj teslimatı doğrulanmadı",
        ),
    )
    return TurnReport(
        changed_paths=("site.html",),
        gate=VerificationResult(ok=True, evidence=items),
        criteria=items,
    )


def test_partial_browser_evidence_never_reports_zero_success():
    text = partial_report().render_with_model_text(
        "Tarayıcıda test edildi; mesaj teslimatı doğrulanmadı."
    )
    assert "hiçbir doğrulama başarıyla" not in text
    assert "ÇALIŞTIRILMADI" not in text
    assert "Mesaj teslimatı doğrulanmadı" in text
    assert "1 sayfa" in text


def test_supported_browser_test_is_not_a_false_command_claim(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context.changes.record(tmp_path / "site.html")
    outcome = loop.AgentOutcome("Tarayıcıda test edildi; mesaj teslimatı doğrulanmadı.", [])
    loop._apply_turn_report(outcome, deps, gate=partial_report().gate)
    assert outcome.completion_report is not None
    assert not outcome.completion_report.false_claim


@pytest.mark.asyncio
async def test_internal_repair_delivers_latest_report_without_stale_facts(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    task = (
        "Python sürümünü güncel resmi kaynaklardan araştır, "
        "kısa raporu rapor-son.html dosyasına kaydet."
    )
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    accept_delivery_contract(deps.tool_context, task)
    original = loop.AgentOutcome("Python 3.15.1; rapor hazır.", [])

    async def correction(*args, **kwargs):
        return loop.AgentOutcome("Düzeltme uygulandı: overflow-wrap eklendi.", [], ok=True)

    with patch.object(loop, "_run_verification_correction_attempt", correction):
        repaired = await loop._fix_findings(
            VerificationResult(ok=False, findings=("Yatay taşma",)), original, deps
        )
    deps.tool_context.changes.record(tmp_path / "rapor-son.html")
    (tmp_path / "rapor-son.html").write_text("<h1>Python 3.15.2</h1>")
    evidence = (
        CriterionEvidence(
            "tarayici_sayfalari",
            VerificationCheckKind.TOOL,
            EvidenceStatus.PASSED,
            "1 sayfa tarayıcıda açılıp denetlendi",
        ),
    )
    loop._apply_turn_report(
        repaired, deps, gate=VerificationResult(ok=True, evidence=evidence), task=task
    )
    assert "overflow-wrap" not in repaired.final_text
    assert "rapor-son.html" in repaired.final_text
    assert "3.15.1" not in repaired.final_text


@pytest.mark.parametrize(
    "task,want_demo",
    [
        (
            "İletişim alanı demo olduğunu açıkça söylesin ve mesaj gönderilmiş gibi davranmasın.",
            True,
        ),
        ("Contact form is demo only; do not send messages.", True),
        ("İletişim alanı demo olmasın; mesaj gönderme.", False),
        ("İletişim alanı demo olsun; mesaj gönderme. Ayrıca gerçek mesaj gönder.", False),
        ('"İletişim alanı demo olsun; mesaj gönderme." Bu metni analiz et.', False),
        ("Contact form is not a demo; do not send messages.", False),
        ("İletişim alanı oluştur.", False),
    ],
)
def test_only_explicit_unambiguous_user_demo_contract_is_accepted(tmp_path, task, want_demo):
    from fusion_cli.core.delivery_contract import ContactIntent
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    context = _deps(tmp_path, RecordingSink()).tool_context
    accepted = accept_delivery_contract(context, task)
    assert (accepted.contact is ContactIntent.DEMO_NO_SEND) is want_demo
    previous_id = accepted.accepted_id
    assert accept_delivery_contract(context, "Yeni bir soru").contact is ContactIntent.UNSPECIFIED
    assert context.delivery_contract.accepted.accepted_id != previous_id
    child = replace(context, job_scope="different-owner")
    assert child.delivery_contract.for_owner(child.root, child.job_scope) is None


@pytest.mark.parametrize(
    "intent,disclosure,outcome,status,want",
    [
        ("demo_no_send", True, True, "observed_no_false_receipt", "passed"),
        ("unspecified", True, True, "observed_no_false_receipt", "unverified"),
        ("demo_no_send", False, True, "observed_no_false_receipt", "unverified"),
        ("demo_no_send", True, False, "observed_no_false_receipt", "unverified"),
        ("demo_no_send", True, True, "false_receipt", "failed"),
        ("demo_no_send", True, True, "unverified_transport", "unverified"),
        ("demo_no_send", True, True, "not_measured", "unverified"),
    ],
)
def test_demo_requires_trusted_intent_and_both_positive_observations(
    intent, disclosure, outcome, status, want
):
    from fusion_cli.core.delivery_contract import ContactIntent

    contact = ContactObservation(
        status, visible_demo_disclosure=disclosure, visible_no_send_outcome=outcome
    )
    result = browser_verification_result(
        (PageObservation("index.html", contact_forms=(contact,)),),
        source="tarayıcıda",
        contact_intent=ContactIntent(intent),
    )
    receipt = next(item for item in result.evidence if item.criterion_id == "contact_receipt_truth")
    assert receipt.status.value == want
    if want == "passed":
        assert "gerçek mesaj teslimatı" in receipt.summary
    if status == "false_receipt":
        assert not result.ok


@pytest.mark.parametrize(
    "text",
    [
        "Tüm testler geçti.",
        "All tests passed.",
        "Lint temiz; tarayıcıda test edildi.",
        "Website test edildi. Testler geçti.",
    ],
)
def test_browser_pass_does_not_excuse_broader_success_claims(tmp_path, text):
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context.changes.record(tmp_path / "site.html")
    outcome = loop.AgentOutcome(text, [])
    loop._apply_turn_report(outcome, deps, gate=partial_report().gate)
    assert outcome.completion_report is not None
    assert outcome.completion_report.false_claim
    assert not outcome.ok


def test_repair_does_not_hide_existing_document_css_task(tmp_path):
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    deps = _deps(tmp_path, RecordingSink())
    task = "Mevcut rapor-son.html dosyasındaki CSS taşmasını düzelt, ne değiştirdiğini açıkla."
    contract = accept_delivery_contract(deps.tool_context, task)
    assert contract.document_output is None
    deps.tool_context.changes.record(tmp_path / "rapor-son.html")
    (tmp_path / "rapor-son.html").write_text("<h1>Rapor</h1>")
    outcome = loop.AgentOutcome("overflow-wrap düzeltildi.", [], verification_repaired=True)
    loop._apply_turn_report(outcome, deps, gate=VerificationResult(ok=True), task=task)
    assert "overflow-wrap" in outcome.final_text


def test_browser_verifier_reads_only_current_owner_contract(tmp_path):
    from fusion_cli.core.delivery_contract import ContactIntent
    from fusion_cli.engines.agent.browser_verify import BrowserVerifier
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    context = _deps(tmp_path, RecordingSink()).tool_context
    verifier = BrowserVerifier(context)
    accept_delivery_contract(context, "İletişim alanı demo olsun; mesaj gönderme.")
    assert verifier._contact_intent() is ContactIntent.DEMO_NO_SEND
    child = BrowserVerifier(replace(context, job_scope="child"))
    assert child._contact_intent() is ContactIntent.UNSPECIFIED
    accept_delivery_contract(context, "Gerçek iletişim formunu bağla.")
    assert verifier._contact_intent() is ContactIntent.UNSPECIFIED


@pytest.mark.parametrize(
    "task",
    [
        "'İletişim alanı demo olsun; mesaj gönderme.' Örneği değerlendir.",
        "İletişim alanında demo ne demek? Mesaj gönderme.",
        "Contact demo is not wanted; do not send messages.",
        "Contact form demo is disabled; do not send messages.",
    ],
)
def test_quoted_question_or_negated_demo_is_not_an_accepted_demo_request(tmp_path, task):
    from fusion_cli.core.delivery_contract import ContactIntent
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    context = _deps(tmp_path, RecordingSink()).tool_context
    assert accept_delivery_contract(context, task).contact is ContactIntent.UNSPECIFIED


def test_partial_browser_pass_never_supports_actual_message_receipt(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context.changes.record(tmp_path / "site.html")
    outcome = loop.AgentOutcome("Mesajınız başarıyla alındı. Tarayıcıda test edildi.", [])
    loop._apply_turn_report(outcome, deps, gate=partial_report().gate)
    assert outcome.completion_report is not None
    assert outcome.completion_report.false_claim
    assert not outcome.ok


@pytest.mark.parametrize(
    "text",
    [
        "Site lint temiz ve test edildi.",
        "Site: tüm testler geçti ve test edildi.",
    ],
)
def test_browser_scope_does_not_swallow_other_claims_in_same_sentence(text):
    assert partial_report().unsupported_command_claim(text)


@pytest.mark.parametrize(
    "task",
    [
        "Contact form is demo only; do not send messages. Actually send a real message.",
        "Contact form is demo only; do not send messages. Send actual messages.",
    ],
)
def test_mixed_transport_in_either_word_order_is_not_accepted_demo(tmp_path, task):
    from fusion_cli.core.delivery_contract import ContactIntent
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    context = _deps(tmp_path, RecordingSink()).tool_context
    assert accept_delivery_contract(context, task).contact is ContactIntent.UNSPECIFIED


def test_verified_demo_does_not_present_false_actual_receipt_as_verified(tmp_path):
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context.changes.record(tmp_path / "site.html")
    report = partial_report()
    items = tuple(replace(item, status=EvidenceStatus.PASSED) for item in report.criteria)
    outcome = loop.AgentOutcome("Mesajınız başarıyla alındı.", [])
    loop._apply_turn_report(outcome, deps, gate=replace(report.gate, evidence=items))
    assert outcome.completion_report is not None
    assert outcome.completion_report.false_claim
    assert not outcome.ok
    assert "Ajanın açıklaması (doğrulanmamış)" in outcome.final_text
    assert "Mesaj teslimatı doğrulanmadı" in outcome.final_text


@pytest.mark.parametrize("text", ["All tests passed.", "Lint temiz; tarayıcıda test edildi."])
def test_fully_passed_browser_demo_still_cannot_prove_command_scope(tmp_path, text):
    deps = _deps(tmp_path, RecordingSink())
    deps.tool_context.changes.record(tmp_path / "site.html")
    items = tuple(replace(item, status=EvidenceStatus.PASSED) for item in partial_report().criteria)
    outcome = loop.AgentOutcome(text, [])
    loop._apply_turn_report(outcome, deps, gate=VerificationResult(ok=True, evidence=items))
    assert outcome.completion_report is not None
    assert outcome.completion_report.false_claim
    assert not outcome.ok


@pytest.mark.asyncio
async def test_self_review_repair_also_preserves_document_delivery_intent(tmp_path):
    from unittest.mock import AsyncMock

    deps = _deps(tmp_path, RecordingSink())
    original = loop.AgentOutcome("Rapor hazır.", [])
    corrected = loop.AgentOutcome("CSS taşması düzeltildi.", [])
    with (
        patch.object(review, "review_turn", AsyncMock(return_value="Taşmayı düzelt")),
        patch.object(loop, "run_agent", AsyncMock(return_value=corrected)),
    ):
        result = await loop._self_review("Kısa rapor hazırla", original, deps)
    assert result.verification_repaired


def test_failed_repair_does_not_deliver_report_as_ready(tmp_path):
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    deps = _deps(tmp_path, RecordingSink())
    task = "Kısa raporu rapor-son.html dosyasına kaydet."
    accept_delivery_contract(deps.tool_context, task)
    deps.tool_context.changes.record(tmp_path / "rapor-son.html")
    (tmp_path / "rapor-son.html").write_text("<h1>Rapor</h1>")
    gate = VerificationResult(ok=True, evidence=partial_report().criteria[:2])
    outcome = loop.AgentOutcome("Düzeltme tamamlanamadı.", [], ok=False, verification_repaired=True)
    loop._apply_turn_report(outcome, deps, gate=gate, task=task)
    assert "Rapor hazır" not in outcome.final_text
    assert "doğrulanamadı" in outcome.final_text


def test_turkish_no_send_clause_cannot_erase_prior_positive_delivery_request(tmp_path):
    from fusion_cli.core.delivery_contract import ContactIntent
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    context = _deps(tmp_path, RecordingSink()).tool_context
    task = "İletişim alanı demo olsun; gerçek mesaj gönder ve test mesajı gönderme."
    assert accept_delivery_contract(context, task).contact is ContactIntent.UNSPECIFIED


@pytest.mark.parametrize(
    "task",
    [
        "Contact form is demo only; do not send messages. Messages must be sent to the owner.",
        "İletişim alanı demo olsun; mesaj gönderme. Mesajları gerçekten gönderin.",
        "İletişim alanı demo olsun; mesaj gönderme. Gerçek mesajı alıcıya iletin.",
    ],
)
def test_passive_or_polite_actual_delivery_is_not_an_accepted_demo(tmp_path, task):
    from fusion_cli.core.delivery_contract import ContactIntent
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    context = _deps(tmp_path, RecordingSink()).tool_context
    assert accept_delivery_contract(context, task).contact is ContactIntent.UNSPECIFIED


def test_report_repair_preserves_unsupported_original_claim_failure(tmp_path):
    from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract

    deps = _deps(tmp_path, RecordingSink())
    task = "Kısa raporu rapor-son.html dosyasına kaydet."
    accept_delivery_contract(deps.tool_context, task)
    deps.tool_context.changes.record(tmp_path / "rapor-son.html")
    (tmp_path / "rapor-son.html").write_text("<h1>Rapor</h1>")
    gate = VerificationResult(ok=True, evidence=partial_report().criteria[:2])
    outcome = loop.AgentOutcome("All tests passed.", [], verification_repaired=True)
    loop._apply_turn_report(outcome, deps, gate=gate, task=task)
    assert outcome.completion_report is not None
    assert outcome.completion_report.false_claim
    assert not outcome.ok
    assert "Rapor hazır" not in outcome.final_text
