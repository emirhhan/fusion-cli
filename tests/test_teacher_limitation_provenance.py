"""Teacher assessments retain their unverified provenance in visible output."""

from types import SimpleNamespace

import pytest

from fusion_cli.core.events import TeacherLimitationFound, TurnFinished
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.platform_check import ensure_limitations_disclosed
from fusion_cli.engines.agent.teacher_plan import UnworkablePart
from tests.test_renderer import _renderer


@pytest.mark.parametrize(
    "topic, reason",
    [
        ("Testleri değiştirme", "Kullanıcı testlerin korunmasını istiyor"),
        ("Harici bağımlılık kullanma", "Kullanıcı kapsamı"),
        ("Story çıkartması", "API desteklemiyor"),
    ],
)
@pytest.mark.parametrize("already_mentioned", [False, True])
def test_raw_teacher_assessment_is_not_automatically_appended_to_final_answer(
    topic, reason, already_mentioned
):
    part = UnworkablePart(topic, reason, "Mevcut kapsamda ilerle")
    deps = SimpleNamespace(
        platform_limitations=[part], platform_names=(), platform_check_verified=False
    )
    text = topic + " korundu." if already_mentioned else "İş tamamlandı."
    outcome = AgentOutcome(text, [])
    ensure_limitations_disclosed(outcome, deps)
    assert outcome.final_text == text
    assert deps.platform_limitations == [part]
    ensure_limitations_disclosed(outcome, deps)
    assert outcome.final_text == text


def test_actual_blocked_failure_and_unverified_platform_warning_are_preserved():
    deps = SimpleNamespace(
        platform_limitations=[UnworkablePart("Öğretmen notu", "Görüş", "Öneri")],
        platform_names=("Instagram",),
        platform_check_verified=False,
    )
    outcome = AgentOutcome("Araç erişimi reddetti; işlem tamamlanmadı.", [], ok=False)
    ensure_limitations_disclosed(outcome, deps)
    assert not outcome.ok
    assert outcome.final_text.startswith("Araç erişimi reddetti; işlem tamamlanmadı.")
    assert "Instagram kısıtları resmi kaynaktan doğrulanamadı." in outcome.final_text
    assert "Öğretmen notu" not in outcome.final_text


def test_teacher_limitation_event_is_qualified_in_actual_console_output():
    renderer, buffer = _renderer()
    renderer.handle(
        TeacherLimitationFound("Harici bağımlılık", "Kullanıcı istemedi", "Yerel çözüm")
    )
    renderer.handle(TurnFinished())
    assert "doğrulanmadı" in buffer.getvalue()
    assert "yapılamıyor:" not in buffer.getvalue()


async def test_plan_retains_raw_advisory_internally_with_qualified_activity(tmp_path, monkeypatch):
    import json

    from fusion_cli.core.events import StatusChanged
    from fusion_cli.engines.agent import teacher_flow
    from fusion_cli.tools.builtin import build_registry
    from tests.test_teacher_first import _setup

    deps, sink, _teacher, _apprentice = _setup(monkeypatch, tmp_path)
    response = json.dumps(
        {
            "adimlar": ["Kod hatasını düzelt"],
            "yapilamayanlar": [
                {
                    "konu": "Harici bağımlılık kullanma",
                    "gerekce": "Kullanıcı kapsamı",
                    "alternatif": "Yerel çözüm",
                }
            ],
        }
    )

    async def answer(*args, **kwargs):
        return response

    monkeypatch.setattr(teacher_flow, "_ask", answer)
    monkeypatch.setattr(teacher_flow, "teacher_is_ready", lambda *_args: True)
    messages = []
    await teacher_flow.prepare_teacher_plan(
        "src/app.py içindeki hatayı düzelt", messages, deps, build_registry()
    )
    assert deps.platform_limitations[0].topic == "Harici bağımlılık kullanma"
    assert deps.pending_teacher_plan.unworkables[0] == deps.platform_limitations[0]
    assert any("GÖRÜŞÜDÜR, doğrulanmadı" in message.content for message in messages)
    statuses = [event.message for event in sink.events if isinstance(event, StatusChanged)]
    assert any("doğrulanmadı" in text and "Harici bağımlılık kullanma" in text for text in statuses)
