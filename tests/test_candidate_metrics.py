"""Aday başarısı gerçek kabulden ve tipli olaydan hesaplanır."""

from __future__ import annotations

from evals.candidate_metrics import reduce_candidate_metrics

from fusion_cli.core.events import (
    AttemptExperimentFinished,
    CandidateFinished,
    CandidatePromoted,
    CandidateSelected,
    CandidateStarted,
)
from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind


def _criterion(name: str, status: EvidenceStatus) -> CriterionEvidence:
    return CriterionEvidence(name, VerificationCheckKind.COMMAND, status, "kanıt")


def _started(name: str, ordinal: int) -> CandidateStarted:
    return CandidateStarted(
        "plan", "step", ordinal, "yerel/test", None, 2, "candidates", "task", 1, candidate_id=name
    )


def _finished(name: str, ordinal: int, statuses: tuple[EvidenceStatus, ...]) -> CandidateFinished:
    return CandidateFinished(
        "plan",
        "step",
        ordinal,
        True,
        tuple(_criterion(str(index), status) for index, status in enumerate(statuses)),
        tuple(str(index) for index in range(len(statuses))),
        (),
        candidate_id=name,
        scope="task",
    )


def _task_end() -> AttemptExperimentFinished:
    return AttemptExperimentFinished(
        "task", 1, "candidates", True, (_criterion("0", EvidenceStatus.PASSED),), ("0",), 0, 4
    )


def test_secilebilir_aday_butun_kosullar_gecmeden_basari_degil() -> None:
    events = [
        _started("a", 1),
        _finished("a", 1, (EvidenceStatus.PASSED, EvidenceStatus.UNVERIFIED)),
        _started("b", 2),
        _finished("b", 2, (EvidenceStatus.PASSED, EvidenceStatus.PASSED)),
        CandidateSelected("plan", "step", "a"),
        CandidatePromoted(
            "plan",
            "step",
            True,
            (_criterion("0", EvidenceStatus.PASSED),),
            ("0", "1"),
            candidate_id="a",
        ),
    ]
    metrics = reduce_candidate_metrics([*events, _task_end()])
    assert metrics.pass_at_1 == 0.0
    assert metrics.oracle_at_2 == 1.0
    assert metrics.selected_at_2 == 0.0
    assert metrics.two_candidate_tasks == 1


def test_baslamayan_ikinci_aday_iki_aday_kohortuna_girmez() -> None:
    metrics = reduce_candidate_metrics(
        [_started("a", 1), _finished("a", 1, (EvidenceStatus.PASSED,)), _task_end()]
    )
    assert metrics.pass_at_1 == 1.0
    assert metrics.oracle_at_2 is None
    assert metrics.two_candidate_tasks == 0


def test_olay_raporu_aday_metriklerini_jsonda_korur() -> None:
    from evals.metrics import RunReport
    from evals.report import report_from_dict, report_to_dict

    events = [
        _started("a", 1),
        _finished("a", 1, (EvidenceStatus.PASSED,)),
        _started("b", 2),
        _finished("b", 2, (EvidenceStatus.UNVERIFIED,)),
    ]
    report = RunReport.from_events((), [*events, _task_end()])
    payload = report_to_dict(report)
    assert payload["candidate_metrics"]["oracle_at_2"] == 1.0
    assert report_from_dict(payload).candidate_metrics == report.candidate_metrics


