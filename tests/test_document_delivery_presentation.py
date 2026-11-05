"""Desktop report presentation retains proof without changing engine outcomes."""

import json
from dataclasses import replace

import pytest

from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.turn_report import TurnReport

TASK = "Python’ın güncel sürümünü açıklayan kısa Türkçe HTML raporunu rapor.html olarak hazırla."


def report_outcome():
    evidence = CriterionEvidence(
        "browser",
        VerificationCheckKind.TOOL,
        EvidenceStatus.PASSED,
        "rapor.html açıldı",
        artifact="rapor.html",
    )
    report = TurnReport(
        changed_paths=("rapor.html",),
        gate=VerificationResult(
            True, advisories=("Bir main landmark önerilir.",), evidence=(evidence,)
        ),
        change_lines=("rapor.html (yeni dosya, 67 satır)",),
    )
    text = "Rapor hazır: `rapor.html`."
    return AgentOutcome(report.render_with_model_text(text), [], completion_report=report), text


def test_safe_report_separates_exact_prefix_and_keeps_engine_unchanged():
    from fusion_cli.appserver.delivery_presentation import present_delivery

    outcome, text = report_outcome()
    original = outcome.final_text
    result = present_delivery(TASK, outcome)
    assert result.compact and result.text == text
    assert outcome.final_text == original
    assert result.evidence["sunum"] == "document"
    assert result.evidence["oneriler"] == ["Bir main landmark önerilir."]
    assert result.evidence["kontroller"] == ["rapor.html açıldı"]
    assert result.evidence["degisiklik_ozeti"] == ["rapor.html (yeni dosya, 67 satır)"]


@pytest.mark.parametrize(
    "change", ["failed", "budget", "warning", "unverified", "false", "two", "unknownprefix"]
)
def test_unsafe_or_unknown_report_never_loses_text(change):
    from fusion_cli.appserver.delivery_presentation import present_delivery

    outcome, _ = report_outcome()
    report = outcome.completion_report
    if change == "failed":
        outcome.ok = False
    elif change == "budget":
        outcome.budget_stopped = True
    elif change == "warning":
        report = replace(report, gate=replace(report.gate, warnings=("Ölçülemedi",)))
    elif change == "unverified":
        report = replace(report, gate=None)
    elif change == "false":
        report = replace(report, false_claim=True)
    elif change == "two":
        report = replace(report, changed_paths=("rapor.html", "extra.html"))
    else:
        outcome.final_text = "model heading\n" + outcome.final_text
    outcome.completion_report = report
    result = present_delivery(TASK, outcome)
    assert not result.compact and result.text == outcome.final_text


@pytest.mark.parametrize(
    "suffix", [" Yanıtı yalnız JSON ver.", " Diff ve doğrulama kanıtlarını göster."]
)
def test_explicit_reply_contract_keeps_original(suffix):
    from fusion_cli.appserver.delivery_presentation import present_delivery

    outcome, _ = report_outcome()
    assert not present_delivery(TASK + suffix, outcome).compact


def test_projection_redacts_bounds_and_fails_closed():
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.turn_report import evidence_payload

    outcome, _ = report_outcome()
    data = evidence_payload(outcome.completion_report)
    data.update(
        oneriler=["ü" * 5000] * 100,
        degisiklik_ozeti=["x" * 1000] * 100,
        unknown={"secret": "keep out"},
    )
    result = public_delivery_evidence(data)
    assert "unknown" not in result
    assert result["ayrintilar_kisaltildi"] is True
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 32768
    bad = public_delivery_evidence({**data, "engelliyor": "false"})
    assert bad["engelliyor"] is True and bad["dogrulandi"] is None
    secret = "sk-or-v1-" + "x" * 48
    hidden = public_delivery_evidence({**data, "uyarilar": [secret]})
    assert secret not in json.dumps(hidden)


