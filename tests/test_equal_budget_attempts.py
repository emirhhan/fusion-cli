"""Deney bütçesi normal ek aday hakkından ayrı ve ortak toplamdır."""

from __future__ import annotations

import pytest

from fusion_cli.core.execution_plan import ExecutionPlan
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent.attempts import AttemptExperiment, InvocationBudget
from fusion_cli.engines.agent.execution_policy import policy_for


def test_cagri_hakki_baslamadan_tuketilir_ve_tavan_asilmaz() -> None:
    budget = InvocationBudget(3)
    assert [budget.claim() for _ in range(5)] == [True, True, True, False, False]
    assert budget.used == 3
    assert budget.remaining == 0


def test_iki_slot_haklari_onceden_sabit_ve_artakalan_aktarilmaz() -> None:
    experiment = AttemptExperiment(
        "candidates", 6, 2, ModelSpec("agent", "yerel/test", tags=("strict",)), "is"
    )
    assert experiment.slot_limits == (2, 4)


@pytest.mark.parametrize("total,first", [(1, 1), (4, 0), (4, 4), (0, 1)])
def test_gecersiz_iki_slot_paylasimi_reddedilir(total: int, first: int) -> None:
    with pytest.raises(ValueError):
        AttemptExperiment(
            "candidates", total, first, ModelSpec("agent", "yerel/test", tags=("strict",)), "is"
        )


def test_strict_olmayan_deney_reddedilir() -> None:
    with pytest.raises(ValueError):
        AttemptExperiment("serial", 4, 2, ModelSpec("agent", "yerel/test"), "is")


def test_aday_yerel_ve_toplam_yasam_dongusu_hakkini_birlikte_tuketir() -> None:
    total = InvocationBudget(6)
    first = InvocationBudget(2, parent=total)
    second = InvocationBudget(4, parent=total)
    assert [first.claim() for _ in range(3)] == [True, True, False]
    assert [second.claim() for _ in range(5)] == [True, True, True, True, False]
    assert total.used == 6


@pytest.mark.parametrize("arm,expected_allocations", [("candidates", [2, 2]), ("serial", [4])])
async def test_gercek_caller_iki_slot_ve_onarimi_ayni_toplamda_sinirlar(
    tmp_path, monkeypatch, arm, expected_allocations
) -> None:
    from evals.agent_runner import _CountingPublisher, _EvalApproval, _NullPublisher
    from evals.candidate_metrics import reduce_candidate_metrics
    from evals.profiles import prepare_attempt_experiment

    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.plan_runner import run_execution_plan
    from tests.fakes import make_config
    from tests.test_attempts_wiring import _adim

    prepared = prepare_attempt_experiment(
        make_config(memory_dir=tmp_path), arm=arm, total_calls=4, first_slot_calls=2, task_id="is"
    )
    publisher = _CountingPublisher(_NullPublisher())
    specs = []
    identifiers = iter(f"call{index}" for index in range(20))
    monkeypatch.setattr(loop, "build_provider", _provider_factory(specs, identifiers))
    deps = loop.AgentDeps(prepared.config, publisher, _EvalApproval(), ToolContext(root=tmp_path))
    deps.execution = policy_for(prepared.config, prepared.config.agent, "dosyayı düzelt")
    allocations = []

    async def agent(task, active, **kwargs):
        del kwargs
        allocations.append(active.execution.max_model_calls)
        for _ in range(4):
            await loop._call_model(
                [Message("user", task)],
                active,
                active.base_registry,
                state=loop._State(),
                execution=active.execution,
                offer_tools=False,
            )
        (active.tool_context.root / "kod.py").write_text("yanlış", encoding="utf-8")
        return loop.AgentOutcome("aday", [], ok=False, model_calls_made=2, tool_calls_made=1)

    result = await run_execution_plan(
        "iş",
        deps,
        agent,
        plan=ExecutionPlan("budget", "iş", (_adim("kod.py"),)),
        experiment=prepared.experiment,
    )
    metrics = reduce_candidate_metrics(publisher.events)
    assert not result.ok
    assert allocations == expected_allocations
    assert len(specs) == metrics.lifecycle_calls == 4
    assert all(spec == prepared.config.agent for spec in specs)
    _assert_scope(publisher.events, arm)
    if arm == "candidates":
        assert metrics.two_candidate_tasks == 1
        assert metrics.oracle_at_2 == metrics.selected_at_2 == 0.0
    else:
        assert metrics.two_candidate_tasks == 0
        assert metrics.serial_at_c == 0.0


def test_dinamik_override_butceyi_farkli_modele_kullandiramaz() -> None:
    original = ModelSpec("agent", "yerel/test", tags=("strict",))
    budget = InvocationBudget(4, requested_spec=original)
    slot = InvocationBudget(2, parent=budget)
    assert not slot.claim(ModelSpec("agent", "baska/model", tags=("strict",)))
    assert budget.used == slot.used == 0
    assert slot.claim(original)
    assert budget.used == slot.used == 1


