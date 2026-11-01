"""Ders geri çağırmasının kanıt olmadan güven üretmemesi."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.memory import Lesson, LessonKind
from fusion_cli.engines.agent import learning_steps
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.memory.lesson_scoring import reinforced
from fusion_cli.memory.null import NullLessonMemory
from tests.test_agent_lessons import _deps


class Memory(NullLessonMemory):
    def __init__(self):
        self.lesson = Lesson("Dosyayı önce oku", LessonKind.SUCCESS, id="ders1", confidence=0.5)
        self.feedback = []

    def recall(self, task, limit=4, **kwargs):
        return (self.lesson,)

    def reinforce(self, texts, **kwargs):
        self.feedback.append(kwargs)
        self.lesson = reinforced(
            self.lesson, **{k: v for k, v in kwargs.items() if k != "lesson_ids"}
        )
        return 0


@pytest.mark.parametrize("ok", [True, False])
async def test_iliski_kanitlanmayan_recall_guveni_degistirmez(tmp_path, ok):
    deps = _deps(tmp_path)
    assert hasattr(deps.config.runtime, "lesson_attributed_feedback")
    deps.config = replace(
        deps.config,
        runtime=replace(deps.config.runtime, lesson_attributed_feedback=True, lessons=True),
    )
    deps.lessons = Memory()
    learning_steps.recall_lessons("dosya", deps)
    await learning_steps.reinforce_recalled(
        AgentOutcome("dersi kullandım", [], ok=ok), deps, plan_mode=False
    )
    assert deps.lessons.lesson.confidence == 0.5
    assert deps.lessons.feedback[0]["feedback_reason"] == "usage_unknown"
    assert deps.lessons.feedback[0]["lesson_ids"] == ("ders1",)


@pytest.mark.parametrize("failure", ["", "quota", "altyapı"])
async def test_gercek_tur_recall_offered_unknown_ve_temizlik(tmp_path, monkeypatch, failure):
    from fusion_cli.core.events import LessonOffered, LessonOutcome, LessonsRecalled
    from fusion_cli.engines.agent import loop
    from tests.fakes import ScriptedProvider, model_result, tool_call
    from tests.test_ask_teacher import _Publisher

    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime, lessons=True, lesson_attributed_feedback=True, self_review=False
        ),
    )
    deps.lessons = Memory()
    deps.publisher = _Publisher()
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("recall_lessons", query="dosya"),)),
            model_result(
                "Dersi kullandım; ilgili görev tamamlandı.", ok=not failure, error=failure or None
            ),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    await loop.run_agent("Dosya okuma kuralını açıkla", deps, verify=False, self_review=False)
    events = deps.publisher.events
    assert any(
        isinstance(event, LessonsRecalled) and event.lesson_ids == ("ders1",) for event in events
    )
    assert any(isinstance(event, LessonOffered) and event.lesson_id == "ders1" for event in events)
    outcomes = [event for event in events if isinstance(event, LessonOutcome)]
    assert len(outcomes) == 1 and outcomes[0].used is None
    assert deps.lessons.lesson.confidence == 0.5
    assert deps.lesson_state is None and not deps.recalled_lessons


async def test_gercek_ipucu_istemi_en_fazla_iki_ders(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import loop
    from tests.fakes import ScriptedProvider, model_result

    class ManyMemory(Memory):
        def recall(self, task, limit=4, **kwargs):
            return tuple(
                replace(self.lesson, id=f"ders-{i}", text=f"ÖZGÜN_DERS_{i}") for i in range(5)
            )

    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime,
            lessons=True,
            lesson_recall_hints=True,
            lesson_attributed_feedback=True,
            self_review=False,
        ),
    )
    deps.lessons = ManyMemory()
    provider = ScriptedProvider([model_result("İstenen açıklama tamamlandı.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    await loop.run_agent("Bir okuma kuralını açıkla", deps, verify=False, self_review=False)
    prompt = "\n".join(message.content for message in provider.seen_messages[0])
    assert "ÖZGÜN_DERS_0" in prompt and "ÖZGÜN_DERS_1" in prompt
    assert "ÖZGÜN_DERS_2" not in prompt


@pytest.mark.parametrize("pair", range(20))
def test_gercek_recall_yirmi_surumu_ve_blind_sinirini_tuketir(tmp_path, pair):
    from fusion_cli.core.lesson_runtime import LessonRuntimeContext
    from fusion_cli.core.memory import LessonRecallPolicy
    from fusion_cli.memory.lessons import ChromaLessonMemory
    from tests.test_memory_store import _LocalEmbedding

    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(deps.config.runtime, lessons=True, lesson_conflict_quarantine=True),
    )
    deps.lessons = ChromaLessonMemory(tmp_path / "bellek", embedding_function=_LocalEmbedding())
    old = Lesson(
        f"python eski kural {pair}",
        LessonKind.SUCCESS,
        subject_key=f"api-{pair}",
        version="1",
        source_split="development",
    )
    deps.lessons.add(old)
    old = deps.lessons.all()[0]
    new = replace(
        old,
        id="",
        text=f"python güncel kural {pair}",
        version="2",
        supersedes=(old.id,),
        verified_at="1",
        evidence_refs=("kontrol",),
    )
    deps.lessons.add(new)
    deps.lesson_context = LessonRuntimeContext(
        LessonRecallPolicy(subject_key=f"api-{pair}", version="2", source_split="development")
    )
    recalled = learning_steps.recall_lessons("python kural", deps)
    assert len(recalled) == 1 and recalled[0].text == new.text
    deps.lessons.set_quarantined((recalled[0].id,), quarantined=True)
    assert learning_steps.recall_lessons("python kural", deps) == ()
    deps.lessons.set_quarantined((recalled[0].id,), quarantined=False)
    assert learning_steps.recall_lessons("python kural", deps)[0].id == recalled[0].id
    deps.lesson_context = LessonRuntimeContext(LessonRecallPolicy(source_split="blind"))
    assert learning_steps.recall_lessons("python kural", deps) == ()


async def test_gercek_tur_iptali_unknown_ile_kapanir_ve_iz_birakmaz(tmp_path, monkeypatch):
    import asyncio

    from fusion_cli.core.events import LessonOutcome
    from fusion_cli.engines.agent import loop
    from tests.fakes import ScriptedProvider, model_result, tool_call
    from tests.test_ask_teacher import _Publisher

    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime, lessons=True, lesson_attributed_feedback=True, self_review=False
        ),
    )
    deps.lessons = Memory()
    deps.publisher = _Publisher()
    provider = ScriptedProvider(
        [model_result(tool_calls=(tool_call("recall_lessons", query="dosya"),))]
    )
    next_result = provider._next

    def cancel_after_recall(request):
        if provider.calls:
            raise asyncio.CancelledError
        return next_result(request)

    monkeypatch.setattr(provider, "_next", cancel_after_recall)
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    with pytest.raises(asyncio.CancelledError):
        await loop.run_agent("Dosya okuma kuralını açıkla", deps, verify=False, self_review=False)
    outcomes = [event for event in deps.publisher.events if isinstance(event, LessonOutcome)]
    assert len(outcomes) == 1 and outcomes[0].used is None
    assert deps.lessons.lesson.confidence == 0.5
    assert deps.lesson_state is None and not deps.recalled_lessons and not deps.pending_advice