@pytest.mark.parametrize(
    "field,value",
    [
        ("teslim_turu", []),
        ("criteria", [{"status": []}]),
        ("schema_version", True),
        ("degisen_sayisi", True),
        ("criteria", [{"status": "failed", "applicable": True}]),
        ("criteria_status_counts", {"passed": 0, "failed": 1, "unverified": 0}),
    ],
)
def test_malformed_critical_metadata_cannot_make_document_success(field, value):
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.turn_report import evidence_payload

    outcome, _ = report_outcome()
    data = {**evidence_payload(outcome.completion_report), "sunum": "document", field: value}
    result = public_delivery_evidence(data)
    assert result.get("sunum") is None
    if field != "teslim_turu":
        assert result["engelliyor"] is True


def test_deleted_conversation_cannot_be_resurrected_by_presented_completion(tmp_path):
    from fusion_cli.appserver.delivery_presentation import present_delivery
    from fusion_cli.appserver.visible_transcript import load_visible_transcript
    from fusion_cli.cli.repl.transcript_store import TranscriptStore, delete_conversation

    store = TranscriptStore(tmp_path / "mem", tmp_path, conversation_id="deleted")
    outcome, text = report_outcome()
    delete_conversation(tmp_path / "mem", tmp_path, "deleted")
    assert not store.record_presented_assistant(
        text, evidence=present_delivery(TASK, outcome).evidence
    )
    assert load_visible_transcript(store, []).rows == []


def test_wrong_changed_target_and_surrogate_metadata_fail_closed():
    from fusion_cli.appserver.delivery_presentation import (
        present_delivery,
        public_delivery_evidence,
    )

    outcome, _ = report_outcome()
    outcome.completion_report = replace(outcome.completion_report, changed_paths=("other.html",))
    outcome.final_text = outcome.completion_report.render_with_model_text("Rapor hazır.")
    assert not present_delivery(TASK, outcome).compact
    payload = {
        "schema_version": 1,
        "dogrulandi": True,
        "engelliyor": False,
        "yanlis_iddia": False,
        "degisen": ["x\ud800.html"],
        "degisen_sayisi": 1,
        "sorunlar": [],
        "sorun_sayisi": 0,
    }
    assert public_delivery_evidence(payload)["engelliyor"] is True


def test_failure_after_criterion_cap_is_not_trimmed_into_success():
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.turn_report import evidence_payload

    outcome, _ = report_outcome()
    payload = evidence_payload(outcome.completion_report)
    payload["criteria"] = [{"status": "passed"}] * 50 + [{"status": "failed"}]
    assert public_delivery_evidence(payload)["engelliyor"] is True


def test_openable_paths_are_whole_or_omitted_never_rewritten():
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.turn_report import evidence_payload

    outcome, _ = report_outcome()
    payload = evidence_payload(outcome.completion_report)
    long_path = "nested/" * 100 + "report.html"
    result = public_delivery_evidence({**payload, "degisen": [long_path]})
    assert result["degisen"] == [long_path]
    huge = "nested/" * 6000 + "report.html"
    result = public_delivery_evidence({**payload, "degisen": [huge], "sunum": "document"})
    assert result["degisen"] == [] and result["degisen_sayisi"] == 1
    assert result["degisen_kisaltildi"] is True and result.get("sunum") is None


def test_presented_transcript_replays_proof_but_model_reads_only_text(tmp_path):
    from fusion_cli.appserver.delivery_presentation import present_delivery
    from fusion_cli.appserver.visible_transcript import load_visible_transcript
    from fusion_cli.cli.repl.transcript_store import TranscriptStore, load_transcript_messages

    store = TranscriptStore(tmp_path / "mem", tmp_path, conversation_id="report")
    outcome, text = report_outcome()
    presentation = present_delivery(TASK, outcome)
    store.record_user(TASK)
    assert store.record_presented_assistant(
        text, evidence=presentation.evidence, message_id="job:assistant"
    )
    rows = load_visible_transcript(store, []).rows
    assert rows[-1]["metin"] == text and rows[-1]["kanit"]["sunum"] == "document"
    messages = load_transcript_messages(tmp_path / "mem", tmp_path, conversation_id="report")
    assert messages[-1].content == text and "oneriler" not in messages[-1].content


