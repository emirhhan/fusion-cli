import pytest
from evals import direct_runner
from evals.direct_runner import extract_html
from evals.metrics import RunReport
from evals.profiles import EvalProfile, RunMetadata
from evals.report import report_from_dict, report_to_dict

from fusion_cli.config.models import Config
from fusion_cli.core.types import Message, ModelResult, ModelSpec
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome

from .fakes import ScriptedProvider, make_config


def _ready_web_fallbacks(_config: Config) -> tuple[str, ...]:
    return ("verified-web-other",)


def _result_for_provider_spec(spec: ModelSpec) -> ModelResult:
    if spec.fallback:
        return ModelResult(
            name=spec.name,
            model=spec.fallback[0],
            text="başka web modeli yanıtladı",
            latency_ms=1,
            ok=True,
            served_by=spec.fallback[0],
        )
    return ModelResult(
        name=spec.name,
        model=spec.model,
        text="",
        latency_ms=1,
        ok=False,
        error="AuthenticationError: invalid API key",
    )


def _scripted_provider_factory(specs: list[ModelSpec], providers: list[ScriptedProvider]):
    def build_provider(spec: ModelSpec, **_kwargs: object) -> ScriptedProvider:
        specs.append(spec)
        provider = ScriptedProvider([_result_for_provider_spec(spec)])
        providers.append(provider)
        return provider

    return build_provider


async def _call_eval_model(request: str, deps: AgentDeps) -> AgentOutcome:
    assert deps.base_registry is not None
    result = await loop._call_model(
        [Message("user", request)],
        deps,
        deps.base_registry,
        state=loop._State(),
        execution=ExecutionPolicy(is_web=False, offer_tools=False),
        offer_tools=False,
    )
    return AgentOutcome(
        final_text=result.text or result.error or "",
        messages=[],
        ok=result.ok,
        model_calls_made=1,
    )


def test_profiles_have_stable_cli_values():
    assert [profile.value for profile in EvalProfile] == [
        "production",
        "fusion-full",
        "fusion-minimal",
        "direct",
    ]


def test_report_metadata_round_trips_and_legacy_reports_still_load():
    metadata = RunMetadata(suite="arena.yaml", profile="direct", model="model-x", repeat=3)
    restored = report_from_dict(report_to_dict(RunReport(results=(), metadata=metadata)))
    assert restored.metadata == metadata
    assert report_from_dict({"results": []}).metadata is None


def test_direct_extracts_one_fenced_or_raw_complete_document():
    fenced = "```html\n<!doctype html><html><body>x</body></html>\n```"
    raw = "<!doctype html><html><body>x</body></html>"
    assert extract_html(fenced) == raw
    assert extract_html(raw) == raw
    padded = f"\n{raw}\n"
    assert extract_html(padded) == padded


def test_direct_rejects_commentary_multiple_fences_and_incomplete_html():
    assert extract_html("Here you go\n```html\n<html></html>\n```") is None
    assert extract_html("```html\n<html></html>\n```\n```html\n<html></html>\n```") is None
    assert extract_html("<html><body>unfinished") is None
    assert extract_html("<html></html> trailing commentary") is None


def test_direct_uses_configured_web_session_registry(monkeypatch):
    config = make_config()
    publisher = object()
    registry = object()
    provider = object()
    captured = {}

    monkeypatch.setattr(direct_runner, "web_registry_for", lambda _config: registry)

    def fake_build_provider(spec, **kwargs):
        captured["spec"] = spec
        captured.update(kwargs)
        return provider

    monkeypatch.setattr(direct_runner, "build_provider", fake_build_provider)

    result = direct_runner.build_direct_provider(config, publisher)

    assert result is provider
    assert captured["spec"] == config.agent
    assert captured["web_sessions"] is registry