@pytest.mark.parametrize(
    "flag,value",
    [
        ("auto_web_fallback", True),
        ("teacherless", False),
        ("lessons", True),
        ("teacher_lesson_sync", True),
        ("teacher_codex_fallback", True),
        ("escalate_on_gate_failure", True),
        ("self_review", True),
        ("web_verification", True),
    ],
)
async def test_deney_model_kacisi_ayarini_cagri_acmadan_reddeder(tmp_path, flag, value) -> None:
    from dataclasses import replace

    from evals.agent_runner import _EvalApproval, _NullPublisher
    from evals.profiles import prepare_attempt_experiment

    from fusion_cli.engines.agent.loop import AgentDeps
    from fusion_cli.engines.agent.plan_runner import run_execution_plan
    from tests.fakes import make_config

    prepared = prepare_attempt_experiment(
        make_config(memory_dir=tmp_path),
        arm="serial",
        total_calls=4,
        first_slot_calls=2,
        task_id="is",
    )
    config = replace(prepared.config, runtime=replace(prepared.config.runtime, **{flag: value}))
    deps = AgentDeps(config, _NullPublisher(), _EvalApproval(), ToolContext(root=tmp_path))

    async def forbidden_agent(*args, **kwargs):
        raise AssertionError("Model çağrısı açılmamalı")

    with pytest.raises(ValueError, match="strict model"):
        await run_execution_plan("iş", deps, forbidden_agent, experiment=prepared.experiment)


def _provider_factory(specs, identifiers, unavailable=False):
    from fusion_cli.core.types import ModelResult
    from fusion_cli.providers.eventing import EventingProvider
    from tests.fakes import ScriptedProvider

    def factory(spec, **kwargs):
        specs.append(spec)

        class NamedProvider(ScriptedProvider):
            @property
            def label(self):
                return spec.model

        provider = NamedProvider(
            [
                ModelResult(
                    spec.name,
                    spec.model,
                    "yanlış",
                    1,
                    not unavailable,
                    served_by=spec.model,
                    error="AuthenticationError: geçersiz oturum" if unavailable else None,
                )
            ]
        )
        return EventingProvider(
            provider,
            publisher=kwargs["publisher"],
            role="agent",
            call_id_factory=lambda: next(identifiers),
        )

    return factory


def _assert_scope(events, arm):
    from fusion_cli.core.events import CandidateFinished, ModelCallStarted

    starts = [event for event in events if isinstance(event, ModelCallStarted)]
    assert len({event.turn_id for event in starts}) == 1
    assert starts[0].turn_id is not None
    if arm == "candidates":
        assert len({event.candidate_id for event in starts}) == 2
        finished = [
            event
            for event in events
            if isinstance(event, CandidateFinished) and event.scope == "step"
        ]
        assert [len(event.call_ids) for event in finished] == [2, 2]


@pytest.mark.parametrize("layout", ["later-step", "multi-final", "candidate-final", "root-final"])
async def test_gorev_metrigi_sonraki_adim_ve_finali_gizlemez(tmp_path, monkeypatch, layout):
    from dataclasses import replace

    from evals.candidate_metrics import reduce_candidate_metrics

    from fusion_cli.core.execution_plan import RetrySafety
    from fusion_cli.engines.agent import plan_runner
    from tests.test_attempts_wiring import _adim

    deps, sink, experiment, agent = _experiment_fixture(tmp_path, monkeypatch, "candidates")
    steps = (_adim("kod.py"),)
    if layout == "later-step":
        steps += (
            replace(
                _adim("b.py"),
                step_id="later",
                depends_on=(steps[0].step_id,),
                retry_safety=RetrySafety.NEVER,
            ),
        )
    if layout == "multi-final":
        steps += (replace(_adim("b.py"), step_id="second", depends_on=(steps[0].step_id,)),)
    if layout != "later-step":
        original = plan_runner.verify_plan_acceptance

        async def fail_final(plan, active, **kwargs):
            result = await original(plan, active, **kwargs)
            if layout == "candidate-final" or active.tool_context.root == tmp_path:
                return replace(result, ok=False, findings=("Final kabulü başarısız.",))
            return result

        monkeypatch.setattr(plan_runner, "verify_plan_acceptance", fail_final)
    outcome = await plan_runner.run_execution_plan(
        "iş", deps, agent, plan=ExecutionPlan("plan", "iş", steps), experiment=experiment
    )
    metrics = reduce_candidate_metrics(sink.events)
    assert not outcome.ok
    assert metrics.candidate_tasks == 1
    if layout in {"later-step", "multi-final"}:
        assert metrics.pass_at_1 is metrics.oracle_at_2 is metrics.selected_at_2 is None
        assert metrics.unsupported_candidate_tasks == 1
        assert metrics.step_oracle_at_2 == 1.0
        assert metrics.candidate_steps == (2 if layout == "multi-final" else 1)
    else:
        assert metrics.pass_at_1 == metrics.oracle_at_2 == (layout == "root-final")
        assert metrics.selected_at_2 == 0.0


