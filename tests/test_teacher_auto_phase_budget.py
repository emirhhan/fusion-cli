"""Automatic advisory work has an aggregate deadline; explicit tools keep their own policy."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
import yaml

from fusion_cli.config.loader import load_config
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.events import StatusChanged, TeacherPlanPrepared
from fusion_cli.core.tools import ToolResult
from fusion_cli.engines.agent import teacher_flow
from tests.fakes import make_config
from tests.test_teacher_first import _setup

PLAN = '{"adimlar":["Kod hatasını düzelt"],"dosyalar":["src/app.py"]}'


class Registry:
    def __init__(self, results, *, delay=0.04, swallow_cancel=False):
        self.results = iter(results)
        self.delay = delay
        self.swallow_cancel = swallow_cancel
        self.calls = 0
        self.started = asyncio.Event()
        self.cleaned = False

    def __iter__(self):
        return iter(())

    async def execute(self, name, args, context):
        self.calls += 1
        self.started.set()
        result = next(self.results)
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            await asyncio.sleep(0.02)
            self.cleaned = True
            if not self.swallow_cancel:
                raise
        return result


def deps_for_phase(monkeypatch, tmp_path, *, phase=0.07, request=600):
    deps, sink, *_ = _setup(monkeypatch, tmp_path)
    deps.config = SimpleNamespace(
        runtime=SimpleNamespace(
            teacher_timeout_s=0.3,
            teacher_auto_phase_timeout_s=phase,
            request_timeout_s=request,
        )
    )
    monkeypatch.setattr(teacher_flow, "teacher_is_ready", lambda *_args: True)
    return deps, sink


@pytest.mark.parametrize("first", [ToolResult.failure("transient"), ToolResult("invalid plan")])
async def test_automatic_plan_retry_and_format_repair_share_one_budget(
    monkeypatch, tmp_path, first
):
    deps, sink = deps_for_phase(monkeypatch, tmp_path)
    registry = Registry([first, ToolResult(PLAN)])
    await teacher_flow.prepare_teacher_plan("src/app.py içindeki hatayı düzelt", [], deps, registry)
    assert registry.calls == 2
    assert deps.pending_teacher_plan is None
    assert not deps.tool_context.todos.items
    assert not any(isinstance(event, TeacherPlanPrepared) for event in sink.events)
    assert not deps.teacher_unavailable_notified
    assert any(
        "süre" in event.message.lower() for event in sink.events if isinstance(event, StatusChanged)
    )


async def test_slow_cancellation_cleanup_cannot_apply_late_plan(monkeypatch, tmp_path):
    deps, sink = deps_for_phase(monkeypatch, tmp_path, phase=0.03)
    registry = Registry([ToolResult(PLAN)], delay=0.15, swallow_cancel=True)
    await teacher_flow.prepare_teacher_plan("src/app.py içindeki hatayı düzelt", [], deps, registry)
    assert registry.cleaned
    assert deps.pending_teacher_plan is None
    assert not deps.tool_context.todos.items
    assert not any(isinstance(event, TeacherPlanPrepared) for event in sink.events)
    assert not deps.teacher_unavailable_notified
    assert not deps.teacher_lesson_sync_deferred


async def test_real_user_cancellation_is_not_swallowed_or_turned_into_advisory_timeout(
    monkeypatch, tmp_path
):
    deps, sink = deps_for_phase(monkeypatch, tmp_path, phase=1)
    registry = Registry([ToolResult(PLAN)], delay=0.15, swallow_cancel=True)
    task = asyncio.create_task(
        teacher_flow.prepare_teacher_plan("src/app.py içindeki hatayı düzelt", [], deps, registry)
    )
    await registry.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert registry.cleaned
    assert not deps.tool_context.todos.items
    assert not any(isinstance(event, TeacherPlanPrepared) for event in sink.events)


async def test_only_authoritative_turn_deadline_can_shorten_automatic_budget(monkeypatch, tmp_path):
    deps, _sink = deps_for_phase(monkeypatch, tmp_path, phase=0.1, request=0.001)
    registry = Registry([ToolResult(PLAN)], delay=0.02)
    await teacher_flow.prepare_teacher_plan("src/app.py içindeki hatayı düzelt", [], deps, registry)
    assert deps.pending_teacher_plan is not None


async def test_authoritative_turn_deadline_is_respected(monkeypatch, tmp_path):
    deps, _sink = deps_for_phase(monkeypatch, tmp_path, phase=1)
    deps.deadline = SimpleNamespace(remaining_s=lambda: 0.04)
    registry = Registry([ToolResult(PLAN)], delay=0.15)
    await teacher_flow.prepare_teacher_plan("src/app.py içindeki hatayı düzelt", [], deps, registry)
    assert deps.pending_teacher_plan is None
    assert registry.calls == 0 or registry.cleaned
    assert not deps.teacher_unavailable_notified


def test_default_config_documents_automatic_cap_without_changing_other_timeouts(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("runtime: {}\n")
    runtime = load_config(path).runtime
    assert runtime.teacher_auto_phase_timeout_s == 30.0
    assert runtime.teacher_timeout_s == 300.0
    assert runtime.request_timeout_s == 600.0


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), float("-inf"), True])
def test_automatic_timeout_requires_positive_finite_value_in_config_and_dataclass(tmp_path, value):
    with pytest.raises(ConfigError, match="teacher_auto_phase_timeout_s"):
        replace(make_config().runtime, teacher_auto_phase_timeout_s=value)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"runtime": {"teacher_auto_phase_timeout_s": value}}))
    with pytest.raises(ConfigError, match="teacher_auto_phase_timeout_s"):
        load_config(path)


async def test_manual_model_teacher_tool_keeps_its_existing_request_timeout(monkeypatch, tmp_path):
    from fusion_cli.core.types import ModelSpec
    from tests.test_ask_teacher import _deps, _ogretmen, _OgretmenSaglayici, _registry

    class SlowTeacher(_OgretmenSaglayici):
        async def complete(self, request):
            await asyncio.sleep(0.03)
            return await super().complete(request)

    provider = SlowTeacher()
    _ogretmen(monkeypatch, provider)
    deps = _deps(tmp_path, teacher=ModelSpec(name="teacher", model="fake/teacher"))
    deps.config = replace(
        deps.config,
        runtime=replace(
            deps.config.runtime,
            teacher_auto_phase_timeout_s=0.005,
            teacher_timeout_s=0.01,
            request_timeout_s=0.4,
        ),
    )
    result = await _registry(deps).execute(
        "ask_teacher", {"question": "Somut sorum"}, deps.tool_context
    )
    assert result.ok
    assert provider.seen[0].timeout_s == 0.4
    assert not deps.teacher_unavailable_notified


async def test_disabled_teacher_configuration_stays_disabled(monkeypatch, tmp_path):
    deps, _sink = deps_for_phase(monkeypatch, tmp_path)
    monkeypatch.setattr(teacher_flow, "teacher_is_ready", lambda *_args: False)
    registry = Registry([ToolResult(PLAN)])
    await teacher_flow.prepare_teacher_plan("src/app.py içindeki hatayı düzelt", [], deps, registry)
    assert registry.calls == 0
    assert deps.pending_teacher_plan is None


async def test_final_automatic_review_has_phase_budget_without_disabling_teacher(
    monkeypatch, tmp_path
):
    from fusion_cli.engines.agent.loop import AgentOutcome

    deps, sink = deps_for_phase(monkeypatch, tmp_path, phase=0.08)
    path = tmp_path / "app.py"
    path.write_text("value = 1\n")
    deps.tool_context.changes.record(path)
    registry = Registry([ToolResult('{"bulgular":[]}')], delay=0.2, swallow_cancel=True)
    result = await teacher_flow.review_teacher_changes(
        "app.py hatasını düzelt", AgentOutcome("Düzeltildi.", []), deps, registry
    )
    assert result is None
    assert not deps.teacher_unavailable_notified
    assert not any(isinstance(event, TeacherPlanPrepared) for event in sink.events)


async def test_cancel_converted_to_timeout_error_is_not_retried(monkeypatch, tmp_path):
    deps, _sink = deps_for_phase(monkeypatch, tmp_path, phase=1)

    class ConvertedCancellation(Registry):
        async def execute(self, name, args, context):
            self.calls += 1
            self.started.set()
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError as error:
                await asyncio.sleep(0.01)
                self.cleaned = True
                raise TimeoutError("provider converted cancellation") from error

    registry = ConvertedCancellation([])
    task = asyncio.create_task(
        teacher_flow.prepare_teacher_plan("src/app.py hatasını düzelt", [], deps, registry)
    )
    await registry.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert registry.calls == 1 and registry.cleaned
    assert not deps.tool_context.todos.items