def test_lifecycle_dedupe_acik_cagri_ve_gercek_kimlik_ayri_tutulur() -> None:
    from fusion_cli.core.events import ModelCallAbandoned, ModelCallFinished, ModelCallStarted
    from fusion_cli.core.types import ModelResult

    finished = ModelCallFinished(
        "agent",
        ModelResult("agent", "yerel/test", "", 1, True),
        call_id="call1",
        requested_model="yerel/test",
    )
    metrics = reduce_candidate_metrics(
        [
            ModelCallStarted("agent", "yerel/test", call_id="call1"),
            finished,
            finished,
            ModelCallAbandoned("agent", "yerel/test", call_id="call1"),
            ModelCallStarted("agent", "yerel/test", call_id="call2"),
            ModelCallStarted("agent", "yerel/test", call_id="call3"),
            ModelCallAbandoned("agent", "yerel/test", call_id="call3"),
        ]
    )
    assert metrics.lifecycle_calls == 3
    assert metrics.open_calls == 1
    assert metrics.abandoned_calls == 1
    assert metrics.unknown_served_calls == 1


def test_terfi_ve_geri_alma_cakismasi_ayri_sayilir() -> None:
    from fusion_cli.core.events import WorkspaceConflictDetected

    metrics = reduce_candidate_metrics(
        [
            WorkspaceConflictDetected("plan", "step", "source-promotion", 1),
            WorkspaceConflictDetected("plan", "step", "rollback", 2),
        ]
    )
    assert metrics.source_conflicts == 1
    assert metrics.rollback_conflicts == 2


def test_farkli_gozlenen_model_ana_kohort_oranlarini_gecersiz_kilar() -> None:
    from fusion_cli.core.events import ModelCallFinished
    from fusion_cli.core.types import ModelResult

    metrics = reduce_candidate_metrics(
        [
            _started("a", 1),
            _finished("a", 1, (EvidenceStatus.PASSED,)),
            ModelCallFinished(
                "agent",
                ModelResult("agent", "yerel/test", "", 1, True, served_by="baska/model"),
                call_id="call",
                requested_model="yerel/test",
                candidate_id="a",
            ),
        ]
    )
    assert metrics.pass_at_1 is None
    assert metrics.mismatched_model_calls == 1


def test_ayni_planin_sirali_tekrarlari_birbirini_ezmez() -> None:
    first = [
        _started("a", 1),
        _finished("a", 1, (EvidenceStatus.PASSED,)),
        _started("b", 2),
        _finished("b", 2, (EvidenceStatus.UNVERIFIED,)),
    ]
    second = [
        _started("a", 1),
        _finished("a", 1, (EvidenceStatus.UNVERIFIED,)),
        _started("b", 2),
        _finished("b", 2, (EvidenceStatus.UNVERIFIED,)),
    ]
    metrics = reduce_candidate_metrics([*first, _task_end(), *second, _task_end()])
    assert metrics.two_candidate_tasks == metrics.candidate_tasks == 2
    assert metrics.pass_at_1 == metrics.oracle_at_2 == 0.5


def test_ayni_kosul_iki_adimda_varsa_biri_belirsizken_gecmez() -> None:
    from dataclasses import replace

    from evals.candidate_metrics import accepted

    good = replace(_criterion("kosul", EvidenceStatus.PASSED), step_id="bir")
    unknown = replace(_criterion("kosul", EvidenceStatus.UNVERIFIED), step_id="iki")
    assert not accepted(True, (unknown, good), ("kosul",))


async def test_gercek_eval_koprusu_olaylari_yurutucu_ve_json_raporuna_tasir(
    tmp_path, monkeypatch
) -> None:
    from evals import agent_runner
    from evals.agent_runner import FusionAgentRunner
    from evals.executor import AgentTaskExecutor
    from evals.metrics import RunReport, score_task
    from evals.report import report_to_dict
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    from fusion_cli.engines.agent.loop import AgentOutcome
    from tests.fakes import make_config

    events = [
        _started("a", 1),
        _finished("a", 1, (EvidenceStatus.PASSED,)),
        _started("b", 2),
        _finished("b", 2, (EvidenceStatus.UNVERIFIED,)),
    ]

    async def agent(request, deps):
        del request
        for event in [*events, _task_end()]:
            deps.publisher.publish(event)
        return AgentOutcome("tamam", [], ok=True)

    class Clock:
        def monotonic(self):
            return 0.0

    monkeypatch.setattr(agent_runner, "run_agent", agent)
    task = EvalTask("is", "düzenle", SuccessCriterion(CriterionKind.WORKSPACE_UNCHANGED))
    runner = FusionAgentRunner(make_config(memory_dir=tmp_path / "memory"))
    executor = AgentTaskExecutor(runner, workspace_root=tmp_path / "workspaces", clock=Clock())
    execution = await executor.run(task)
    assert all(event in execution.trace_events for event in events)
    report = RunReport((score_task(task, execution),))
    assert report_to_dict(report)["candidate_metrics"]["oracle_at_2"] == 1.0