async def test_seri_planlama_hatasi_paydadan_dusmez(tmp_path, monkeypatch):
    from evals.candidate_metrics import reduce_candidate_metrics

    from fusion_cli.core.events import AttemptExperimentFinished
    from fusion_cli.engines.agent.plan_runner import run_execution_plan
    from tests.test_attempts_wiring import _adim

    good = tmp_path / "good"
    bad = tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    deps, first, experiment, agent = _experiment_fixture(good, monkeypatch, "serial", "good")
    assert (
        await run_execution_plan(
            "iş",
            deps,
            agent,
            plan=ExecutionPlan("plan", "iş", (_adim("kod.py"),)),
            experiment=experiment,
        )
    ).ok
    deps, second, experiment, agent = _experiment_fixture(bad, monkeypatch, "serial", "bad")
    outcome = await run_execution_plan("iş", deps, agent, experiment=experiment)
    assert not outcome.ok
    finished = [event for event in second.events if isinstance(event, AttemptExperimentFinished)]
    assert len(finished) == 1 and finished[0].used_calls == 2
    assert reduce_candidate_metrics(second.events).serial_at_c == 0.0
    assert reduce_candidate_metrics(first.events + second.events).serial_at_c == 0.5


async def test_gecersiz_plan_sifir_cagriyla_tam_bir_sonuc_uretir(tmp_path, monkeypatch):
    from evals.candidate_metrics import reduce_candidate_metrics

    from fusion_cli.core.events import AttemptExperimentFinished
    from fusion_cli.engines.agent.plan_runner import run_execution_plan

    deps, sink, experiment, agent = _experiment_fixture(tmp_path, monkeypatch, "serial")
    from dataclasses import replace

    from tests.test_attempts_wiring import _adim

    step = _adim("kod.py")
    invalid = replace(step, depends_on=(step.step_id,))
    result = await run_execution_plan(
        "iş", deps, agent, plan=ExecutionPlan("plan", "iş", (invalid,)), experiment=experiment
    )
    finished = [event for event in sink.events if isinstance(event, AttemptExperimentFinished)]
    assert not result.ok
    assert len(finished) == 1 and finished[0].used_calls == 0
    assert reduce_candidate_metrics(sink.events).serial_at_c == 0.0


def _experiment_fixture(root, monkeypatch, arm, task_id="task", unavailable=False):
    from evals.agent_runner import _CountingPublisher, _EvalApproval, _NullPublisher
    from evals.profiles import prepare_attempt_experiment

    from fusion_cli.core.evidence import ToolUse
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools import build_registry
    from tests.fakes import make_config

    prepared = prepare_attempt_experiment(
        make_config(memory_dir=root), arm=arm, total_calls=6, first_slot_calls=3, task_id=task_id
    )
    sink = _CountingPublisher(_NullPublisher())
    ids = iter(f"{task_id}-{index}" for index in range(30))
    monkeypatch.setattr(loop, "build_provider", _provider_factory([], ids, unavailable))
    deps = loop.AgentDeps(prepared.config, sink, _EvalApproval(), ToolContext(root=root))

    async def agent(task, active, **kwargs):
        reply = await loop._call_model(
            [Message("user", task)],
            active,
            active.base_registry,
            state=loop._State(),
            execution=active.execution,
            offer_tools=False,
        )
        if kwargs.get("plan_mode"):
            return loop.AgentOutcome("geçersiz plan", [], ok=reply.ok, model_calls_made=1)
        step = active.context_step
        path = step.verification_checks[0].target
        content = "yanlış" if step.step_id == "later" else "sağlam"
        arguments = {"path": path, "content": content}
        written = await build_registry().execute("write_file", arguments, active.tool_context)
        return loop.AgentOutcome(
            "tamam",
            [],
            ok=reply.ok and written.ok and content == "sağlam",
            model_calls_made=1,
            tool_calls_made=1,
            mutating_tool_calls_made=1,
            tool_uses=(ToolUse("write_file", written.ok, True, arguments),),
        )

    return deps, sink, prepared.experiment, agent


async def test_saglayici_erisilemezligi_olculen_basarisizlik_diye_sayilmaz(tmp_path, monkeypatch):
    from evals.candidate_metrics import reduce_candidate_metrics

    from fusion_cli.core.events import AttemptExperimentFinished
    from fusion_cli.engines.agent.plan_runner import run_execution_plan

    deps, sink, experiment, agent = _experiment_fixture(
        tmp_path, monkeypatch, "serial", unavailable=True
    )
    result = await run_execution_plan("iş", deps, agent, experiment=experiment)
    finished = [event for event in sink.events if isinstance(event, AttemptExperimentFinished)]
    assert not result.ok
    assert len(finished) == 1 and finished[0].measurement == "unavailable"
    assert finished[0].used_calls == 1
    metrics = reduce_candidate_metrics(sink.events)
    assert metrics.serial_at_c is None
    assert metrics.unavailable_serial_tasks == 1