async def test_actual_session_returns_and_reloads_one_clean_delivery(tmp_path, monkeypatch):
    from fusion_cli.appserver.protocol import Request
    from tests.test_appserver_session import _session

    outcome, text = report_outcome()

    async def run(*args, **kwargs):
        return outcome

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "delivery"}))
    result = await session._dispatch(
        Request("r", "tur.calistir", {"gorev": TASK, "gonderim_id": "job"})
    )
    assert result["metin"] == text and result["kanit"]["sunum"] == "document"
    await session.close()
    reopened = _session(tmp_path, [])
    await reopened._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "delivery"}))
    rows = (await reopened._dispatch(Request("h", "oturum.gecmis", {})))["mesajlar"]
    answers = [row for row in rows if row["rol"] == "asistan"]
    assert len(answers) == 1 and answers[0]["metin"] == text
    assert answers[0]["kanit"] == result["kanit"]
    await reopened.close()


@pytest.mark.parametrize("warning", [False, True])
async def test_failed_durable_write_keeps_full_text(tmp_path, monkeypatch, warning):
    from fusion_cli.appserver.protocol import Request
    from tests.test_appserver_session import _session

    outcome, _ = report_outcome()
    if warning:
        outcome.completion_report = replace(
            outcome.completion_report,
            gate=replace(outcome.completion_report.gate, warnings=("Kalite uyarısı",)),
        )
        outcome.final_text = outcome.completion_report.render_with_model_text("Rapor hazır.")

    async def run(*args, **kwargs):
        return outcome

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    session = _session(tmp_path, [])
    monkeypatch.setattr(
        session._transcript_store, "record_presented_assistant", lambda *args, **kwargs: False
    )
    stored = []
    original = session._transcript_store.record_assistant

    def record(text, **kwargs):
        stored.append(text)
        return original(text, **kwargs)

    monkeypatch.setattr(session._transcript_store, "record_assistant", record)
    result = await session._dispatch(
        Request("r", "tur.calistir", {"gorev": TASK, "gonderim_id": "job"})
    )
    assert result["metin"] == outcome.final_text
    assert result["kanit"].get("sunum") is None
    assert stored == [outcome.final_text]
    await session.close()


@pytest.mark.parametrize("pause", ["lookup", "claim", "running", "execute"])
@pytest.mark.parametrize("switch", ["conversation", "roundtrip", "root"])
async def test_completion_proof_stays_with_accepted_owner(tmp_path, monkeypatch, pause, switch):
    import asyncio

    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.visible_transcript import load_visible_transcript
    from tests.test_appserver_session import _session

    outcome, _ = report_outcome()
    entered, release = asyncio.Event(), asyncio.Event()

    async def run(*args, **kwargs):
        if pause == "execute":
            entered.set()
            await release.wait()
        return outcome

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    accepted = session._transcript_store
    if pause != "execute":
        name = "finish" if pause == "running" else pause
        original = getattr(session._submission_store, name)

        async def paused(*args, **kwargs):
            if pause != "running" or kwargs.get("state") == "running":
                entered.set()
                await release.wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(session._submission_store, name, paused)
    pending = asyncio.create_task(
        session._dispatch(Request("r", "tur.calistir", {"gorev": TASK, "gonderim_id": "job"}))
    )
    await asyncio.wait_for(entered.wait(), 3)
    new_root = tmp_path / "other"
    new_root.mkdir()
    data = {"sohbet_id": "other", **({"kok": str(new_root)} if switch == "root" else {})}
    switched = await session._dispatch(Request("switch", "oturum.baslat", data))
    if switch == "root" and pause == "execute":
        assert switched["ok"] is False  # Existing active-turn root guard.
    else:
        assert switched["ok"] is True
    other = session._transcript_store
    if switch == "roundtrip":
        await session._dispatch(Request("back", "oturum.baslat", {"sohbet_id": "accepted"}))
    release.set()
    result = await asyncio.wait_for(pending, 5)
    answers = [row for row in load_visible_transcript(accepted, []).rows if "kanit" in row]
    assert len(answers) == 1 and "kanit" in answers[0]
    if switched["ok"] is True:
        assert not any("kanit" in row for row in load_visible_transcript(other, []).rows)
    assert result["metin"] == answers[0]["metin"]
    await session.close()


