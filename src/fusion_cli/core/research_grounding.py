"""Private immutable reader receipts and digest-bound source-consistency results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Completeness = Literal["complete", "truncated", "blocked", "unknown"]


@dataclass(frozen=True, slots=True)
class SourceReceipt:
    """Created only by trusted readers; never decoded from public tool data."""

    requested_url: str
    final_url: str
    fetched_at: str
    text: str
    completeness: Completeness = "complete"
    scope: str = "document"
    published_at: str = ""
    updated_at: str = ""
    section_id: str = ""


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    accepted_id: str
    root: str
    owner: str
    call_id: str
    receipt: SourceReceipt
    digest: str


@dataclass(frozen=True, slots=True)
class TextSpan:
    id: str
    start: int
    end: int
    text: str
    location: str


@dataclass(frozen=True, slots=True)
class ResearchTarget:
    accepted_id: str
    root: str
    owner: str
    original_task: str
    spans: tuple[TextSpan, ...]
    digest: str
    complete: bool = True


@dataclass(frozen=True, slots=True)
class ClaimFinding:
    targets: tuple[str, ...]
    kind: str
    sources: tuple[str, ...]
    basis: str


@dataclass(frozen=True, slots=True)
class GroundingVerdict:
    target_digest: str
    source_digest: str
    status: Literal["supported", "issues", "incomplete"]
    reviewed: tuple[str, ...] = ()
    claims: tuple[ClaimFinding, ...] = ()
    reason: str = ""