def test_primary_eval_disables_auxiliary_strong_models_without_mutating_config():
    from dataclasses import replace

    from evals.profiles import prepare_eval_config

    from fusion_cli.config.model_select import select_agent_spec
    from fusion_cli.core.types import ModelSpec

    original = replace(make_config(), teacher=ModelSpec("teacher", "strong/model"))
    prepared = prepare_eval_config(original, "local/small")
    assert prepared.agent.strict
    assert prepared.agent.fallback == ()
    assert select_agent_spec(prepared, "code") == prepared.agent
    assert prepared.judge == prepared.agent
    assert prepared.teacher is None
    assert prepared.vision == prepared.agent
    assert prepared.runtime.teacherless
    assert not prepared.runtime.lessons
    assert not prepared.runtime.teacher_lesson_sync
    assert not prepared.runtime.teacher_codex_fallback
    assert not prepared.runtime.escalate_on_gate_failure
    assert original.teacher.model == "strong/model"
    assert not original.agent.strict


def test_primary_eval_disables_explicit_automatic_web_fallback_without_mutating_config():
    from dataclasses import replace

    from evals.profiles import prepare_eval_config

    config = make_config()
    original = replace(config, runtime=replace(config.runtime, auto_web_fallback=True))

    prepared = prepare_eval_config(original, "local/small")

    assert prepared.runtime.auto_web_fallback is False
    assert original.runtime.auto_web_fallback is True


async def test_primary_eval_unavailable_model_cannot_pass_on_ready_web_fallback(
    monkeypatch, tmp_path
):
    from dataclasses import replace

    from evals import agent_runner
    from evals.agent_runner import FusionAgentRunner
    from evals.profiles import prepare_eval_config

    config = make_config()
    original = replace(config, runtime=replace(config.runtime, auto_web_fallback=True))
    prepared = prepare_eval_config(original, "selected/model")
    providers = []
    specs = []
    monkeypatch.setattr(agent_runner, "run_agent", _call_eval_model)
    monkeypatch.setattr(loop, "build_provider", _scripted_provider_factory(specs, providers))
    monkeypatch.setattr("fusion_cli.providers.fallback_plan._web_fallbacks", _ready_web_fallbacks)

    with pytest.raises(agent_runner.EvaluationUnavailableError, match="Sağlayıcı kullanılamıyor"):
        await FusionAgentRunner(prepared).run("bir görev", root=tmp_path)

    assert original.runtime.auto_web_fallback is True
    assert prepared.runtime.auto_web_fallback is False
    assert len(providers) == 1
    assert len(specs) == 1
    assert specs[0].model == "selected/model"
    assert specs[0].strict
    assert specs[0].fallback == ()
    assert providers[0].calls == 1


def test_report_preserves_strict_provenance_and_unknown_tokens():
    from evals.execution import ModelCallIdentity

    metadata = RunMetadata(
        suite="dev.yaml",
        requested_model="local/small",
        calls=(ModelCallIdentity("call1", "review", "local/small", None),),
        split="development",
        source_digest="a" * 64,
        prompt_digest="b" * 64,
        initial_workspace_digest="c" * 64,
        split_digest="d" * 64,
        scorer_digest="e" * 64,
        effective_config_digest="f" * 64,
        max_model_calls=12,
        timeout_s=480,
    )
    payload = report_to_dict(RunReport(results=(), metadata=metadata))
    assert report_from_dict(payload).metadata == metadata
    assert payload["metadata"]["calls"][0]["served_model"] is None
    assert payload["metadata"]["calls"][0]["prompt_tokens"] is None


