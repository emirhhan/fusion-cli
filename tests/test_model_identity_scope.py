"""Model identity follows the provider request, rather than the configured default."""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.turn_hints import identity_hint
from fusion_cli.tools import ToolRegistry

from .fakes import RecordingSink, ScriptedProvider, model_result
from .test_agent_loop import _deps


def _capture_provider(monkeypatch, *, results=None):
    provider = ScriptedProvider(results or [model_result("Yanıt.")] * 4)
    selected = []

    def build(spec, **kwargs):
        selected.append(spec)
        return provider

    monkeypatch.setattr(loop, "build_provider", build)
    return provider, selected


async def test_task_mapping_identity_matches_actual_request(tmp_path, monkeypatch):
    default = ModelSpec("default", "sahte/default", tags=("agent",))
    mapped = ModelSpec("mapped", "sahte/mapped", tags=("agent",))
    deps = _deps(
        tmp_path,
        RecordingSink(),
        agent=default,
        candidates=(mapped,),
        task_model_map={"general": "mapped"},
    )
    provider, selected = _capture_provider(monkeypatch)

    await loop.run_agent("Hangi modeli kullanıyorsun?", deps, verify=False)

    assert selected[0].model == mapped.model
    system = "\n".join(m.content for m in provider.seen_messages[0] if m.role == "system")
    # Task mapping retains the default as an availability fallback; name the
    # requested primary truthfully without pretending it is the serving leaf.
    assert f"`{mapped.model}`" in system
    assert identity_hint(default.model) not in system


async def test_active_override_refreshes_inherited_identity_without_rewriting_user(
    tmp_path, monkeypatch
):
    default = ModelSpec("default", "sahte/default", tags=("agent",))
    override = ModelSpec("override", "sahte/override", tags=("agent",))
    deps = _deps(tmp_path, RecordingSink(), agent=default, task_model_map={})
    provider, selected = _capture_provider(monkeypatch)
    quoted = "Kullanıcı alıntısı: " + str(identity_hint(default.model))
    messages = [Message("system", "Özel sistem kuralı."), Message("user", quoted)]
    execution = ExecutionPolicy(is_web=False)

    await loop._call_model(messages, deps, ToolRegistry(), state=loop._State(), execution=execution)
    deps.active_model_override = override
    await loop._call_model(messages, deps, ToolRegistry(), state=loop._State(), execution=execution)

    assert [spec.model for spec in selected] == [default.model, override.model]
    first_system = "\n".join(m.content for m in provider.seen_messages[0] if m.role == "system")
    next_system = "\n".join(m.content for m in provider.seen_messages[1] if m.role == "system")
    assert identity_hint(default.model) in first_system
    assert identity_hint(override.model) in next_system
    assert identity_hint(default.model) not in next_system
    assert next_system.startswith("Özel sistem kuralı.")
    assert provider.seen_messages[1][-1].content == quoted


async def test_fallback_request_does_not_claim_primary_is_the_serving_model(tmp_path, monkeypatch):
    spec = ModelSpec("primary", "sahte/primary", fallback=("sahte/backup",), tags=("agent",))
    deps = _deps(tmp_path, RecordingSink(), agent=spec, task_model_map={})
    # The fallback result is a fact only after the provider has answered. The same
    # request can be served by either leaf, so it must not assert a current leaf.
    served = replace(model_result("Yanıt."), model="sahte/backup")
    provider, _selected = _capture_provider(monkeypatch, results=[served])
    messages = [Message("system", "Özel sistem kuralı."), Message("user", "Hangi model?")]

    result = await loop._call_model(
        messages,
        deps,
        ToolRegistry(),
        state=loop._State(),
        execution=ExecutionPolicy(is_web=False),
    )

    system = "\n".join(m.content for m in provider.seen_messages[0] if m.role == "system")
    assert identity_hint(spec.model) not in system
    assert "birincil model" in system
    assert "henüz doğrulanmadı" in system
    assert result.model == "sahte/backup"


async def test_repeated_requests_keep_one_identity_and_no_extra_system_messages(
    tmp_path, monkeypatch
):
    spec = ModelSpec("selected", "sahte/selected", tags=("agent",))
    deps = _deps(tmp_path, RecordingSink(), agent=spec, task_model_map={})
    provider, _selected = _capture_provider(monkeypatch)
    messages = [Message("system", "Özel sistem kuralı."), Message("user", "Hangi model?")]
    for _ in range(3):
        await loop._call_model(
            messages,
            deps,
            ToolRegistry(),
            state=loop._State(),
            execution=ExecutionPolicy(is_web=False),
        )

    for request_messages in provider.seen_messages:
        systems = [m.content for m in request_messages if m.role == "system"]
        assert len(systems) == 1
        assert systems[0].count(str(identity_hint(spec.model))) == 1


async def test_request_without_initial_system_does_not_accumulate_identity(tmp_path, monkeypatch):
    spec = ModelSpec("selected", "sahte/selected", tags=("agent",))
    deps = _deps(tmp_path, RecordingSink(), agent=spec, task_model_map={})
    provider, _selected = _capture_provider(monkeypatch)
    messages = [Message("user", "Hangi model?")]

    for _ in range(2):
        await loop._call_model(
            messages,
            deps,
            ToolRegistry(),
            state=loop._State(),
            execution=ExecutionPolicy(is_web=False),
        )

    assert provider.seen_messages[0] == provider.seen_messages[1]
    assert provider.seen_messages[1][0].content.count(str(identity_hint(spec.model))) == 1
