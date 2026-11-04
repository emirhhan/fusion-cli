"""Regression checks for evidence, retrieval and irrelevant delivery summaries."""

from dataclasses import replace

import pytest

from fusion_cli.core.memory import Lesson, LessonKind
from fusion_cli.core.types import Message
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import learning, learning_steps
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.turn_report import CommandRun, TurnReport, evidence_payload
from tests.test_agent_lessons import _deps
from tests.test_lesson_runtime_attribution import Memory


@pytest.mark.parametrize("ok", [False, None])
def test_failed_or_unknown_tool_is_not_affirmative_evidence(ok):
    assert not learning.has_measurable_evidence([Message("tool", "claimed success", ok=ok)])


@pytest.mark.parametrize("attributed", [False, True])
async def test_retrieval_alone_never_changes_confidence(tmp_path, attributed):
    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(deps.config.runtime, lessons=True, lesson_attributed_feedback=attributed),
    )
    deps.lessons = Memory()
    learning_steps.recall_lessons("file", deps)
    await learning_steps.reinforce_recalled(AgentOutcome("ok", []), deps, plan_mode=False)
    assert deps.lessons.lesson.confidence == 0.5


@pytest.mark.parametrize("attributed", [False, True])
async def test_success_lesson_requires_relevant_verification(tmp_path, monkeypatch, attributed):
    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(deps.config.runtime, lessons=True, lesson_attributed_feedback=attributed),
    )
    stored = []

    class Store(Memory):
        def all(self):
            return ()

        def add(self, lesson):
            stored.append(lesson)
            return True

    deps.lessons = Store()

    async def extract(*args, **kwargs):
        return (Lesson("A verified procedure", LessonKind.SUCCESS),)

    monkeypatch.setattr(learning, "extract_lessons", extract)
    await learning_steps._extract_and_store(
        "task", [Message("tool", "observed content", ok=True)], deps
    )
    assert not stored


def test_informational_command_does_not_create_empty_delivery_card():
    assert evidence_payload(TurnReport(command_runs=(CommandRun("date", 0, True),))) is None


def test_informational_command_retains_warning_and_failed_gate():
    for gate in (
        VerificationResult(ok=True, warnings=("Measurement unavailable",)),
        VerificationResult(ok=False, findings=("Blocked",)),
    ):
        assert evidence_payload(TurnReport(command_runs=(CommandRun("date", 0, True),), gate=gate))


@pytest.mark.parametrize(
    "task",
    [
        "Görseldeki sayıyı oku. Bilgisayar kontrolü, tıklama veya terminal kullanma.",
        "Read this image. Do not use terminal or computer control.",
    ],
)
def test_direct_coordinated_prohibition_caps_families(task):
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.engines.agent.tool_constraints import forbidden_families

    assert forbidden_families(task) == {ToolFamily.SHELL, ToolFamily.DESKTOP}


def test_quoted_or_affirmative_tool_mentions_do_not_deny():
    from fusion_cli.engines.agent.tool_constraints import forbidden_families

    assert not forbidden_families('Explain "terminal kullanma". Terminal kullan.')


async def test_forbidden_family_is_blocked_at_dispatch_without_execution(tmp_path):
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.core.types import ToolCall
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _execute
    from fusion_cli.tools.builtin import build_registry

    deps = _deps(tmp_path)
    result, outcome = await _execute(
        ToolCall("denied", "run_shell", "{}"),
        {"command": "date"},
        deps,
        build_registry(),
        execution=ExecutionPolicy(
            is_web=False, forbidden_tool_families=frozenset({ToolFamily.SHELL})
        ),
    )
    assert not result.ok and outcome.value == "blocked"


async def test_focused_window_policy_rejects_different_or_unknown_pid(tmp_path):
    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.desktop_policy import assess

    context = ToolContext(root=tmp_path)
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    context.desktop.focused_window = (42, 350.0, 260.0, 210.0, 380.0)
    for answer in ({"ok": True, "app": "Notes", "pid": 43}, {"ok": False}):

        async def probe(request, answer=answer):
            return answer

        result = await assess("desktop_click", {"x": 400, "y": 300}, context, probe)
        assert result is not None and result.blocked


async def test_failed_tool_can_teach_observed_mistake_but_not_success(tmp_path, monkeypatch):
    deps = _deps(tmp_path)
    stored = []

    class Store(Memory):
        def all(self):
            return ()

        def add(self, lesson):
            stored.append(lesson)
            return True

    deps.lessons = Store()

    async def extract(*args, **kwargs):
        return (
            Lesson("Invalid option --missing is rejected", LessonKind.MISTAKE),
            Lesson("The command succeeded", LessonKind.SUCCESS),
        )

    monkeypatch.setattr(learning, "extract_lessons", extract)
    await learning_steps._extract_and_store(
        "task", [Message("tool", "unknown option --missing", ok=False)], deps
    )
    assert [lesson.kind for lesson in stored] == [LessonKind.MISTAKE]


@pytest.mark.parametrize("tool_name", ["run_shell", "bash", "desktop_click"])
async def test_original_request_cap_survives_replanned_execution(tmp_path, tool_name):
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.core.types import ToolCall
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _execute
    from fusion_cli.tools.builtin import build_registry

    deps = _deps(tmp_path)
    deps.turn_forbidden_families = frozenset({ToolFamily.SHELL, ToolFamily.DESKTOP})
    result, outcome = await _execute(
        ToolCall("denied", tool_name, "{}"),
        {},
        deps,
        build_registry(),
        execution=ExecutionPolicy(is_web=False),
    )
    assert not result.ok and outcome.value == "blocked"


