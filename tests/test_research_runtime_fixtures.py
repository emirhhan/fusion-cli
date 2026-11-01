"""Araştırma görevleri gerçek yürütücüye ve sabit sözleşmelere bağlanır."""

from __future__ import annotations

from pathlib import Path

import pytest
from evals import loader

ROOT = Path(__file__).resolve().parents[1]


def test_research_suites_have_all_32_tasks_and_typed_budgets():
    suites = [
        loader.load_tasks(ROOT / f"evals/suite/fusion-research-{split}.yaml")
        for split in ("dev", "validation", "blind")
    ]
    assert [len(tasks) for tasks in suites] == [16, 8, 8]
    assert len({task.id for tasks in suites for task in tasks}) == 32
    assert len({task.request for tasks in suites for task in tasks}) == 32
    for tasks in suites:
        for task in tasks:
            assert task.budget.max_model_calls in (12, 20)
            assert task.budget.timeout_s in (480, 720)


def test_suite_metadata_has_single_public_loader_and_rejects_unknown(tmp_path):
    assert hasattr(loader, "load_suite"), "Tiplenmiş split üstverisi yükleyicide eksik"
    path = tmp_path / "suite.yaml"
    path.write_text(
        "split: invented\n"
        "tasks: [{id: one, request: oku, criterion: {kind: workspace_unchanged}}]\n"
    )
    from fusion_cli.core.errors import EvalError

    with pytest.raises(EvalError, match="split"):
        loader.load_suite(path)


def test_runtime_scenario_runner_is_reachable_from_existing_factory():
    import inspect

    from evals.profiles import build_runner

    assert "task" in inspect.signature(build_runner).parameters


RUNTIME_IDS = (
    "T03",
    "T04",
    "T08",
    "T13",
    "T15",
    "T16",
    "T17",
    "T18",
    "T19",
    "T20",
    "T21",
    "T22",
    "T23",
    "T24",
    "T25",
    "T26",
    "T27",
    "T28",
)


@pytest.mark.parametrize("identity", RUNTIME_IDS)
@pytest.mark.parametrize("use_reference", (False, True))
async def test_runtime_human_reference_actual_runner_and_clean_acceptance(
    tmp_path, monkeypatch, identity, use_reference
):
    from evals.executor import AgentTaskExecutor

    from fusion_cli.core.clock import SystemClock
    from tests.test_research_support import scripted_runner

    tasks = [
        task
        for split in ("dev", "validation", "blind")
        for task in loader.load_tasks(ROOT / f"evals/suite/fusion-research-{split}.yaml")
    ]
    task = next(task for task in tasks if task.id == identity)
    runner = await scripted_runner(task, tmp_path, monkeypatch, use_reference)
    execution = await AgentTaskExecutor(
        runner, workspace_root=tmp_path / "workspaces", clock=SystemClock()
    ).run(task)
    stderr = (tmp_path / "workspaces" / identity / "_acceptance.stderr.txt").read_text()
    assert (execution.exit_code == 0) is use_reference, (
        identity,
        "\n".join(stderr.splitlines()[-8:]),
        execution.output_text,
        [
            (type(event).__name__, str(event)[:1000])
            for event in execution.trace_events
            if type(event).__name__ in {"ErrorOccurred", "ToolExecuted", "TurnBudgetExhausted"}
        ],
    )
    assert execution.model_calls > 0
    assert not (tmp_path / "workspaces" / identity / "reference.json").exists()
    assert not (tmp_path / "workspaces" / identity / "scenario.json").exists()
    if use_reference and identity == "T16":
        from evals.profiles import RunMetadata
        from evals.research_metadata import complete_metadata

        metadata = complete_metadata(RunMetadata(task_ids=(task.id,)), (execution,))
        assert metadata.environment_digest and "environment" not in metadata.unknowns
        assert metadata.corpus_digest is None and "corpus" in metadata.unknowns
    if use_reference:
        from tests.test_research_support import countercontrol

        await countercontrol(
            task, execution, tmp_path / "workspaces" / identity, tmp_path / "counter"
        )


