"""Main context input measurements follow actor purpose, never a candidate's name."""

from dataclasses import replace

import pytest

from fusion_cli.appserver.usage import UsageMeter
from fusion_cli.core.events import Event, ModelCallFinished
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message, ModelResult, ModelSpec, TokenUsage
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.team import ScopedPublisher
from fusion_cli.providers import factory
from fusion_cli.tools.registry import ToolRegistry
from tests.fakes import AlwaysApprove, ScriptedProvider, make_config


class MeasuredPublisher:
    def __init__(self):
        self.meter = UsageMeter()
        self.events: list[Event] = []

    def publish(self, event: Event) -> None:
        self.events.append(event)
        self.meter.observe(event)


def measured_result(name="secilen", *, tokens=26_262):
    return ModelResult(
        name=name,
        model="fake/selected-model",
        text="Ölçülen yanıt.",
        latency_ms=1,
        ok=True,
        usage=TokenUsage(
            prompt_tokens=tokens,
            completion_tokens=10,
            prompt_measured=True,
            completion_measured=True,
        ),
    )


@pytest.mark.parametrize("name", ["secilen", "user-defined-candidate", "agent"])
async def test_actual_actor_candidate_name_does_not_hide_last_input_measurement(
    tmp_path, monkeypatch, name
):
    publisher = MeasuredPublisher()
    result = measured_result(name)
    monkeypatch.setattr(factory, "configure_litellm", lambda: None)
    monkeypatch.setattr(
        factory, "LiteLlmProvider", lambda *_args, **_kwargs: ScriptedProvider([result])
    )
    deps = loop.AgentDeps(
        config=make_config(agent=ModelSpec(name=name, model=result.model, tags=("strict",))),
        publisher=publisher,
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    outcome = await loop._call_model(
        [Message("user", "Merhaba")],
        deps,
        ToolRegistry(),
        state=loop._State(),
        execution=ExecutionPolicy(is_web=False, offer_tools=False),
        offer_tools=False,
    )

    assert outcome.ok
    assert publisher.meter.total.prompt_tokens == result.usage.prompt_tokens
    assert publisher.meter.total.completion_tokens == result.usage.completion_tokens
    finished = [event for event in publisher.events if isinstance(event, ModelCallFinished)]
    assert len(finished) == 1 and finished[0].role == name
    assert publisher.meter.last_agent_prompt_tokens == 26_262
    assert publisher.meter.last_agent_model == result.model
    assert getattr(finished[0], "purpose", None) == "actor"


@pytest.mark.parametrize("name", ["agent", "secilen", "teacher", "judge", "intro"])
async def test_nonactor_provider_with_any_candidate_name_does_not_replace_actor_measurement(
    monkeypatch, name
):
    publisher = MeasuredPublisher()
    original = measured_result("original", tokens=100)
    publisher.publish(ModelCallFinished(role="agent", result=original))
    helper = measured_result(name, tokens=999)
    monkeypatch.setattr(factory, "configure_litellm", lambda: None)
    monkeypatch.setattr(
        factory, "LiteLlmProvider", lambda *_args, **_kwargs: ScriptedProvider([helper])
    )
    provider = factory.build_provider(
        ModelSpec(name=name, model=helper.model), publisher=publisher, retry_delays_s=()
    )
    from tests.fakes import request

    await provider.complete(request())

    assert publisher.meter.calls == 2
    assert publisher.meter.total.prompt_tokens == 1_099
    assert publisher.meter.last_agent_prompt_tokens == 100
    assert publisher.meter.last_agent_model == original.model
    event = publisher.events[-1]
    assert isinstance(event, ModelCallFinished)
    assert event.role == name and event.purpose == "other"


@pytest.mark.parametrize(
    "background,agent_id,ok,measured,tokens,purpose",
    [
        (True, "", True, True, 999, "actor"),
        (False, "child", True, True, 999, "actor"),
        (False, "child", True, True, 999, None),
        (False, "", False, True, 999, "actor"),
        (False, "", True, False, 999, "actor"),
        (False, "", True, False, 999, None),
        (False, "", True, True, 0, "actor"),
        (False, "", True, True, 999, "other"),
    ],
)
def test_nonroot_or_unmeasured_results_do_not_overwrite_last_actor(
    background, agent_id, ok, measured, tokens, purpose
):
    publisher = MeasuredPublisher()
    original = measured_result(tokens=100)
    publisher.publish(ModelCallFinished(role="agent", result=original))
    excluded = replace(
        measured_result("agent", tokens=tokens),
        ok=ok,
        usage=replace(measured_result(tokens=tokens).usage, prompt_measured=measured),
    )
    publisher.publish(
        ModelCallFinished(
            role="agent",
            result=excluded,
            purpose=purpose,
            background=background,
            agent_id=agent_id,
        )
    )

    assert publisher.meter.calls == 2
    assert publisher.meter.total.prompt_tokens == 100 + tokens
    assert publisher.meter.last_agent_prompt_tokens == 100


async def test_scoped_child_actor_keeps_purpose_without_contaminating_root_meter():
    from fusion_cli.providers.eventing import EventingProvider
    from tests.fakes import request

    publisher = MeasuredPublisher()
    result = measured_result()
    provider = EventingProvider(
        ScriptedProvider([result]),
        publisher=ScopedPublisher(publisher, "child-1"),
        role="secilen",
        purpose="actor",
    )

    await provider.complete(request())

    assert publisher.meter.calls == 1
    assert publisher.meter.total.prompt_tokens == 26_262
    assert publisher.meter.last_agent_prompt_tokens is None
    finished = publisher.events[-1]
    assert isinstance(finished, ModelCallFinished)
    assert finished.agent_id == "child-1" and finished.purpose == "actor"


def test_actor_purpose_round_trips_without_changing_legacy_role():
    from fusion_cli.appserver.serialize import event_to_dict
    from fusion_cli.observability.replay import event_from_payload

    event = ModelCallFinished(role="secilen", result=measured_result(), purpose="actor")
    payload = event_to_dict(event)
    restored = event_from_payload({**payload, "event": payload.pop("olay")})

    assert restored == event
    legacy = event_from_payload(
        {
            key: value
            for key, value in {**payload, "event": "ModelCallFinished"}.items()
            if key != "purpose"
        }
    )
    assert isinstance(legacy, ModelCallFinished) and legacy.purpose is None


def test_actor_measurement_does_not_change_selected_context_budget(monkeypatch):
    from fusion_cli.appserver import context_gauge
    from fusion_cli.engines.agent.context_budget import ContextBudget

    budget = ContextBudget(360_678, 262_144, "fake/selected-model")
    monkeypatch.setattr(context_gauge, "input_window_tokens", lambda _model: 262_144)
    before = context_gauge.baglam_olcusu([], budget=budget)
    publisher = MeasuredPublisher()
    publisher.publish(
        ModelCallFinished(role="candidate", result=measured_result(), purpose="actor")
    )
    after = context_gauge.baglam_olcusu(
        [],
        budget=budget,
        last_prompt_tokens=publisher.meter.last_agent_prompt_tokens,
        last_prompt_model=publisher.meter.last_agent_model,
    )

    assert before["model_siniri_token"] == after["model_siniri_token"] == 262_144
    assert before["sinir"] == after["sinir"] == 360_678
    assert before["son_girdi_token"] is None
    assert after["son_girdi_token"] == 26_262
