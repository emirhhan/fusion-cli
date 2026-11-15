"""Checkpoint kanıtlarının tipli JSON dönüşümleri."""

from __future__ import annotations

from dataclasses import asdict, replace
from typing import cast

from ..core.checkpoint import ArtifactFingerprint, StepCheckpointEvidence, WorkflowBudgetUsage
from ..core.constants import MAX_CHECKPOINT_OUTPUT_CHARS
from ..core.evidence import CriterionEvidence, EvidenceEnvironment, EvidenceStatus, ToolUse
from ..core.execution_plan import VerificationCheckKind
from ..core.redaction import redact
from ..core.workspace_fingerprint import WorkspaceEffect


def _safe_text(value: object) -> str:
    """Diske yazılan her kanıt metni maskelenir ve sınırlanır."""
    return redact(str(value))[:MAX_CHECKPOINT_OUTPUT_CHARS]


def _safe_arguments(arguments: object) -> dict[str, object]:
    """Araç argümanı da sır taşıyabilir; değerler metin olarak maskelenir."""
    if not isinstance(arguments, dict):
        return {}
    return {str(key): _safe_text(value) for key, value in arguments.items()}


#: Checkpoint'e yazılacak en çok değişen-dosya adı (kanıt tazeliğini boş/dolu bilgisi belirler).
_MAX_CHECKPOINT_CHANGED = 50


def _environment_payload(environment: EvidenceEnvironment | None) -> dict[str, str] | None:
    """Ortam referansını checkpoint sınırında maskeli taşı."""
    return (
        {key: _safe_text(value) for key, value in asdict(environment).items()}
        if environment
        else None
    )


def _environment(item: dict[str, object]) -> EvidenceEnvironment | None:
    """Eski kayıtta kimlik yoksa ortam uydurma."""
    raw = item.get("environment")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("geçersiz checkpoint kanıt ortamı")
    return EvidenceEnvironment(
        *(
            _text(raw, field)
            for field in ("command", "cwd", "runtime", "dependency_digest", "config_digest")
        )
    )


def _tool_payload(use: ToolUse) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": use.name,
        "ok": use.ok,
        "mutating": use.mutating,
        "arguments": _safe_arguments(use.arguments),
        "output": _safe_text(use.output),
        "source_digest": _safe_text(use.source_digest),
        "source_after_digest": _safe_text(use.source_after_digest),
        "call_id": _safe_text(use.call_id),
        "environment": _environment_payload(use.environment),
    }
    effect = use.workspace_effect
    if effect is not None:
        payload["workspace_changed"] = (
            None
            if effect.changed is None
            else [_safe_text(path) for path in effect.changed[:_MAX_CHECKPOINT_CHANGED]]
        )
        payload["workspace_reason"] = _safe_text(effect.reason)
    return payload


def _effect(item: dict[str, object]) -> WorkspaceEffect | None:
    """Eski kayıtta alan yoksa ölçüm UYDURULMAZ (temkinli sınıflandırma geçerli kalır)."""
    if "workspace_changed" not in item:
        return None
    changed = item["workspace_changed"]
    reason = _text(item, "workspace_reason")
    if changed is None:
        return WorkspaceEffect(None, reason)
    if not isinstance(changed, list) or not all(isinstance(path, str) for path in changed):
        raise ValueError("geçersiz checkpoint çalışma alanı etkisi")
    return WorkspaceEffect(tuple(changed), reason)


def _criterion_payload(evidence: CriterionEvidence) -> dict[str, object]:
    payload = asdict(evidence)
    payload["kind"] = evidence.kind.value
    payload["status"] = evidence.status.value
    payload["summary"] = _safe_text(evidence.summary)
    payload["artifact"] = _safe_text(evidence.artifact)
    payload["command"] = _safe_text(evidence.command)
    payload["output"] = _safe_text(evidence.output)
    for field in (
        "source_digest",
        "source_after_digest",
        "call_id",
        "step_id",
        "check_target",
        "check_expected",
    ):
        payload[field] = _safe_text(getattr(evidence, field))
    payload["environment"] = _environment_payload(evidence.environment)
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


def _flag(item: dict[str, object], name: str) -> bool:
    """Eklemeli boolean alanını geriye uyumlu doğrula."""
    value = item.get(name, True)
    if not isinstance(value, bool):
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
    return ToolUse(
        _text(item, "name"),
        ok,
        mutating,
        arguments,
        _text(item, "output"),
        workspace_effect=_effect(item),
        source_digest=_text(item, "source_digest"),
        source_after_digest=_text(item, "source_after_digest"),
        environment=_environment(item),
        call_id=_text(item, "call_id"),
    )


def _criterion(criterion: dict[str, object]) -> CriterionEvidence:
    """Sürümsüz eski kanıttan kaynak veya ortam kimliği türetme."""
    evidence = CriterionEvidence(
        criterion_id=_text(criterion, "criterion_id"),
        kind=VerificationCheckKind(_text(criterion, "kind")),
        status=EvidenceStatus(_text(criterion, "status")),
        summary=_text(criterion, "summary"),
        artifact=_text(criterion, "artifact"),
        command=_text(criterion, "command"),
        output=_text(criterion, "output"),
        behavioral=_flag(criterion, "behavioral"),
        applicable=_flag(criterion, "applicable"),
        step_id=_text(criterion, "step_id"),
        check_target=_text(criterion, "check_target"),
        check_expected=_text(criterion, "check_expected"),
        source_digest=_text(criterion, "source_digest"),
        source_after_digest=_text(criterion, "source_after_digest"),
        environment=_environment(criterion),
        call_id=_text(criterion, "call_id"),
    )
    if evidence.kind is VerificationCheckKind.REPRODUCTION and not (
        evidence.source_digest
        and evidence.source_after_digest
        and evidence.environment is not None
        and evidence.call_id
    ):
        evidence = replace(evidence, status=EvidenceStatus.UNVERIFIED)
    return evidence


def parse_evidence(raw: object) -> tuple[StepCheckpointEvidence, ...]:
    """Eski kayıtta alan yoksa kanıt uydurmadan boş kayıt döndür."""
    results = []
    for item in _objects(raw):
        criteria = tuple(_criterion(criterion) for criterion in _objects(item.get("criteria", [])))
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
