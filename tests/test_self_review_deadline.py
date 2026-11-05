"""An optional reviewer must leave time to deliver already measured work."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.core.events import SelfReviewFinished, TurnAnswered
from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.core.turn_deadline import TurnDeadline
from fusion_cli.core.types import StreamDone
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop, review

from .fakes import ScriptedProvider, model_result, tool_call
from .test_agent_external_deadline import deps_for
from .test_turn_deadline import FakeClock


async def test_finished_measured_task_survives_near_deadline_optional_review(tmp_path, monkeypatch):
    clock = FakeClock()
    deps = deps_for(tmp_path, TurnDeadline.from_duration(30, clock))

    class BufferedProvider(ScriptedProvider):
        async def stream(self, request):
            yield StreamDone(self._next(request))

    provider = BufferedProvider(
        [
            model_result(tool_calls=[tool_call("write_file", path="notes.txt", content="hazır")]),
            model_result("notes.txt hazır."),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: provider)

    async def no_intro(*args, **kwargs):
        return ""

    monkeypatch.setattr(loop, "intro_paragraph", no_intro)
    outer = asyncio.timeout(None)

    class Measured:
        async def verify(self):
            assert (tmp_path / "notes.txt").read_text() == "hazır"
            clock.value = 29.8
            outer.reschedule(asyncio.get_running_loop().time() + 0.3)
            return VerificationResult(
                ok=True,
                evidence=(
                    CriterionEvidence(
                        "content",
                        VerificationCheckKind.FILE_CONTAINS,
                        EvidenceStatus.PASSED,
                        "notes.txt içeriği okundu: hazır",
                        artifact="notes.txt",
                    ),
                ),
            )

    deps.verifier = Measured()
    review_calls = []

    async def stalled(*args, **kwargs):
        review_calls.append(True)
        await asyncio.sleep(60)

    monkeypatch.setattr(review, "_ask", stalled)
    async with outer:
        outcome = await loop.run_agent("notes.txt dosyasına hazır yaz.", deps, self_review=True)
    assert outcome.ok and not outcome.budget_stopped
    assert outcome.completion_report is not None
    assert outcome.completion_report.is_verified is True
    assert "notes.txt" in outcome.final_text
    assert (tmp_path / "notes.txt").read_text() == "hazır"
    assert not review_calls
    events = deps.publisher.sink.events
    assert any(isinstance(e, TurnAnswered) for e in events)
    assert any(isinstance(e, SelfReviewFinished) and not e.completed for e in events)


@pytest.mark.parametrize(
    "limit", ["external", "shared_budget", "tighter_external", "tighter_budget"]
)
async def test_review_feedback_is_bounded_by_remaining_hard_time(tmp_path, monkeypatch, limit):
    clock = FakeClock()
    deadline = TurnDeadline.from_duration(1.05, clock)
    deps = deps_for(tmp_path, deadline if limit in {"external", "tighter_external"} else None)
    if limit == "tighter_budget":
        deps.deadline = TurnDeadline.from_duration(10, clock)
    if limit in {"shared_budget", "tighter_external", "tighter_budget"}:
        budget_deadline = (
            TurnDeadline.from_duration(10, clock) if limit == "tighter_external" else deadline
        )
        deps.budget = loop._new_budget(deps.config, budget_deadline)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def stalled(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()

    monkeypatch.setattr(review, "_ask", stalled)
    outcome = loop.AgentOutcome("Hazır dosya", [])
    async with asyncio.timeout(0.3):
        result = await loop._self_review("Dosyayı hazırla", outcome, deps)
    assert result is outcome and result.ok
    assert started.is_set() and cancelled.is_set()
    finished = [e for e in deps.publisher.sink.events if isinstance(e, SelfReviewFinished)]
    assert len(finished) == 1 and not finished[0].completed


async def test_optional_review_timeout_preserves_existing_failure(tmp_path, monkeypatch):
    deps = deps_for(tmp_path, TurnDeadline.from_duration(0.1, FakeClock()))
    calls = []

    async def must_not_start(*args, **kwargs):
        calls.append(True)
        raise AssertionError("No reviewer time remains")

    monkeypatch.setattr(review, "_ask", must_not_start)
    outcome = loop.AgentOutcome("İçerik ölçümü başarısız.", [], ok=False)
    result = await loop._self_review("Dosyayı hazırla", outcome, deps)
    assert result is outcome and not result.ok
    assert result.final_text == "İçerik ölçümü başarısız."
    assert not calls
    assert any(
        isinstance(e, SelfReviewFinished) and not e.completed for e in deps.publisher.sink.events
    )


async def test_external_cancellation_during_optional_review_propagates(tmp_path, monkeypatch):
    deps = deps_for(tmp_path, TurnDeadline.from_duration(10, FakeClock()))
    started = asyncio.Event()

    async def stalled(*args, **kwargs):
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(review, "_ask", stalled)
    task = asyncio.create_task(loop._self_review("İş", loop.AgentOutcome("Yanıt", []), deps))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not any(isinstance(e, SelfReviewFinished) for e in deps.publisher.sink.events)


async def test_no_hard_deadline_retains_completed_review(tmp_path, monkeypatch):
    deps = deps_for(tmp_path, None)

    async def clean(*args, **kwargs):
        return model_result("TAMAM")

    monkeypatch.setattr(review, "_ask", clean)
    outcome = loop.AgentOutcome("Hazır", [])
    result = await loop._self_review("İş", outcome, deps)
    assert result is outcome
    finished = [e for e in deps.publisher.sink.events if isinstance(e, SelfReviewFinished)]
    assert len(finished) == 1 and finished[0].completed and not finished[0].issue_found
