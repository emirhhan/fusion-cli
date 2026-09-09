"""Başarısız plan denemelerinin yeni bilgi üretip üretmediğini ölçer."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from ...core.execution_plan import PlanStep
from .step_verification import StepVerificationResult

if TYPE_CHECKING:
    from .loop import AgentOutcome


def progress_fingerprint(
    step: PlanStep, outcome: AgentOutcome, verification: StepVerificationResult
) -> str:
    """Model anlatımını değil, araç ve doğrulama kanıtını kararlı biçimde özetle."""
    payload = {
        "step": {
            "effects": sorted(step.expected_effects),
            "checks": sorted(
                (check.kind.value, check.target, check.expected)
                for check in step.verification_checks
            ),
        },
        "tools": sorted(
            (
                use.name,
                bool(use.ok),
                json.dumps(dict(use.arguments), sort_keys=True, ensure_ascii=False, default=str),
                use.output[-2_000:],
            )
            for use in outcome.tool_uses
        ),
        "verification": {
            "findings": sorted(verification.findings),
            "criteria": sorted(
                (item.criterion_id, item.status.value, item.summary)
                for item in verification.criteria
            ),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
