"""Alt ajan ve inceleyici için sınırlandırılmış ortak kanıt paketi."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ...core.evidence import CriterionEvidence
from ...core.redaction import redact, redact_value
from ...core.repair_ledger import FailureEvidence

if TYPE_CHECKING:
    from .loop import AgentDeps

BUNDLE_CHAR_LIMIT = 25000
DIFF_CHAR_LIMIT = 16000


def evidence_text(criteria: tuple[CriterionEvidence | FailureEvidence, ...]) -> str:
    """Kriter metni sırları JSON içine kaçırmadan sınırlı taşınır."""
    return json.dumps(redact_value(criteria), ensure_ascii=False, default=str)[:BUNDLE_CHAR_LIMIT]


def current_diff(deps: AgentDeps) -> str:
    """Mevcut ChangeSet üzerinden aynı fark yordamını paylaş."""
    from .teacher_flow import _diff_summary

    return redact(_diff_summary(deps))[:DIFF_CHAR_LIMIT]


def compile_handoff(deps: AgentDeps, brief: str) -> str:
    """İzin veya bütçe üretmeden yalnız mevcut kanıtı kısa metne çevir."""
    if deps.config.runtime.subagent_context_mode != "evidence_bundle":
        return brief
    state = deps.lesson_state
    verification = state.verification if state is not None else None
    criteria = verification.evidence if verification is not None else ()
    from ...tools.files import _revision_of

    sources = []
    for path, recorded in deps.tool_context.read_revisions.items():
        current = _revision_of(path)
        state_text = "yeniden oku" if current != recorded else "okuma sürümü güncel"
        sources.append(f"{path}: {state_text}; sha256={current or 'bilinmiyor'}")
    parts = [
        redact(brief)[:6000],
        redact("\n".join(sources))[:4000],
        "Kanıt dosyalarını kullanmadan önce yeniden oku; içerik değişmiş olabilir.",
        "Güncel değişiklikler:\n" + current_diff(deps)[:8000],
        "Kriter kanıtları:\n" + evidence_text(criteria)[:6000],
    ]
    return "\n\n".join(parts)[:BUNDLE_CHAR_LIMIT]
