"""Checkpoint kanıtlarının tipli JSON dönüşümleri."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

from ..core.checkpoint import ArtifactFingerprint, StepCheckpointEvidence, WorkflowBudgetUsage
from ..core.constants import MAX_CHECKPOINT_OUTPUT_CHARS
from ..core.evidence import CriterionEvidence, EvidenceStatus, ToolUse
from ..core.execution_plan import VerificationCheckKind
from ..core.redaction import redact


def _safe_text(value: object) -> str:
    """Diske yazılan her kanıt metni maskelenir ve sınırlanır."""
    return redact(str(value))[:MAX_CHECKPOINT_OUTPUT_CHARS]


def _safe_arguments(arguments: object) -> dict[str, object]:
    """Araç argümanı da sır taşıyabilir; değerler metin olarak maskelenir."""
    if not isinstance(arguments, dict):
        return {}
    return {str(key): _safe_text(value) for key, value in arguments.items()}


def _tool_payload(use: ToolUse) -> dict[str, object]:
    return {
        "name": use.name,
        "ok": use.ok,
        "mutating": use.mutating,
        "arguments": _safe_arguments(use.arguments),
        "output": _safe_text(use.output),
    }


def _criterion_payload(evidence: CriterionEvidence) -> dict[str, object]:
    payload = asdict(evidence)
    payload["kind"] = evidence.kind.value
    payload["status"] = evidence.status.value
    payload["summary"] = _safe_text(evidence.summary)
    payload["command"] = _safe_text(evidence.command)
    payload["output"] = _safe_text(evidence.output)
    return payload


def evidence_payload(items: tuple[StepCheckpointEvidence, ...]) -> list[dict[str, object]]:
    """Sınırlı adım kanıtlarını JSON'a uygun sözlüklere çevir.

    Checkpoint diskte kalır: ham araç çıktısı ve argümanı buraya olduğu gibi
    yazılırsa devam kaydı hem sınırsız büyür hem de kullanıcının `.env` benzeri
    içeriğini taşıyabilir. Transcript ve log yollarında olduğu gibi tek çıkış
    noktası maskelemeden geçer.
    """
    return [
        {
            "step_id": item.step_id,
            "criteria": [_criterion_payload(evidence) for evidence in item.criteria],
            "artifacts": [asdict(artifact) for artifact in item.artifacts],
            "tool_uses": [_tool_payload(use) for use in item.tool_uses],
            "tool_calls": item.tool_calls,
            "mutation_calls": item.mutation_calls,
            "already_done_calls": item.already_done_calls,
        }
        for item in items
    ]


def budget_payload(items: tuple[WorkflowBudgetUsage, ...]) -> list[dict[str, object]]:
    """Zarf kayıtlarını JSON'a uygun sözlüklere çevir."""
    return [asdict(item) for item in items]


def _objects(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        raise ValueError("checkpoint kanıt listesi bekleniyordu")
    if not all(isinstance(item, dict) for item in raw):
        raise ValueError("checkpoint kanıt nesnesi bekleniyordu")
    return cast("list[dict[str, object]]", raw)


def _text(item: dict[str, object], name: str) -> str:
    value = item.get(name, "")
    if not isinstance(value, str):
        raise ValueError(f"geçersiz checkpoint kanıt alanı: {name}")
    return value


def _count(item: dict[str, object], name: str) -> int:
    value = item.get(name, 0)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"geçersiz checkpoint sayacı: {name}")
    return value


def _tool(item: dict[str, object]) -> ToolUse:
    arguments = item.get("arguments", {})
    if not isinstance(arguments, dict) or not all(isinstance(key, str) for key in arguments):
        raise ValueError("geçersiz checkpoint araç argümanları")
    ok, mutating = item.get("ok"), item.get("mutating")
    if not isinstance(ok, bool) or not isinstance(mutating, bool):
        raise ValueError("geçersiz checkpoint araç sonucu")
    return ToolUse(_text(item, "name"), ok, mutating, arguments, _text(item, "output"))


def parse_evidence(raw: object) -> tuple[StepCheckpointEvidence, ...]:
    """Eski kayıtta alan yoksa kanıt uydurmadan boş kayıt döndür."""
    results = []
    for item in _objects(raw):
        criteria = tuple(
            CriterionEvidence(
                criterion_id=_text(criterion, "criterion_id"),
                kind=VerificationCheckKind(_text(criterion, "kind")),
                status=EvidenceStatus(_text(criterion, "status")),
                summary=_text(criterion, "summary"),
                artifact=_text(criterion, "artifact"),
                command=_text(criterion, "command"),
                output=_text(criterion, "output"),
            )
            for criterion in _objects(item.get("criteria", []))
        )
        artifacts = tuple(
            ArtifactFingerprint(_text(artifact, "path"), _text(artifact, "digest"))
            for artifact in _objects(item.get("artifacts", []))
        )
        results.append(
            StepCheckpointEvidence(
                step_id=_text(item, "step_id"),
                criteria=criteria,
                artifacts=artifacts,
                tool_uses=tuple(_tool(tool) for tool in _objects(item.get("tool_uses", []))),
                tool_calls=_count(item, "tool_calls"),
                mutation_calls=_count(item, "mutation_calls"),
                already_done_calls=_count(item, "already_done_calls"),
            )
        )
    return tuple(results)


def parse_budget(raw: object) -> tuple[WorkflowBudgetUsage, ...]:
    """Kayıtlı zarf harcamasını geri yükle."""
    return tuple(
        WorkflowBudgetUsage(_text(item, "envelope"), _text(item, "scope"), _count(item, "calls"))
        for item in _objects(raw)
    )
