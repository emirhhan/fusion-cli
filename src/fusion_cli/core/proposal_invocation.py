"""Kurulu önerinin tipli kökeni ve çağrı doğrulama sınırı."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .execution_plan import ExecutionPlan
from .memory import RoutineSpec

PROPOSAL_FIELD = "fusion-proposal: "
INVOCATION_PREFIX = "FUSION_ROUTINE_INVOCATION: "


@dataclass(frozen=True, slots=True)
class ProposalPolicy:
    """Kurulu önerilerin modelden bağımsız tüketim politikası."""

    enabled: bool = False
    source_split: str = ""


@dataclass(frozen=True, slots=True)
class ProposalInvocation:
    """Beceri gövdesinden ayrı kaynak ve özgün dosya sürümü."""

    proposal_id: str
    source_split: str
    routine: RoutineSpec
    revision: str


class ProposalValidator(Protocol):
    """Alt katman motorun mevcut plan/önkoşul kapısını çağırabilir."""

    def __call__(
        self, proposal: ProposalInvocation, arguments: str, root: Path
    ) -> ExecutionPlan: ...


def body_revision(raw: str) -> str:
    """Metadata dışındaki TÜM beceri içeriği aynı sürüme bağlanır."""
    body = (
        "\n".join(line for line in raw.splitlines() if not line.startswith(PROPOSAL_FIELD)) + "\n"
    )
    return hashlib.sha256(body.encode()).hexdigest()


def proposal_metadata(raw: str) -> ProposalInvocation | None:
    """Eksik normal beceriyi koru; bozuk öneri metadata'sını reddet."""
    lines = [
        line[len(PROPOSAL_FIELD) :] for line in raw.splitlines() if line.startswith(PROPOSAL_FIELD)
    ]
    if not lines:
        return None
    if len(lines) != 1:
        raise ValueError("Öneri metadata alanı yineleniyor.")
    payload = json.loads(lines[0])
    if not isinstance(payload, dict) or set(payload) != {
        "proposal_id",
        "source_split",
        "routine",
        "revision",
    }:
        raise ValueError("Öneri metadata alanı geçersiz.")
    routine = payload["routine"]
    if not isinstance(routine, dict) or set(routine) != set(RoutineSpec.__dataclass_fields__):
        raise ValueError("Öneri rutin metadata alanı geçersiz.")
    for key in ("preconditions", "checks"):
        values = routine[key]
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError("Öneri koşulları metin listesi olmalı.")
        routine[key] = tuple(values)
    if any(
        not isinstance(value, str)
        for key, value in routine.items()
        if key not in {"preconditions", "checks"}
    ):
        raise ValueError("Öneri kaynak alanı metin olmalı.")
    if any(
        not isinstance(payload[key], str) for key in ("proposal_id", "source_split", "revision")
    ):
        raise ValueError("Öneri kimlik alanı metin olmalı.")
    return ProposalInvocation(
        payload["proposal_id"], payload["source_split"], RoutineSpec(**routine), payload["revision"]
    )


def metadata_line(proposal: ProposalInvocation) -> str:
    """Ayrılmış tek satır metadata; ikinci dosya/depo oluşturmaz."""
    return PROPOSAL_FIELD + json.dumps(asdict(proposal), ensure_ascii=False, sort_keys=True)


def visible_proposal(proposal: ProposalInvocation | None, policy: ProposalPolicy) -> bool:
    """Bilinmeyen ve geliştirme kökeni kör split'e hiçbir yoldan girmez."""
    if proposal is None:
        return True
    return policy.enabled and (policy.source_split != "blind" or proposal.source_split == "blind")
