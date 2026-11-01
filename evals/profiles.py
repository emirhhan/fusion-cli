"""Sabit değerlendirme profilleri ve sır taşımayan koşu kökeni."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from evals.execution import ModelCallIdentity
from evals.loader import load_suite

if TYPE_CHECKING:
    from evals.executor import AgentRunner
    from evals.tasks import EvalTask
    from fusion_cli.config.models import Config
    from fusion_cli.engines.agent.attempts import AttemptExperiment


class EvalProfile(StrEnum):
    PRODUCTION = "production"
    FUSION_FULL = "fusion-full"
    FUSION_MINIMAL = "fusion-minimal"
    DIRECT = "direct"


@dataclass(frozen=True, slots=True)
class RunMetadata:
    schema_version: int = 3
    suite: str = ""
    profile: str = EvalProfile.FUSION_FULL.value
    model: str = ""
    repeat: int = 1
    seed: str | None = None
    exclusions: tuple[str, ...] = ()
    arm: str = "primary-strict"
    requested_model: str | None = None
    calls: tuple[ModelCallIdentity, ...] = ()
    source_digest: str | None = None
    prompt_digest: str | None = None
    initial_workspace_digest: str | None = None
    split: str | None = None
    split_digest: str | None = None
    scorer_digest: str | None = None
    effective_config_digest: str | None = None
    environment_digest: str | None = None
    corpus_digest: str | None = None
    max_model_calls: int | None = None
    timeout_s: float | None = None
    execution_ids: tuple[tuple[str, int], ...] = ()
    task_config_digests: tuple[tuple[str, str], ...] = ()
    model_calls_total: int | None = None
    task_ids: tuple[str, ...] = ()
    task_budgets: tuple[tuple[str, int, float], ...] = ()
    corpus_counts: tuple[tuple[str, int], ...] = ()
    unknowns: tuple[str, ...] = ("environment", "corpus", "live_baseline")


def build_runner(
    profile: EvalProfile,
    config: Config,
    *,
    experiment: AttemptExperiment | None = None,
    source_split: str | None = None,
    task: EvalTask | None = None,
) -> AgentRunner:
    validate_profile_tasks(profile, (task,) if task is not None else ())
    if (
        task is not None
        and task.runtime_scenario
        and profile in {EvalProfile.DIRECT, EvalProfile.FUSION_MINIMAL}
    ):
        raise ValueError("Runtime araştırma görevi tam Fusion profilini gerektirir.")
    if experiment is not None and profile in {EvalProfile.DIRECT, EvalProfile.FUSION_MINIMAL}:
        raise ValueError("Aday deneyi tam Fusion yürütme profilini gerektirir.")
    config = resolve_profile_config(profile, config)
    if profile is EvalProfile.DIRECT:
        from evals.direct_runner import DirectRunner

        return DirectRunner(config)
    from evals.agent_runner import FusionAgentRunner, MinimalAgentRunner

    if profile is EvalProfile.FUSION_MINIMAL:
        return MinimalAgentRunner(config, source_split=source_split, task=task)
    return FusionAgentRunner(config, experiment=experiment, source_split=source_split, task=task)


def validate_profile_tasks(profile: EvalProfile, tasks: tuple[EvalTask, ...]) -> None:
    """Uygulanmayan bütçeyi desteklenmiş veya ölçülmüş gibi sunma."""
    if profile in {EvalProfile.DIRECT, EvalProfile.FUSION_MINIMAL} and any(
        task.budget is not None for task in tasks
    ):
        raise ValueError(
            "Görev bütçesi bu profilde desteklenmiyor; fusion-full veya production kullanın."
        )


def exclusions_for(profile: EvalProfile) -> tuple[str, ...]:
    if profile in {EvalProfile.PRODUCTION, EvalProfile.FUSION_FULL}:
        return ("interactive_asker", "persistent_lessons", "cross_run_recall")
    if profile is EvalProfile.FUSION_MINIMAL:
        return ("verifier", "self_review", "reflexion", "recall", "playbooks", "workflow")
    return ("tools", "agent_loop", "verifier", "self_review", "reflexion")


def prepare_eval_config(config: Config, model: str | None = None) -> Config:
    """Ana deney kolunu mevcut strict yoldan kur; kullanıcı ayarına yazma."""
    from fusion_cli.config.model_select import apply_single_model

    selected = apply_single_model(config, model or config.agent.model)
    runtime = replace(
        selected.runtime,
        teacherless=True,
        lessons=False,
        teacher_lesson_sync=False,
        teacher_codex_fallback=False,
        escalate_on_gate_failure=False,
        escalation_model="",
        auto_web_fallback=False,
    )
    return replace(selected, runtime=runtime, teacher=None, vision=selected.agent, tiers=())


def resolve_profile_config(profile: EvalProfile, config: Config) -> Config:
    """Profil ayarını tek yerde çöz; çözülmüş nesneyi runner ve metadata paylaşır."""
    if profile is not EvalProfile.FUSION_MINIMAL:
        return config
    from fusion_cli.core.execution_mode import ExecutionMode

    runtime = replace(
        config.runtime,
        self_review=False,
        reflexion=False,
        lessons=False,
        verification_commands=(),
        web_verification=False,
        browser_verification=False,
        visual_verification=False,
        playbooks=False,
        workflow_mode=ExecutionMode.OFF,
    )
    return config if runtime == config.runtime else replace(config, runtime=runtime)


def _digest_entries(entries: object) -> str:
    return hashlib.sha256(
        json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def _file_digests(root: Path, paths: tuple[Path, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(paths)
        if path.is_file() and not path.is_symlink()
    )


def _source_entries(root: Path) -> tuple[tuple[str, str], ...]:
    paths = (*tuple((root / "src").rglob("*.py")), *tuple((root / "evals").glob("*.py")))
    return _file_digests(root, paths)


def _prompt_entries(root: Path) -> tuple[tuple[str, str], ...]:
    return _file_digests(
        root,
        tuple(
            path
            for path in (root / "src").rglob("*")
            if "prompts" in path.parts and path.suffix in {".txt", ".md"}
        ),
    )


def _scorer_entries(root: Path) -> tuple[tuple[str, str], ...]:
    scorer_paths = tuple((root / "evals/fixtures/fusion_research").rglob("acceptance.py"))
    return _file_digests(
        root,
        (
            *scorer_paths,
            root / "evals/criteria.py",
            root / "evals/research_acceptance.py",
            root / "evals/executor.py",
            root / "evals/metrics.py",
            root / "evals/candidate_metrics.py",
            root / "evals/fixtures/fusion_research/manifest.json",
        ),
    )


def build_run_metadata(
    *,
    suite: Path,
    tasks: tuple[EvalTask, ...],
    profile: EvalProfile,
    config: Config,
    repeat: int,
    seed: Path | None,
    calls: tuple[ModelCallIdentity, ...],
    experiment: AttemptExperiment | None = None,
) -> RunMetadata:
    """Exact dosya özetlerini dondur; ortam/Task3 bağlantısı verilmediyse bilinmez."""
    from evals.effective_config import project_effective

    validate_profile_tasks(profile, tasks)
    root = Path(__file__).resolve().parents[1]
    source = _source_entries(root)
    prompts = _prompt_entries(root)
    scorer = _scorer_entries(root)
    seed_entries = () if seed is None else _file_digests(seed, tuple(seed.rglob("*")))
    split = load_suite(suite).metadata.split
    budgets = tuple(
        (task.id, task.budget.max_model_calls, task.budget.timeout_s)
        for task in tasks
        if task.budget is not None
    )
    uniform_calls = {item[1] for item in budgets}
    uniform_timeout = {item[2] for item in budgets}
    has_all_budgets = len(budgets) == len(tasks) and bool(tasks)
    return RunMetadata(
        task_ids=tuple(task.id for task in tasks),
        task_budgets=budgets,
        timeout_s=next(iter(uniform_timeout))
        if has_all_budgets and len(uniform_timeout) == 1
        else None,
        suite=str(suite),
        profile=profile.value,
        model=config.agent.model,
        repeat=repeat,
        seed=None if seed is None else str(seed),
        exclusions=exclusions_for(profile),
        requested_model=config.agent.model,
        arm=experiment.arm if experiment else "primary-strict",
        max_model_calls=experiment.total_calls
        if experiment
        else (next(iter(uniform_calls)) if has_all_budgets and len(uniform_calls) == 1 else None),
        calls=calls,
        source_digest=_digest_entries(source),
        prompt_digest=_digest_entries((prompts, [(task.id, task.request) for task in tasks])),
        initial_workspace_digest=_digest_entries(
            (seed_entries, [(task.id, sorted(task.setup.items())) for task in tasks])
        ),
        split=None if split is None else str(split),
        split_digest=hashlib.sha256(suite.read_bytes()).hexdigest(),
        scorer_digest=_digest_entries(scorer),
        effective_config_digest=project_effective(config, config.agent, "eval").digest,
        unknowns=("environment", "corpus", "live_baseline")
        + (() if has_all_budgets else ("task_timeout",))
        + (() if experiment or has_all_budgets else ("task_call_budget",)),
    )


@dataclass(frozen=True, slots=True)
class PreparedAttemptExperiment:
    """Üretim varsayılanına yazmadan hazırlanmış ölçüm kolu."""

    config: Config
    experiment: AttemptExperiment


def prepare_attempt_experiment(
    config: Config,
    *,
    arm: Literal["candidates", "serial"],
    total_calls: int,
    first_slot_calls: int,
    task_id: str,
    repeat: int = 1,
) -> PreparedAttemptExperiment:
    """İki kol aynı model, yerel doğrulama ve toplam invocation tavanıyla çalışır."""
    from fusion_cli.engines.agent.attempts import AttemptExperiment

    prepared = prepare_eval_config(config)
    runtime = replace(
        prepared.runtime,
        self_review=False,
        web_verification=False,
        browser_verification=False,
        visual_verification=False,
    )
    prepared = replace(prepared, runtime=runtime)
    return PreparedAttemptExperiment(
        prepared,
        AttemptExperiment(arm, total_calls, first_slot_calls, prepared.agent, task_id, repeat),
    )


def build_attempt_runner_factory(
    profile: EvalProfile,
    config: Config,
    experiment: AttemptExperiment,
    *,
    source_split: str | None = None,
) -> Callable[[EvalTask, int], AgentRunner]:
    """Gerçek görev ve tekrar kimliğini dondur; mevcut runner çağrısını paylaş."""

    def create(task: EvalTask, repeat: int) -> AgentRunner:
        return build_runner(
            profile,
            config,
            experiment=replace(experiment, task_id=task.id, repeat=repeat),
            source_split=source_split,
            task=task,
        )

    return create