@pytest.mark.parametrize("critical", ["problems", "failed", "unverified"])
def test_critical_totals_survive_missing_detail_lists(critical):
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {**evidence_payload(outcome.completion_report), "sunum": "document"}
    if critical == "problems":
        value.update(sorun_sayisi=3, sorunlar=[])
    else:
        value.pop("criteria", None)
        value["criteria_status_counts"] = {"passed": 0, "failed": 0, "unverified": 0}
        value["criteria_status_counts"][critical] = 1
        value["criteria_count"] = 1
    projected = public_delivery_evidence(value)
    assert projected.get("sunum") is None and projected["dogrulandi"] is not True
    if critical == "problems":
        assert projected["sorun_sayisi"] == 3
    else:
        assert projected["criteria_status_counts"][critical] == 1


def test_url_query_or_quoted_example_cannot_supply_output_identity():
    from fusion_cli.appserver.delivery_presentation import present_delivery

    outcome, _ = report_outcome()
    task = (
        "Read 'https://example.org/?file=rapor.html' and write a brief HTML report as other.html."
    )
    assert not present_delivery(task, outcome).compact
    assert not present_delivery(
        'Write a brief HTML report as Other.HTML. Example: "rapor.html is a sample".', outcome
    ).compact


@pytest.mark.parametrize(
    "instruction",
    [
        " Show the source code in your reply.",
        " Cevabında HTML kodunu göster.",
        " Include the code changes in your answer.",
    ],
)
def test_explicit_code_output_keeps_full_presentation(instruction):
    from fusion_cli.appserver.delivery_presentation import present_delivery

    outcome, _ = report_outcome()
    assert not present_delivery(TASK + instruction, outcome).compact


def test_criteria_total_without_status_details_is_unknown():
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence

    outcome, _ = report_outcome()
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    value = {**evidence_payload(outcome.completion_report), "sunum": "document"}
    value.pop("criteria", None)
    value.pop("criteria_status_counts", None)
    value["criteria_count"] = 3
    projected = public_delivery_evidence(value)
    assert projected["criteria_count"] == 3
    assert projected["dogrulandi"] is None and projected.get("sunum") is None


@pytest.mark.parametrize(
    "field", ["uyarilar", "olculmeyen", "kontroller", "oneriler", "degisiklik_ozeti"]
)
def test_explicit_null_detail_list_cannot_become_healthy_document(field):
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {**evidence_payload(outcome.completion_report), "sunum": "document", field: None}
    projected = public_delivery_evidence(value)
    assert projected["engelliyor"] is True
    assert projected["dogrulandi"] is not True and projected.get("sunum") is None


@pytest.mark.parametrize(
    "field",
    [
        "uyarilar",
        "olculmeyen",
        "criteria",
        "criteria_status_counts",
        "supheli_test_degisikligi",
        "ayrintilar_kisaltildi",
    ],
)
def test_durable_replay_rejects_explicit_null_warning_lists(tmp_path, field):
    from fusion_cli.appserver.visible_transcript import load_visible_transcript
    from fusion_cli.cli.repl.transcript_store import TranscriptStore
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {**evidence_payload(outcome.completion_report), "sunum": "document", field: None}
    store = TranscriptStore(tmp_path / "mem", tmp_path, conversation_id="null-proof")
    assert store.record_presented_assistant("Original answer", evidence=value)
    proof = load_visible_transcript(store, []).rows[-1]["kanit"]
    assert proof["engelliyor"] is True and proof["dogrulandi"] is not True
    assert proof.get("sunum") is None