def test_family_cap_removes_schemas_but_keeps_image_reader(tmp_path):
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.engines.agent.engine_tools import build_agent_registry
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _permitted, run_agent

    deps = _deps(tmp_path)
    deps.config = replace(deps.config, vision=ModelSpec(name="vision", model="fake/vision"))
    registry = build_agent_registry(deps, depth=0, run_agent=run_agent)
    names = _permitted(
        None,
        registry,
        ExecutionPolicy(
            is_web=False, forbidden_tool_families=frozenset({ToolFamily.SHELL, ToolFamily.DESKTOP})
        ),
        set(),
    )
    assert names is not None and "view_image" in names
    assert "run_shell" not in names and "desktop_click" not in names


def test_english_positive_coordinate_clause_does_not_inherit_prohibition():
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.engines.agent.tool_constraints import forbidden_families

    assert forbidden_families("Do not use terminal and use browser.") == {ToolFamily.SHELL}


def test_turkish_instruction_after_comma_preserves_previous_prohibition():
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.engines.agent.tool_constraints import forbidden_families

    assert forbidden_families("Terminal kullanma, sadece görseli oku.") == {ToolFamily.SHELL}


async def test_same_process_other_window_cannot_reuse_focus(tmp_path):
    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.desktop_policy import assess

    context = ToolContext(root=tmp_path)
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    context.desktop.focused_window = (42, 350.0, 260.0, 210.0, 380.0)
    context.desktop.focused_window_id = 101
    context.desktop.focused_window_title = "Expected"

    async def probe(request):
        return {
            "ok": True,
            "app": "Notes",
            "pid": 42,
            "window": {"id": 102, "title": "Other", "bounds": [350.0, 260.0, 210.0, 380.0]},
        }

    result = await assess("desktop_click", {"x": 400, "y": 300}, context, probe)
    assert result is not None and result.blocked


@pytest.mark.parametrize(
    "window,blocked",
    [
        ({"id": 101, "title": "Expected", "bounds": [350.0, 260.0, 210.0, 380.0]}, False),
        ({"id": 101, "title": "Expected", "bounds": [360.0, 260.0, 210.0, 380.0]}, True),
        ({"id": 101, "title": "Renamed", "bounds": [350.0, 260.0, 210.0, 380.0]}, True),
        (None, True),
    ],
)
async def test_focus_checks_current_identity_title_and_geometry(tmp_path, window, blocked):
    from fusion_cli.core.desktop_frame import DesktopFrame
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.desktop_policy import assess

    context = ToolContext(root=tmp_path)
    context.desktop.frame = DesktopFrame(1000, 800, 0, 0, 1000, 800)
    context.desktop.focused_window = (42, 350.0, 260.0, 210.0, 380.0)
    context.desktop.focused_window_id = 101
    context.desktop.focused_window_title = "Expected"

    async def probe(request):
        return {"ok": True, "app": "Notes", "pid": 42, "window": window}

    assessment = await assess("desktop_click", {"x": 400, "y": 300}, context, probe)
    assert assessment is not None and bool(assessment.blocked) == blocked


def test_turkish_inflected_computer_control_is_direct_prohibition():
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.engines.agent.tool_constraints import forbidden_families

    assert forbidden_families("Bilgisayar kontrolünü kullanma.") == {ToolFamily.DESKTOP}


def test_coordinated_object_bans_remain_bans():
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.engines.agent.tool_constraints import forbidden_families

    assert forbidden_families("Terminal, browser veya desktop kullanma.") == {
        ToolFamily.SHELL,
        ToolFamily.BROWSER,
        ToolFamily.DESKTOP,
    }


@pytest.mark.parametrize("name", ["desktop_type", "desktop_key", "desktop_scroll"])
async def test_foreground_interaction_cannot_drift_to_other_window(tmp_path, name):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.desktop_policy import assess

    context = ToolContext(root=tmp_path)
    context.desktop.focused_window = (42, 350.0, 260.0, 210.0, 380.0)
    context.desktop.focused_window_id = 101
    context.desktop.focused_window_title = "Expected"

    async def probe(request):
        return {
            "ok": True,
            "app": "Notes",
            "pid": 42,
            "window": {"id": 102, "title": "Dialog", "bounds": [350.0, 260.0, 210.0, 380.0]},
        }

    assessment = await assess(name, {"text": "hello", "key": "a", "lines": 1}, context, probe)
    assert assessment is not None and assessment.blocked


async def test_original_family_cap_is_serialized_for_background_child(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.agent_task_tools import _inherited_limits
    from fusion_cli.engines.agent.team import SubTask
    from tests.fakes import ScriptedProvider, model_result

    deps = _deps(tmp_path)
    monkeypatch.setattr(
        loop,
        "build_provider",
        lambda *a, **k: ScriptedProvider([model_result("Açıklama tamamlandı.")]),
    )
    await loop.run_agent(
        "Terminal kullanma. Yalnız açıklama yap.", deps, verify=False, self_review=False
    )
    _, options = _inherited_limits(deps, SubTask("Run date"))
    assert options.allowed_tools is not None
    assert "run_shell" not in options.allowed_tools and "bash" not in options.allowed_tools


@pytest.mark.parametrize("name", ["team_run", "SendMessage", "send_message"])
async def test_unbound_worker_or_peer_cannot_bypass_root_family_cap(tmp_path, name):
    from fusion_cli.core.tools import ToolFamily
    from fusion_cli.core.types import ToolCall
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _execute
    from fusion_cli.tools.builtin import build_registry

    deps = _deps(tmp_path)
    deps.turn_forbidden_families = frozenset({ToolFamily.SHELL})
    result, outcome = await _execute(
        ToolCall("denied", name, "{}"),
        {},
        deps,
        build_registry(),
        execution=ExecutionPolicy(is_web=False),
    )
    assert not result.ok and outcome.value == "blocked"
