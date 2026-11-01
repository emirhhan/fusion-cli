"""İncelemedeki dört karşı örnek gerçek kabul ve public API sınırlarında reddedilir."""

from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path

import pytest
from evals.execution import TaskExecution
from evals.executor import AgentTaskExecutor
from evals.kabul.run_manifest import FreezeEvidence, FreezeStatus, freeze_run
from evals.loader import load_suite, load_tasks
from evals.profiles import RunMetadata
from evals.report import report_from_dict
from evals.research_metadata import complete_metadata

from fusion_cli.core.clock import SystemClock
from fusion_cli.core.evidence import EvidenceEnvironment
from tests import test_research_support as support
from tests.fakes import ScriptedProvider, model_result, tool_call
from tests.test_run_manifest import area, engine

ROOT = Path(__file__).parents[1]
DIGEST = "a" * 64


@pytest.mark.parametrize("identity", ("T13", "T15", "T24"))
@pytest.mark.parametrize("unrelated", (False, True))
async def test_reproduction_requires_relevant_before_after_evidence(
    tmp_path, monkeypatch, identity, unrelated
):
    task = next(
        task
        for split in ("dev", "validation", "blind")
        for task in load_tasks(ROOT / f"evals/suite/fusion-research-{split}.yaml")
        if task.id == identity
    )
    if unrelated:
        monkeypatch.setattr(support, "reference_provider", unrelated_provider)
    runner = await support.scripted_runner(task, tmp_path, monkeypatch, True)
    result = await AgentTaskExecutor(
        runner, workspace_root=tmp_path / "work", clock=SystemClock()
    ).run(task)
    assert (result.exit_code == 0) is not unrelated
    assert result.model_calls > 0


async def unrelated_provider(fixture):
    actions = json.loads((fixture / "reference.json").read_text())
    results = []
    shell_count = 0
    for index, action in enumerate(actions):
        arguments = action["arguments"]
        if action["name"] == "run_shell":
            arguments = {
                "command": 'python -B -c "assert ' + ("False" if shell_count == 0 else "True") + '"'
            }
            shell_count += 1
        results.append(
            model_result(
                tool_calls=(
                    replace(tool_call(action["name"], **arguments), id=f"unrelated-{index}"),
                )
            )
        )
    results.extend(model_result((fixture / "response.txt").read_text()) for _ in range(4))
    return ScriptedProvider(results)


def metadata():
    return RunMetadata(
        task_ids=("T01", "T25"),
        task_budgets=(("T01", 12, 480.0), ("T25", 20, 720.0)),
        requested_model="local/test",
        split="development",
        source_digest=DIGEST,
        prompt_digest=DIGEST,
        initial_workspace_digest=DIGEST,
        split_digest=DIGEST,
        scorer_digest=DIGEST,
        effective_config_digest=DIGEST,
        corpus_digest=DIGEST,
    )


def execution(identity):
    return TaskExecution(
        identity,
        environments=(EvidenceEnvironment("python", "/tmp", "runtime", "deps", "config"),),
        effective_config_digest=DIGEST,
        sample_index=1,
    )


def frozen(evaluation):
    return freeze_run(
        area(),
        run_id="html_oyun.curA",
        variant="A",
        engine=engine(),
        brief=b"A",
        final_brief=True,
        viewports=((1280, 800),),
        assets=(),
        evidence=FreezeEvidence(**{field.name: DIGEST for field in fields(FreezeEvidence)}),
        evaluation=evaluation,
    )


@pytest.mark.parametrize("identities", (("T01",), ("T01", "foreign"), ("T01", "T01")))
def test_incomplete_foreign_duplicate_execution_never_completes(identities):
    result = complete_metadata(metadata(), tuple(execution(identity) for identity in identities))
    assert result.environment_digest is None
    assert "task_effective_config" in result.unknowns
    assert frozen(replace(result, corpus_digest=DIGEST)).status is FreezeStatus.UNVERIFIED


