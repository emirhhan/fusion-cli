"""İstem optimizasyonunun gerçek görev/bütçe bağını doğrula."""

from __future__ import annotations

import sys
import types

import pytest
from evals.executor import AgentRunObservation
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion, TaskBudget
from prompt_opt.targets import PromptTarget

from fusion_cli.cli import prompt_opt_commands
from tests.test_prompt_opt_research import _local_config, _ScriptedRunner
from tests.test_prompt_opt_research import research_cli as research_cli


async def test_cli_executor_fabrikasi_gercek_gorev_butcesini_kosucuya_baglar(tmp_path, monkeypatch):
    from evals.agent_runner import FusionAgentRunner

    module = types.ModuleType("f31_budget_prompt")
    module.TEXT = "temel"
    monkeypatch.setitem(sys.modules, module.__name__, module)
    target = PromptTarget("system", tmp_path / "prompt.md", module.__name__, "TEXT")
    task = EvalTask(
        "budget-task",
        "istek",
        SuccessCriterion(CriterionKind.KEYWORD, keyword="tamam"),
        budget=TaskBudget(2, 3.0),
    )
    seen = []

    async def scripted_run(self, request, *, root, strict_approval=False, transcript=None):
        seen.append((self._config, self._task))
        return AgentRunObservation("tamam", 0)

    monkeypatch.setattr(FusionAgentRunner, "run", scripted_run)
    monkeypatch.setattr(prompt_opt_commands.tempfile, "tempdir", str(tmp_path))
    factory = prompt_opt_commands._executor_factory(_local_config(tmp_path), target)
    execution = await factory("aday").run(task)
    assert execution.output_text == "tamam"
    assert seen[0][1] == task
    assert seen[0][0].runtime.agent_max_steps == task.budget.max_model_calls == 2
    assert seen[0][0].runtime.teacherless
    assert module.TEXT == "temel"