def test_eval_cli_uses_strict_config_and_records_provenance_without_live_calls(
    monkeypatch, tmp_path
):
    from evals import cli
    from evals.executor import AgentRunObservation
    from evals.report import read_report

    original = make_config()
    seen = []

    class Runner:
        async def run(self, request, *, root, **kwargs):
            return AgentRunObservation("tamam", 0)

    def build(profile, config, *, source_split=None):
        assert source_split == "development"
        seen.append(config)
        return Runner()

    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "split: development\ntasks:\n- id: local\n  request: Yanıtla\n"
        "  criterion:\n    kind: keyword\n    keyword: tamam\n"
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr(cli, "load_config", lambda: original)
    monkeypatch.setattr(cli, "build_runner", build)
    assert (
        cli.main(
            [
                "run",
                str(suite),
                "--model",
                "local/small",
                "--out",
                str(output),
                "--workspace",
                str(tmp_path / "work"),
            ]
        )
        == 0
    )
    assert seen[0].agent.strict
    assert seen[0].teacher is None
    assert original.agent.model != "local/small"
    metadata = read_report(output).metadata
    assert metadata.requested_model == "local/small"
    assert metadata.split == "development"
    assert metadata.source_digest is not None
    assert metadata.prompt_digest is not None
    assert metadata.initial_workspace_digest is not None
    assert metadata.scorer_digest is not None
    assert metadata.effective_config_digest is not None
    assert metadata.environment_digest is None
    assert "environment" in metadata.unknowns


def test_effective_config_fingerprints_auxiliary_escape_controls():
    from dataclasses import replace

    from evals.effective_config import project_effective

    config = make_config()
    first = project_effective(config, config.agent, "eval")
    changed = replace(
        config,
        runtime=replace(
            config.runtime,
            teacher_codex_fallback=not config.runtime.teacher_codex_fallback,
        ),
    )
    assert project_effective(changed, changed.agent, "eval").digest != first.digest


def test_new_observation_metadata_preserves_existing_positional_fields():
    from evals.execution import TaskExecution
    from evals.executor import AgentRunObservation

    assert AgentRunObservation("tamam", 1, 2).retries == 2
    assert TaskExecution("local", 0).exit_code == 0


def test_prompt_digest_includes_exact_task_request_bytes(tmp_path):
    from dataclasses import replace

    from evals.loader import load_tasks
    from evals.profiles import build_run_metadata, prepare_eval_config

    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "tasks:\n- id: local\n  request: İlk istek\n"
        "  criterion:\n    kind: keyword\n    keyword: tamam\n"
    )
    tasks = load_tasks(suite)
    config = prepare_eval_config(make_config())
    options = {
        "suite": suite,
        "profile": EvalProfile.FUSION_FULL,
        "config": config,
        "repeat": 1,
        "seed": None,
        "calls": (),
    }
    first = build_run_metadata(tasks=tasks, **options)
    second = build_run_metadata(tasks=(replace(tasks[0], request="İkinci istek"),), **options)
    assert first.prompt_digest != second.prompt_digest


@pytest.mark.parametrize("profile", ["fusion-full", "fusion-minimal"])
def test_profile_cli_metadata_matches_actual_runner_config(monkeypatch, tmp_path, profile):
    from evals import cli
    from evals.effective_config import project_effective
    from evals.metrics import RunReport
    from evals.profiles import build_runner
    from evals.report import read_report

    config = make_config()
    observed = []

    def build(profile, resolved, *, source_split=None):
        runner = build_runner(profile, resolved, source_split=source_split)
        observed.append(runner._config)
        return runner

    async def no_provider(tasks, executor, *, repeat):
        return RunReport(results=())

    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "tasks:\n- id: t\n  request: Tamam\n  criterion:\n    kind: keyword\n    keyword: tamam\n"
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.setattr(cli, "build_runner", build)
    monkeypatch.setattr(cli, "_run_suite_and_close", no_provider)
    assert (
        cli.main(
            [
                "run",
                str(suite),
                "--profile",
                profile,
                "--out",
                str(output),
                "--workspace",
                str(tmp_path / "runs"),
            ]
        )
        == 0
    )
    actual = observed[0]
    metadata = read_report(output).metadata
    assert (
        metadata.effective_config_digest == project_effective(actual, actual.agent, "eval").digest
    )