@pytest.mark.parametrize(
    "field",
    [
        "ayrintilar_kisaltildi",
        "criteria",
        "criteria_status_counts",
        "supheli_test_degisikligi",
        "teslim_turu",
        "degisen_kisaltildi",
        "sorunlar_kisaltildi",
        "criteria_truncated",
        "degisen_sayisi",
        "sorun_sayisi",
        "criteria_count",
        "degisen",
        "sorunlar",
    ],
)
def test_known_typed_metadata_distinguishes_null_from_absence(field):
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    base = {**evidence_payload(outcome.completion_report), "sunum": "document"}
    projected = public_delivery_evidence({**base, field: None})
    assert projected["engelliyor"] is True and projected["dogrulandi"] is not True
    assert projected.get("sunum") is None


@pytest.mark.parametrize(
    "tamper",
    [
        {"adet": 2**53, "zayiflatan": 0},
        {"adet": 1, "zayiflatan": 2},
        {"adet": True, "zayiflatan": 0},
    ],
)
def test_tamper_counts_are_safe_and_consistent_even_when_unverified(tamper):
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {
        **evidence_payload(outcome.completion_report),
        "dogrulandi": None,
        "supheli_test_degisikligi": tamper,
        "sunum": "document",
    }
    projected = public_delivery_evidence(value)
    assert projected["engelliyor"] is True and projected.get("sunum") is None


def test_positive_nonweakening_tamper_downgrades_verified_to_unknown():
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {
        **evidence_payload(outcome.completion_report),
        "sunum": "document",
        "supheli_test_degisikligi": {"adet": 1, "zayiflatan": 0},
    }
    projected = public_delivery_evidence(value)
    assert projected["dogrulandi"] is None and projected.get("sunum") is None
    assert projected["supheli_test_degisikligi"]["adet"] == 1


@pytest.mark.parametrize("case", ["statuses_exceed_total", "retained_exceed_total", "unsafe_sum"])
def test_criterion_totals_cannot_contradict_retained_or_known_status_counts(case):
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {**evidence_payload(outcome.completion_report), "sunum": "document"}
    if case == "statuses_exceed_total":
        value.update(
            criteria_count=1, criteria_status_counts={"passed": 2, "failed": 0, "unverified": 0}
        )
    elif case == "retained_exceed_total":
        value.update(criteria_count=1, criteria=[{"status": "passed"}] * 2)
    else:
        value.pop("criteria_count")
        value["criteria_status_counts"] = {"passed": 2**53 - 1, "failed": 0, "unverified": 1}
    projected = public_delivery_evidence(value)
    assert projected["engelliyor"] is True and projected.get("sunum") is None


@pytest.mark.parametrize("field", ["dogrulandi", "degisen", "sorunlar"])
def test_missing_required_evidence_fields_fail_closed(field):
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {**evidence_payload(outcome.completion_report), "sunum": "document"}
    value.pop(field)
    projected = public_delivery_evidence(value)
    assert projected["engelliyor"] is True and projected.get("sunum") is None


@pytest.mark.parametrize(
    "field",
    [
        "criteria",
        "criteria_status_counts",
        "supheli_test_degisikligi",
        "ayrintilar_kisaltildi",
        "teslim_turu",
    ],
)
def test_absent_optional_typed_metadata_keeps_legacy_document(field):
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {**evidence_payload(outcome.completion_report), "sunum": "document"}
    value.pop(field, None)
    projected = public_delivery_evidence(value)
    assert projected["dogrulandi"] is True and projected["sunum"] == "document"


def test_valid_zero_tamper_and_false_truncation_keep_typed_semantics():
    from fusion_cli.appserver.delivery_presentation import public_delivery_evidence
    from fusion_cli.engines.agent.completion_evidence import evidence_payload

    outcome, _ = report_outcome()
    value = {
        **evidence_payload(outcome.completion_report),
        "sunum": "document",
        "ayrintilar_kisaltildi": False,
        "supheli_test_degisikligi": {"adet": 0, "zayiflatan": 0},
    }
    projected = public_delivery_evidence(value)
    assert projected["dogrulandi"] is True and projected.get("sunum") is None
    assert projected["ayrintilar_kisaltildi"] is False