@pytest.mark.parametrize("stage", ["d", "v"])
def test_tekrarlarin_gercek_cagri_ve_usd_artisi_reddedilir(research_cli, monkeypatch, stage):
    from dataclasses import replace

    from evals.execution import ModelCallIdentity
    from prompt_opt.proposals import ProposalStore
    from typer.testing import CliRunner

    from fusion_cli.cli.app import app

    original = _ScriptedRunner.run

    async def varied(self, request, *, root, **kwargs):
        observation = await original(self, request, root=root, **kwargs)
        sample = int(root.name.removeprefix("run-"))
        count = 2 if self.base != self.module.TEXT and request[0] == stage else sample
        return replace(
            observation,
            model_calls=count,
            calls=tuple(
                ModelCallIdentity(
                    str(index), "agent", "scripted/local", "scripted/local", cost_usd=1.0
                )
                for index in range(count)
            ),
        )

    monkeypatch.setattr(_ScriptedRunner, "run", varied)
    paths, *_ = research_cli
    result = CliRunner().invoke(
        app,
        [
            "prompt-opt",
            "calistir",
            "--kume",
            "dev",
            "--ayri",
            "val",
            "--aday",
            "1",
            "--tekrar",
            "2",
        ],
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert ProposalStore(paths.proposals).list() == ()


@pytest.mark.parametrize("stage", ["d", "v"])
def test_bilinen_served_model_degisiminde_oneri_saklanmaz(research_cli, monkeypatch, stage):
    from dataclasses import replace

    from prompt_opt.proposals import ProposalStore

    from tests.test_prompt_opt_research import _invoke_research

    original = _ScriptedRunner.run

    async def drift(self, request, **kwargs):
        observation = await original(self, request, **kwargs)
        actual = (
            "served/different"
            if self.base != self.module.TEXT and request[0] == stage
            else "served/base"
        )
        return replace(
            observation,
            calls=tuple(replace(call, served_model=actual) for call in observation.calls),
        )

    monkeypatch.setattr(_ScriptedRunner, "run", drift)
    paths, *_ = research_cli
    result = _invoke_research()
    assert result.exit_code == 0, (result.output, result.exception)
    assert ProposalStore(paths.proposals).list() == ()


async def _failed_edit_events(tmp_path, monkeypatch):
    from fusion_cli.core.events import ToolExecuted, ToolOutcome
    from fusion_cli.engines.agent.loop import run_agent
    from tests.fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from tests.test_agent_loop import TAM_CEVAP, _deps, _kur

    sink = RecordingSink()
    (tmp_path / "a.txt").write_text("abc", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        tool_call("edit_file", path="a.txt", old="absent", new="replacement")
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    await run_agent(
        "a.txt dosyasını düzenle",
        _deps(
            tmp_path,
            sink,
            memory_dir=tmp_path / "memory",
            home=tmp_path,
            runtime={
                "agent_max_steps": 2,
                "reflexion": False,
                "self_review": False,
                "teacherless": True,
            },
        ),
    )
    failures = tuple(
        event
        for event in sink.events
        if isinstance(event, ToolExecuted)
        and event.name == "edit_file"
        and event.outcome is ToolOutcome.FAILED
    )
    assert failures
    assert all(event.diff is None and event.workspace == "" for event in failures)
    return failures


@pytest.mark.parametrize("stage", ["d", "v"])
def test_gercek_run_agent_edit_hatasi_her_iki_secim_kapisinda_reddedilir(
    research_cli, tmp_path, monkeypatch, stage
):
    import asyncio
    from dataclasses import replace

    from prompt_opt.proposals import ProposalStore

    from tests.test_prompt_opt_research import _invoke_research

    failures = asyncio.run(_failed_edit_events(tmp_path, monkeypatch))
    original = _ScriptedRunner.run

    async def with_failure(self, request, **kwargs):
        observation = await original(self, request, **kwargs)
        if self.base != self.module.TEXT and request[0] == stage:
            return replace(observation, trace_events=failures)
        return observation

    monkeypatch.setattr(_ScriptedRunner, "run", with_failure)
    paths, *_ = research_cli
    result = _invoke_research()
    assert result.exit_code == 0, (result.output, result.exception)
    assert ProposalStore(paths.proposals).list() == ()


async def test_gercek_edit_hatasi_ureticisi_typed_mutating_kaniti_tasir(tmp_path, monkeypatch):
    failures = await _failed_edit_events(tmp_path, monkeypatch)
    assert all(getattr(event, "mutating", None) is True for event in failures)


def test_tekrarlarin_kayipsiz_cagri_ve_usd_toplami_manifestte_korunur(research_cli, monkeypatch):
    from dataclasses import replace

    from evals.execution import ModelCallIdentity
    from prompt_opt.proposals import ProposalStore
    from typer.testing import CliRunner

    from fusion_cli.cli.app import app

    original = _ScriptedRunner.run

    async def varied(self, request, *, root, **kwargs):
        observation = await original(self, request, root=root, **kwargs)
        count = int(root.name.removeprefix("run-"))
        return replace(
            observation,
            model_calls=count,
            calls=tuple(
                ModelCallIdentity(
                    str(index), "agent", "scripted/local", "scripted/local", cost_usd=1.0
                )
                for index in range(count)
            ),
        )

    monkeypatch.setattr(_ScriptedRunner, "run", varied)
    paths, *_ = research_cli
    result = CliRunner().invoke(
        app,
        [
            "prompt-opt",
            "calistir",
            "--kume",
            "dev",
            "--ayri",
            "val",
            "--aday",
            "1",
            "--tekrar",
            "2",
        ],
    )
    assert result.exit_code == 0, (result.output, result.exception)
    (proposal,) = ProposalStore(paths.proposals).list()
    assert all(
        item.measurement.model_calls == item.metadata.model_calls_total == 9
        for item in proposal.run_manifest
    )
    assert all(item.measurement.cost_usd == 9.0 for item in proposal.run_manifest)
    assert all("cost_usd" not in item.measurement.unknowns for item in proposal.run_manifest)


def test_bilinmeyen_served_model_kimligi_unknown_kalir_ve_yasaklanmaz(research_cli, monkeypatch):
    from dataclasses import replace

    from prompt_opt.proposals import ProposalStore

    from tests.test_prompt_opt_research import _invoke_research

    original = _ScriptedRunner.run

    async def unknown(self, request, **kwargs):
        observation = await original(self, request, **kwargs)
        return replace(
            observation, calls=tuple(replace(call, served_model=None) for call in observation.calls)
        )

    monkeypatch.setattr(_ScriptedRunner, "run", unknown)
    paths, *_ = research_cli
    result = _invoke_research()
    assert result.exit_code == 0, (result.output, result.exception)
    (proposal,) = ProposalStore(paths.proposals).list()
    assert all("served_model" in item.measurement.unknowns for item in proposal.run_manifest)
    assert "usage_unknown" in proposal.proposal_generation_role


@pytest.mark.parametrize("trace_kind", ["missing-field", "non-tool-trace"])
def test_mutasyon_bilgisi_eksik_olay_olculmus_sifir_degil_unknown(trace_kind):
    from evals.metrics import RunReport, TaskResult
    from prompt_opt.research_evidence import measure

    from fusion_cli.core.events import Channel, ToolExecuted, ToolOutcome, TurnAnswered

    event = (
        ToolExecuted(name="edit_file", args={}, outcome=ToolOutcome.FAILED, output="hata")
        if trace_kind == "missing-field"
        else TurnAnswered(channel=Channel.MAIN, text="tamam")
    )
    measurement = measure(
        RunReport((TaskResult("a", False, False, 0, 1, 0.0, trace_events=(event,)),))
    )
    assert measurement.failed_mutations is None
    assert "failed_mutations" in measurement.unknowns


def test_eski_tekrar_ortalamasindan_toplam_uydurulmaz():
    from evals.metrics import RunReport, TaskResult
    from prompt_opt.research_evidence import measure

    report = RunReport((TaskResult("a", False, False, 0, 2, 0.0, runs=2),))
    measurement = measure(report)
    assert measurement.model_calls is None
    assert "model_calls" in measurement.unknowns


def test_ab_ba_birlesimi_kayipsiz_cagri_toplamlarini_toplar():
    from evals.execution import ModelCallIdentity
    from evals.metrics import RunReport, TaskResult
    from evals.profiles import RunMetadata
    from prompt_opt.research_comparison import _combine
    from prompt_opt.research_evidence import measure

    calls = tuple(
        ModelCallIdentity(str(index), "agent", "m", "m", cost_usd=1.0) for index in range(3)
    )
    report = RunReport(
        (TaskResult("a", True, True, 0, 2, 0.0, runs=2, passes=2),),
        metadata=RunMetadata(calls=calls, model_calls_total=3, repeat=2),
    )
    measured = measure(_combine(report, report))
    assert measured.model_calls == 6
    assert measured.cost_usd == 6.0
