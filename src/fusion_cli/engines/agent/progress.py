"""Başarısız plan denemelerinin yeni bilgi üretip üretmediğini ölçer."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING

from ...core.execution_plan import PlanStep
from .step_verification import StepVerificationResult

if TYPE_CHECKING:
    from .loop import AgentOutcome


#: Çıktıdaki her denemede değişen ayrıntılar: tarih/saat, onaltılık kimlik, geçici dizin, sayı.
#: Ölçüldü (29 Ekim, A3-12): ham çıktı (zaman damgası, PID, tmp yolu) her denemede farklı
#: özet üretiyor, "aynı duvara çarpıyorsun" tespiti (`repeated`) hiç tetiklenmiyordu.
_VOLATILE = re.compile(
    r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?Z?"
    r"|0x[0-9a-fA-F]+|\b[0-9a-f]{8,}\b"
    r"|/(?:private/)?(?:var/folders|tmp)/\S+"
    r"|\d+"
)


def _stable_tail(output: str) -> str:
    return _VOLATILE.sub("#", output[-2_000:])


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
                _stable_tail(use.output),
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