@pytest.mark.parametrize("configs", ((), (("T01", DIGEST),), (("T01", "bad"), ("T25", DIGEST))))
def test_freeze_requires_actual_complete_valid_task_config(configs):
    value = replace(metadata(), environment_digest=DIGEST, task_config_digests=configs)
    assert frozen(value).status is FreezeStatus.UNVERIFIED


def test_generic_short_id_does_not_enter_research_namespace(tmp_path):
    path = tmp_path / "unrelated.yaml"
    path.write_text(
        "split: development\ntasks: [{id: T04, request: ilgisiz, "
        "criterion: {kind: workspace_unchanged}}]\n"
    )
    assert load_suite(path, allowed_splits=frozenset({"development"})).tasks[0].id == "T04"


@pytest.mark.parametrize(
    "raw",
    (
        ("T01", True, True),
        ("T01", "12", 10),
        ("T01", 12, "10"),
        ("T01", 0, 10),
        ("T01", 12, float("nan")),
        ("T01", 12, float("inf")),
        ("T01", 12),
        ("T01", 12, 10, 99),
    ),
)
def test_report_rejects_invalid_raw_budget(raw):
    with pytest.raises(ValueError, match="bütçe"):
        report_from_dict({"results": [], "metadata": {"task_budgets": [raw]}})


@pytest.mark.parametrize("repeat", (1, 2))
def test_complete_real_task_repeat_coverage_can_freeze_and_roundtrip(repeat):
    executions = tuple(
        replace(execution(identity), sample_index=index)
        for identity in metadata().task_ids
        for index in range(1, repeat + 1)
    )
    result = complete_metadata(replace(metadata(), repeat=repeat), executions)
    result = replace(result, corpus_digest=DIGEST)
    assert result.environment_digest and "task_effective_config" not in result.unknowns
    assert frozen(result).status is FreezeStatus.FROZEN
    from evals.metrics import RunReport
    from evals.report import report_to_dict

    assert report_from_dict(report_to_dict(RunReport((), metadata=result))).metadata == result
    duplicate = (*executions[:-1], executions[0])
    incomplete = complete_metadata(replace(metadata(), repeat=repeat), duplicate)
    assert incomplete.environment_digest is None
    assert frozen(replace(incomplete, corpus_digest=DIGEST)).status is FreezeStatus.UNVERIFIED


@pytest.mark.parametrize("missing", ("index", "config", "shape", "explicit_unknown"))
def test_actual_dependency_config_or_sample_identity_cannot_be_invented(missing):
    values = (execution("T01"), execution("T25"))
    if missing == "index":
        values = (replace(values[0], sample_index=None), values[1])
    elif missing == "config":
        values = (replace(values[0], effective_config_digest=None), values[1])
    elif missing == "shape":
        values = (replace(values[0], effective_config_digest="invalid"), values[1])
    result = complete_metadata(metadata(), values)
    if missing == "explicit_unknown":
        result = replace(result, unknowns=(*result.unknowns, "task_effective_config"))
    assert frozen(replace(result, corpus_digest=DIGEST)).status is FreezeStatus.UNVERIFIED


@pytest.mark.parametrize("namespace", (True, False))
def test_moved_relabelled_renamed_research_blind_stays_blocked(tmp_path, monkeypatch, namespace):
    import yaml
    from evals import loader

    from fusion_cli.core.errors import EvalError

    task = loader.task_to_mapping(load_tasks(ROOT / "evals/suite/fusion-research-blind.yaml")[0])
    task["id"] = "renamed"
    raw = {"split": "development", "tasks": [task]}
    if namespace:
        raw["namespace"] = "fusion_research"
    path = tmp_path / "moved.yaml"
    path.write_text(yaml.safe_dump(raw))
    monkeypatch.setattr(loader, "parse_task", lambda item: pytest.fail("Kör görev çözümlenemez"))
    with pytest.raises(EvalError, match="split"):
        load_suite(path, allowed_splits=frozenset({"development"}))


def test_legacy_missing_budget_and_config_stay_unknown():
    result = report_from_dict({"results": [], "metadata": {}}).metadata
    assert result.task_budgets == result.task_config_digests == result.execution_ids == ()
    assert frozen(result).status is FreezeStatus.UNVERIFIED