@pytest.mark.parametrize("identity", RUNTIME_IDS)
async def test_runtime_seed_and_forged_receipt_fail_external_acceptance(tmp_path, identity):
    from evals.executor import AgentRunObservation, AgentTaskExecutor

    from fusion_cli.core.clock import SystemClock

    task = next(
        task
        for split in ("dev", "validation", "blind")
        for task in loader.load_tasks(ROOT / f"evals/suite/fusion-research-{split}.yaml")
        if task.id == identity
    )

    class SeedRunner:
        async def run(self, request, *, root, **kwargs):
            (root / "_runtime_receipt.json").write_text('{"scenario":"forged", "passed":true}')
            return AgentRunObservation("Tamamlandı", 0)

    execution = await AgentTaskExecutor(
        SeedRunner(), workspace_root=tmp_path, clock=SystemClock()
    ).run(task)
    assert execution.exit_code != 0


def test_real_corpus_admission_counts_and_unknown_metadata_roundtrip(tmp_path):
    import json

    from evals.metrics import RunReport
    from evals.profiles import RunMetadata
    from evals.report import report_from_dict, report_to_dict
    from evals.research_metadata import complete_metadata

    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            {
                "version": 2,
                "cases": [
                    {
                        "case_id": "synthetic-1",
                        "provider": "synthetic",
                        "transport": "offline",
                        "split": "diagnostic",
                        "provenance": "synthetic",
                        "output": "Yalnız açıklama",
                        "expected_calls": [],
                        "protocol": "v1",
                    }
                ],
            }
        )
    )
    metadata = RunMetadata(
        task_ids=("T01", "T25"), task_budgets=(("T01", 12, 480.0), ("T25", 20, 720.0))
    )
    result = complete_metadata(metadata, (), corpus=corpus)
    assert result.environment_digest is None and "environment" in result.unknowns
    assert result.corpus_digest and "corpus" not in result.unknowns
    assert dict(result.corpus_counts)["recorded_cases"] == 0
    assert dict(result.corpus_counts)["synthetic_cases"] == 1
    assert dict(result.corpus_counts)["usage_unknown_cases"] == 1
    assert report_from_dict(report_to_dict(RunReport((), metadata=result))).metadata == result
    corpus.write_text('{"version":1,"cases":[]}')
    with pytest.raises(ValueError, match="sürümü"):
        complete_metadata(metadata, (), corpus=corpus)


def test_relabelled_blind_task_is_rejected_before_parsing(tmp_path, monkeypatch):
    from fusion_cli.core.errors import EvalError

    path = tmp_path / "renamed.yaml"
    path.write_text("namespace: fusion_research\nsplit: development\ntasks: [{id: T04}]\n")

    def no_parse(item):
        raise AssertionError("Kör görev parse_task sınırına ulaşamaz")

    monkeypatch.setattr(loader, "parse_task", no_parse)
    with pytest.raises(EvalError, match="split"):
        loader.load_suite(path, allowed_splits=frozenset({"development"}))


async def test_task_budget_caps_all_provider_roles_before_next_invocation(tmp_path, monkeypatch):
    from dataclasses import replace

    from evals import agent_runner
    from evals.agent_runner import FusionAgentRunner
    from evals.tasks import TaskBudget

    from fusion_cli.core.types import CompletionRequest
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.providers.eventing import EventingProvider
    from tests.fakes import ScriptedProvider, make_config, model_result

    task = loader.load_tasks(ROOT / "evals/suite/fusion-research-dev.yaml")[0]
    task = replace(task, budget=TaskBudget(2, 5.0))
    provider = ScriptedProvider([model_result("yanıt")] * 4)

    async def actual_event_boundary(request, deps):
        for role in ("agent", "judge", "learning"):
            await EventingProvider(provider, publisher=deps.publisher, role=role).complete(
                CompletionRequest(messages=(), temperature=0, max_tokens=8, timeout_s=1)
            )
        return AgentOutcome("Bitti", [])

    monkeypatch.setattr(agent_runner, "run_agent", actual_event_boundary)
    config = make_config(memory_dir=tmp_path / "memory", source=tmp_path / "config.yaml")
    result = await FusionAgentRunner(config, task=task).run(task.request, root=tmp_path)
    assert provider.calls == result.model_calls == 2
    assert result.claimed_success is False


