"""Stable evaluation profile identities and report metadata."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evals.executor import AgentRunner
    from fusion_cli.config.models import Config


class EvalProfile(StrEnum):
    FUSION_FULL = "fusion-full"
    FUSION_MINIMAL = "fusion-minimal"
    DIRECT = "direct"


@dataclass(frozen=True, slots=True)
class RunMetadata:
    schema_version: int = 2
    suite: str = ""
    profile: str = EvalProfile.FUSION_FULL.value
    model: str = ""
    repeat: int = 1
    seed: str | None = None
    exclusions: tuple[str, ...] = ()


def build_runner(profile: EvalProfile, config: Config) -> AgentRunner:
    if profile is EvalProfile.DIRECT:
        from evals.direct_runner import DirectRunner

        return DirectRunner(config)
    from evals.agent_runner import FusionAgentRunner, MinimalAgentRunner

    if profile is EvalProfile.FUSION_MINIMAL:
        return MinimalAgentRunner(config)
    return FusionAgentRunner(config)


def exclusions_for(profile: EvalProfile) -> tuple[str, ...]:
    if profile is EvalProfile.FUSION_FULL:
        return ("interactive_asker", "persistent_lessons", "cross_run_recall")
    if profile is EvalProfile.FUSION_MINIMAL:
        return ("verifier", "self_review", "reflexion", "recall", "playbooks", "workflow")
    return ("tools", "agent_loop", "verifier", "self_review", "reflexion")