@pytest.mark.parametrize(
    "wrapper",
    [
        "env PYTHONPATH=. python -m pytest -q",
        "command python -m pytest -q",
        "exec python -m pytest -q",
        "timeout 5 python -m pytest -q",
        "bash -c 'PYTHONPATH=. python -m pytest -q'",
        "sh -c 'PYTHONPATH=. python -m pytest -q'",
        "unknown-launcher python -m pytest -q",
    ],
)
async def test_acceptance_wrapper_grammar_is_unavailable_with_broken_or_fixed_product(
    tmp_path, wrapper
):
    from evals.executor import EXIT_VERIFICATION_UNAVAILABLE, AgentTaskExecutor
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    from .test_eval_executor import _FakeClock, _FakeRunner

    for value in (0, 7):
        task = EvalTask(
            id="wrapped",
            request="değeri düzelt",
            setup={
                "product.py": f"value = {value}\n",
                "test_behavior.py": (
                    "import product\n\ndef test_value():\n    assert product.value == 7\n"
                ),
            },
            criterion=SuccessCriterion(
                kind=CriterionKind.EXIT_CODE, expected_exit_code=0, command=wrapper
            ),
        )
        execution = await AgentTaskExecutor(
            _FakeRunner(files={"pytest.py": "pass\n"}),
            workspace_root=tmp_path,
            clock=_FakeClock(0.0, 1.0),
        ).run(task)
        assert execution.exit_code == EXIT_VERIFICATION_UNAVAILABLE


@pytest.mark.parametrize("command", ["true", "false", "sleep 0"])
async def test_known_non_python_acceptance_commands_remain_available(tmp_path, command):
    from evals.executor import AgentTaskExecutor
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    from .test_eval_executor import _FakeClock, _FakeRunner

    task = EvalTask(
        "local",
        "yerel kontrol",
        SuccessCriterion(
            kind=CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command=command,
        ),
    )
    execution = await AgentTaskExecutor(
        _FakeRunner(),
        workspace_root=tmp_path,
        clock=_FakeClock(0.0, 1.0),
    ).run(task)
    assert execution.exit_code == (1 if command == "false" else 0)


@pytest.mark.parametrize(
    "command",
    [
        "cd ../outside && python -m pytest -q",
        "cd /outside && python -m pytest -q",
        "cd $TARGET && python -m pytest -q",
        "cd sub* && python -m pytest -q",
        "cd sub || python -m pytest -q",
        "cd sub; python -m pytest -q",
    ],
)
async def test_ambiguous_or_outside_acceptance_cwd_is_unavailable(tmp_path, command):
    from evals.executor import EXIT_VERIFICATION_UNAVAILABLE, AgentTaskExecutor
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    from .test_eval_executor import _FakeClock, _FakeRunner

    task = EvalTask(
        "local",
        "kontrol et",
        SuccessCriterion(
            kind=CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command=command,
        ),
    )
    result = await AgentTaskExecutor(
        _FakeRunner(),
        workspace_root=tmp_path,
        clock=_FakeClock(0.0, 1.0),
    ).run(task)
    assert result.exit_code == EXIT_VERIFICATION_UNAVAILABLE


def test_nested_cd_chain_freezes_inputs_against_each_effective_seed_directory():
    from evals.acceptance_command import plan_acceptance

    plan = plan_acceptance(
        "cd sub && python -m pytest -c first.ini first.py && "
        "cd nested && python -m pytest -c second.ini second.py"
    )
    assert plan.unavailable_reason is None
    assert plan.frozen_inputs == frozenset(
        {
            "sub/first.ini",
            "sub/first.py",
            "sub/nested/second.ini",
            "sub/nested/second.py",
        }
    )