def test_partial_environment_coverage_stays_unknown():
    from evals.execution import TaskExecution
    from evals.profiles import RunMetadata
    from evals.research_metadata import complete_metadata

    from fusion_cli.core.evidence import EvidenceEnvironment

    first = TaskExecution(
        "first",
        environments=(EvidenceEnvironment("python", "/tmp", "runtime", "dependencies", "config"),),
    )
    report = complete_metadata(RunMetadata(), (first, TaskExecution("second")))
    assert report.environment_digest is None
    assert "environment" in report.unknowns


async def test_task_timeout_cancels_actual_runner_and_never_claims_success(tmp_path, monkeypatch):
    import asyncio
    from dataclasses import replace

    from evals import agent_runner
    from evals.tasks import TaskBudget

    from tests.fakes import make_config

    task = loader.load_tasks(ROOT / "evals/suite/fusion-research-dev.yaml")[0]
    task = replace(task, budget=TaskBudget(12, 0.001))
    cancelled = []
    actual_configs = []

    async def slow(request, deps):
        from evals.effective_config import project_effective

        actual_configs.append(project_effective(deps.config, deps.config.agent, "eval").digest)
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    monkeypatch.setattr(agent_runner, "run_agent", slow)
    config = make_config(memory_dir=tmp_path / "memory", source=tmp_path / "config.yaml")
    result = await agent_runner.FusionAgentRunner(config, task=task).run(
        task.request, root=tmp_path
    )
    assert cancelled == [True]
    assert actual_configs == [result.effective_config_digest]
    assert result.claimed_success is False and result.model_calls == 0


def test_public_cli_runs_runtime_task_and_records_budget_environment_corpus(tmp_path, monkeypatch):
    import asyncio
    import json

    import yaml
    from evals import cli

    from tests.fakes import make_config
    from tests.test_research_support import scripted_runner

    task = next(
        task
        for task in loader.load_tasks(ROOT / "evals/suite/fusion-research-validation.yaml")
        if task.id == "T03"
    )
    asyncio.run(scripted_runner(task, tmp_path, monkeypatch, True))
    config = make_config(
        memory_dir=tmp_path / "memory",
        source=tmp_path / "config.yaml",
        runtime={"self_review": False, "lessons": False, "auto_web_fallback": False},
    )
    monkeypatch.setattr(cli, "load_config", lambda: config)
    suite = tmp_path / "suite.yaml"
    suite.write_text(
        yaml.safe_dump({"split": "validation", "tasks": [loader.task_to_mapping(task)]})
    )
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps({"version": 2, "cases": []}))
    report = tmp_path / "report.json"
    assert (
        cli.main(
            [
                "run",
                str(suite),
                "--out",
                str(report),
                "--workspace",
                str(tmp_path / "work"),
                "--corpus",
                str(corpus),
            ]
        )
        == 0
    )
    observed = json.loads(report.read_text())
    assert observed["results"][0]["success"] is True
    metadata = observed["metadata"]
    assert metadata["task_budgets"] == [["T03", 12, 480.0]]
    assert metadata["environment_digest"] and metadata["corpus_digest"]
    assert metadata["model_calls_total"] > 0
    assert metadata["task_config_digests"][0][0] == "T03"
    assert len(metadata["task_config_digests"][0][1]) == 64
    assert "task_effective_config" not in metadata["unknowns"]
    from evals.report import report_from_dict

    assert report_from_dict(observed).metadata.task_config_digests == tuple(
        tuple(item) for item in metadata["task_config_digests"]
    )
    assert dict(metadata["corpus_counts"])["recorded_cases"] == 0
    assert "live_baseline" in metadata["unknowns"]