async def test_deney_eval_ham_typed_trace_tekrar_ayni_metrigi_uretir(tmp_path, monkeypatch) -> None:
    from evals.agent_runner import FusionAgentRunner
    from evals.profiles import prepare_attempt_experiment

    from fusion_cli.engines.agent import plan_runner
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.observability.trace_store import TraceStore
    from tests.fakes import make_config

    events = [
        _started("a", 1),
        _finished("a", 1, (EvidenceStatus.PASSED,)),
        _started("b", 2),
        _finished("b", 2, (EvidenceStatus.UNVERIFIED,)),
    ]

    async def execute(task, deps, agent, **kwargs):
        del task, agent, kwargs
        for event in [*events, _task_end()]:
            deps.publisher.publish(event)
        return AgentOutcome("tamam", [], ok=True)

    prepared = prepare_attempt_experiment(
        make_config(memory_dir=tmp_path),
        arm="candidates",
        total_calls=4,
        first_slot_calls=2,
        task_id="task",
    )
    monkeypatch.setattr(plan_runner, "run_execution_plan", execute)
    runner = FusionAgentRunner(prepared.config, experiment=prepared.experiment)
    observation = await runner.run("iş", root=tmp_path, transcript=tmp_path / "_transkript.jsonl")
    replayed = TraceStore(tmp_path).read("_transkript")
    assert replayed
    assert reduce_candidate_metrics(replayed) == reduce_candidate_metrics(observation.trace_events)
    assert reduce_candidate_metrics(replayed).oracle_at_2 == 1.0


def test_tek_adim_ve_final_basarisi_bagimsiz_tam_aday_kaniti_yerine_gecmez() -> None:
    from dataclasses import replace

    events = [
        _started("a", 1),
        replace(_finished("a", 1, (EvidenceStatus.PASSED,)), scope="step"),
        _started("b", 2),
        replace(_finished("b", 2, (EvidenceStatus.PASSED,)), scope="step"),
        _task_end(),
    ]
    metrics = reduce_candidate_metrics(events)
    assert metrics.candidate_tasks == 1
    assert metrics.supported_candidate_tasks == metrics.two_candidate_tasks == 0
    assert metrics.unsupported_candidate_tasks == 1
    assert metrics.pass_at_1 is metrics.oracle_at_2 is metrics.selected_at_2 is None
    assert metrics.step_oracle_at_2 == 1.0


def test_desteklenmeyen_gorev_karisimi_ana_orani_yukseltmez() -> None:
    from dataclasses import replace

    known = [
        _started("a", 1),
        _finished("a", 1, (EvidenceStatus.PASSED,)),
        _started("b", 2),
        _finished("b", 2, (EvidenceStatus.PASSED,)),
        _task_end(),
    ]
    unknown = [
        replace(_started("c", 1), task_id="other"),
        replace(_finished("c", 1, (EvidenceStatus.PASSED,)), scope="step"),
        replace(_task_end(), task_id="other", ok=False),
    ]
    metrics = reduce_candidate_metrics([*known, *unknown])
    assert metrics.candidate_tasks == 2 and metrics.unsupported_candidate_tasks == 1
    assert metrics.pass_at_1 is metrics.oracle_at_2 is metrics.selected_at_2 is None