def test_iki_kol_ayni_strict_model_ve_toplam_yasam_dongusu_tavaniyla_hazirlanir(tmp_path):
    from evals.profiles import prepare_attempt_experiment

    config = make_config(
        memory_dir=tmp_path, runtime={"auto_web_fallback": True, "self_review": True}
    )
    candidates = prepare_attempt_experiment(
        config, arm="candidates", total_calls=6, first_slot_calls=2, task_id="gorev"
    )
    serial = prepare_attempt_experiment(
        config, arm="serial", total_calls=6, first_slot_calls=2, task_id="gorev"
    )
    assert candidates.config == serial.config
    assert candidates.experiment.requested_spec == serial.experiment.requested_spec
    assert candidates.experiment.total_calls == serial.experiment.total_calls == 6
    assert not candidates.config.runtime.auto_web_fallback
    assert not candidates.config.runtime.self_review
    assert config.runtime.auto_web_fallback and config.runtime.self_review


@pytest.mark.parametrize("profile", [EvalProfile.DIRECT, EvalProfile.FUSION_MINIMAL])
def test_aday_deneyi_tam_plan_yolunu_gerektirir(tmp_path, profile):
    from evals.profiles import build_runner, prepare_attempt_experiment

    prepared = prepare_attempt_experiment(
        make_config(memory_dir=tmp_path),
        arm="candidates",
        total_calls=4,
        first_slot_calls=2,
        task_id="is",
    )
    with pytest.raises(ValueError, match="tam Fusion"):
        build_runner(profile, prepared.config, experiment=prepared.experiment)


async def test_eval_runner_gercek_manifest_splitini_ders_baglamina_tasir(tmp_path, monkeypatch):
    from evals import agent_runner
    from evals.profiles import build_runner

    captured = []

    async def agent(request, deps):
        del request
        captured.append(deps.lesson_context.policy.source_split)
        return AgentOutcome("tamam", [], ok=True)

    monkeypatch.setattr(agent_runner, "run_agent", agent)
    runner = build_runner(
        EvalProfile.FUSION_FULL, make_config(memory_dir=tmp_path), source_split="validation"
    )
    await runner.run("iş", root=tmp_path)
    assert captured == ["validation"]


@pytest.mark.parametrize("arm", ["candidates", "serial"])
def test_public_cli_iki_gorev_iki_tekrarda_gercek_fabrika_ve_kotayi_korur(
    tmp_path, monkeypatch, arm
):
    from evals import cli
    from evals.report import read_report

    from tests.test_equal_budget_attempts import _provider_factory

    config = make_config(memory_dir=tmp_path / "memory")
    monkeypatch.setattr(cli, "load_config", lambda: config)
    identifiers = iter(f"call{index}" for index in range(100))
    monkeypatch.setattr(loop, "build_provider", _provider_factory([], identifiers))
    _public_experiment_agent(monkeypatch)
    seen = []
    original = cli.build_attempt_runner_factory

    def factory(*args, **kwargs):
        create = original(*args, **kwargs)

        def capture(task, repeat):
            runner = create(task, repeat)
            seen.append(runner._experiment)
            return runner

        return capture

    monkeypatch.setattr(cli, "build_attempt_runner_factory", factory)
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        "split: validation\ntasks:\n"
        + "".join(
            f"- id: {name}\n  request: Dosya yaz\n"
            "  criterion:\n    kind: keyword\n    keyword: tamam\n"
            for name in ("bir", "iki")
        )
    )
    output = tmp_path / "report.json"
    assert (
        cli.main(
            [
                "run",
                str(suite),
                "--out",
                str(output),
                "--workspace",
                str(tmp_path / "runs"),
                "--repeat",
                "2",
                "--attempt-arm",
                arm,
                "--attempt-total-calls",
                "4",
                "--attempt-first-slot-calls",
                "2",
            ]
        )
        == 0
    )
    report = read_report(output)
    _assert_public_arm(report, seen, arm, tmp_path / "runs")