async def test_actual_executor_carries_explicit_repeat_identity(tmp_path):
    from evals.executor import AgentRunObservation
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    class Runner:
        async def run(self, request, **kwargs):
            return AgentRunObservation("tamam", 1, effective_config_digest=DIGEST)

    task = EvalTask("generic", "iş", SuccessCriterion(CriterionKind.KEYWORD, keyword="tamam"))
    executor = AgentTaskExecutor(Runner(), workspace_root=tmp_path, clock=SystemClock())
    assert (await executor.run(task)).sample_index == 1
    assert (await executor.run_sample(task, sample_index=2)).sample_index == 2


@pytest.mark.parametrize("marker", ("namespace", "runtime_scenario"))
def test_research_identity_cannot_be_overridden_by_another_fixture_command(tmp_path, marker):
    import yaml

    from fusion_cli.core.errors import EvalError

    task = {
        "id": "T04",
        "request": "alıntı",
        "criterion": {
            "kind": "exit_code",
            "expected_exit_code": 0,
            "command": "python -m evals.fixtures.fusion_research.acceptance T01",
        },
    }
    raw = {"split": "development", "tasks": [task]}
    if marker == "namespace":
        raw["namespace"] = "fusion_research"
    else:
        task["runtime_scenario"] = "quoted_action"
    path = tmp_path / "renamed.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(EvalError, match="split"):
        load_suite(path, allowed_splits=frozenset({"development"}))


@pytest.mark.parametrize(
    "identity,index,digest",
    (
        ("foreign", None, None),
        ("T01", None, None),
        ("T01", None, DIGEST),
        ("foreign", 1, DIGEST),
        ("T01", 1, DIGEST),
        ("foreign", 1, None),
    ),
)
def test_extra_execution_never_disappears_from_integrity(identity, index, digest):
    from evals.execution import ModelCallIdentity

    valid = (replace(execution("T01"), model_calls=2), replace(execution("T25"), model_calls=3))
    extra = replace(
        execution(identity),
        sample_index=index,
        effective_config_digest=digest,
        model_calls=7,
        calls=(ModelCallIdentity("extra", "agent", "local/test", "local/test"),),
    )
    result = complete_metadata(metadata(), (*valid, extra))
    assert result.environment_digest is None
    assert "environment" in result.unknowns and "task_effective_config" in result.unknowns
    assert result.model_calls_total == 12
    assert [call.call_id for call in result.calls] == ["extra"]
    assert frozen(replace(result, corpus_digest=DIGEST)).status is FreezeStatus.UNVERIFIED


def test_unknown_config_also_keeps_environment_integrity_unknown():
    values = (execution("T01"), replace(execution("T25"), effective_config_digest=None))
    result = complete_metadata(metadata(), values)
    assert result.environment_digest is None
    assert "task_effective_config" in result.unknowns
    assert frozen(replace(result, corpus_digest=DIGEST)).status is FreezeStatus.UNVERIFIED


@pytest.mark.parametrize("operator", (" && ", " || ", " ; ", "&&", ";"))
@pytest.mark.parametrize("last", ("T02", "T04"))
def test_all_chained_fixture_references_are_guarded_before_parse(
    tmp_path, monkeypatch, operator, last
):
    import yaml
    from evals import loader

    from fusion_cli.core.errors import EvalError

    module = "evals.fixtures.fusion_research.acceptance"
    command = operator.join(f"python -m {module} {identity}" for identity in ("T01", "T02", last))
    raw = {
        "split": "development",
        "tasks": [
            {
                "id": "renamed",
                "request": "kontrol",
                "criterion": {
                    "kind": "exit_code",
                    "expected_exit_code": 0,
                    "command": command,
                },
            }
        ],
    }
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(raw))
    if last == "T04":
        monkeypatch.setattr(
            loader, "parse_task", lambda item: pytest.fail("Kör görev çözümlenemez")
        )
        with pytest.raises(EvalError, match="split"):
            load_suite(path, allowed_splits=frozenset({"development"}))
    else:
        assert load_suite(path, allowed_splits=frozenset({"development"})).tasks[0].id == "renamed"