def _public_experiment_agent(monkeypatch):
    from fusion_cli.core.evidence import ToolUse
    from fusion_cli.core.execution_plan import ExecutionPlan
    from fusion_cli.engines.agent import plan_runner
    from fusion_cli.engines.agent.plan_generation import PlanGeneration
    from fusion_cli.tools import build_registry
    from tests.test_attempts_wiring import _adim

    async def generate(task, deps, agent, limit, **kwargs):
        del deps, agent, limit, kwargs
        return PlanGeneration(ExecutionPlan("plan", task, (_adim("kod.py"),)), 0)

    async def agent(task, active, **kwargs):
        del kwargs
        for _ in range(2):
            await loop._call_model(
                [Message("user", task)],
                active,
                active.base_registry,
                state=loop._State(),
                execution=active.execution,
                offer_tools=False,
            )
        arguments = {"path": "kod.py", "content": "sağlam"}
        written = await build_registry().execute("write_file", arguments, active.tool_context)
        return AgentOutcome(
            "tamam",
            [],
            ok=written.ok,
            model_calls_made=2,
            tool_calls_made=1,
            mutating_tool_calls_made=1,
            tool_uses=(ToolUse("write_file", written.ok, True, arguments),),
        )

    monkeypatch.setattr(plan_runner, "generate_plan", generate)
    monkeypatch.setattr("evals.agent_runner.run_agent", agent)


def _assert_public_arm(report, seen, arm, root):
    from fusion_cli.core.events import AttemptExperimentFinished, ModelCallStarted
    from fusion_cli.observability.trace_store import TraceStore

    assert {(item.task_id, item.repeat) for item in seen} == {
        ("bir", 1),
        ("bir", 2),
        ("iki", 1),
        ("iki", 2),
    }
    assert all(item.total_calls == 4 for item in seen)
    assert report.metadata.arm == arm and report.metadata.max_model_calls == 4
    assert report.metadata.split == "validation"
    assert report.mean_model_calls <= 4
    assert report.task_success_rate == 1.0
    assert report.task_count == 2 and all(item.runs == 2 for item in report.results)
    if arm == "candidates":
        assert report.candidate_metrics.two_candidate_tasks == 4
        assert report.candidate_metrics.selected_at_2 == 1.0
    else:
        assert report.candidate_metrics.serial_at_c == 1.0

    finished = []
    for path in root.rglob("_transkript.jsonl"):
        events = TraceStore(path.parent).read(path.stem)
        completions = [event for event in events if isinstance(event, AttemptExperimentFinished)]
        calls = [event for event in events if isinstance(event, ModelCallStarted)]
        assert len(completions) == 1
        assert len(calls) <= completions[0].total_calls == 4
        assert completions[0].used_calls == len(calls)
        finished.extend(completions)
    assert {(item.task_id, item.repeat) for item in finished} == {
        ("bir", 1),
        ("bir", 2),
        ("iki", 1),
        ("iki", 2),
    }


@pytest.mark.parametrize(
    "options",
    [
        ["--attempt-arm", "candidates"],
        ["--attempt-total-calls", "4"],
        [
            "--attempt-arm",
            "serial",
            "--attempt-total-calls",
            "2",
            "--attempt-first-slot-calls",
            "2",
        ],
        [
            "--attempt-arm",
            "serial",
            "--attempt-total-calls",
            "4",
            "--attempt-first-slot-calls",
            "2",
            "--profile",
            "direct",
        ],
        [
            "--attempt-arm",
            "serial",
            "--attempt-total-calls",
            "4",
            "--attempt-first-slot-calls",
            "2",
            "--repeat",
            "0",
        ],
    ],
)
def test_public_cli_gecersiz_deneyi_config_ve_model_cagrisi_oncesi_reddeder(monkeypatch, options):
    from evals import cli

    def forbidden():
        raise AssertionError("Config veya model çağrısı açılmamalı")

    monkeypatch.setattr(cli, "load_config", forbidden)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["run", "olmayan-suite.yaml", *options])
    assert stopped.value.code == 2
