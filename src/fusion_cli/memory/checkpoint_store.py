"""Workflow checkpoint'leri için atomik ve toleranslı JSON deposu."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import replace
from pathlib import Path
from typing import cast

from ..core.atomic_file import atomic_replace_text
from ..core.checkpoint import WorkflowCheckpoint
from ..core.errors import CheckpointConflictError
from ..core.execution_plan import (
    ExecutionPlan,
    PlanPhase,
    PlanStatus,
    PlanStep,
    RetrySafety,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
)
from ..core.file_lease import FileLease
from ..core.read_budget import ReadBudget, ReadBudgetExceededError
from ..core.routine_codec import decode_routine, encode_routine
from .checkpoint_effects import effects_payload, parse_effects
from .checkpoint_evidence import budget_payload, evidence_payload, parse_budget, parse_evidence
from .checkpoint_repair import parse_repair, repair_payload

_logger = logging.getLogger(__name__)
_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")
_SUPPORTED_SCHEMAS = frozenset({1, 2, 3, 4, 5, 6, 7})


def _step_to_dict(step: PlanStep) -> dict[str, object]:
    return {
        "step_id": step.step_id,
        "goal": step.goal,
        "depends_on": list(step.depends_on),
        "expected_effects": list(step.expected_effects),
        "allowed_tool_families": list(step.allowed_tool_families),
        "success_criteria": list(step.success_criteria),
        "verification_hint": step.verification_hint,
        "retry_safety": step.retry_safety.value,
        "status": step.status.value,
        "attempts": step.attempts,
        "verification_checks": [
            {
                "criterion_id": check.criterion_id,
                "kind": check.kind.value,
                "target": check.target,
                "expected": check.expected,
            }
            for check in step.verification_checks
        ],
        "phase": step.phase.value,
        "revision": step.revision,
        "last_progress_fingerprint": step.last_progress_fingerprint,
    }


def _to_dict(checkpoint: WorkflowCheckpoint) -> dict[str, object]:
    plan = checkpoint.plan
    return {
        "schema_version": 7,
        "storage_revision": checkpoint.storage_revision,
        "plan": {
            "routine": encode_routine(plan.routine),
            "plan_id": plan.plan_id,
            "task": plan.task,
            "schema_version": plan.schema_version,
            "status": plan.status.value,
            "steps": [_step_to_dict(step) for step in plan.steps],
        },
        "root": checkpoint.root,
        "conversation_id": checkpoint.conversation_id,
        "completed_step_ids": list(checkpoint.completed_step_ids),
        "updated_at": checkpoint.updated_at,
        "step_evidence": evidence_payload(checkpoint.step_evidence),
        "budget_usage": budget_payload(checkpoint.budget_usage),
        "condensations": checkpoint.condensations,
        "quality_feedback": checkpoint.quality_feedback,
        "uncovered": list(checkpoint.uncovered),
        "effect_intents": effects_payload(checkpoint.effect_intents),
        "turn_repair": repair_payload(checkpoint.turn_repair, checkpoint.root),
    }


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("metin listesi bekleniyordu")
    return tuple(value)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("nesne bekleniyordu")
    return cast("dict[str, object]", value)


def _text(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"geçersiz alan: {key}")
    return value


def _integer(data: dict[str, object], key: str, default: int = 0) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"geçersiz alan: {key}")
    return value


def _verification_checks(value: object) -> tuple[VerificationCheck, ...]:
    """Yeni kontrolleri oku; eski checkpoint'lerde alan yoksa boş kabul et."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("geçersiz verification_checks")
    checks: list[VerificationCheck] = []
    for item in value:
        data = _mapping(item)
        expected = data.get("expected", "")
        if not isinstance(expected, str):
            raise ValueError("geçersiz verification check expected")
        checks.append(
            VerificationCheck(
                criterion_id=_text(data, "criterion_id"),
                kind=VerificationCheckKind(_text(data, "kind")),
                target=_text(data, "target"),
                expected=expected,
            )
        )
    return tuple(checks)


def _from_dict(raw: object) -> WorkflowCheckpoint:
    data = _mapping(raw)
    schema = data.get("schema_version", 1)
    if isinstance(schema, bool) or not isinstance(schema, int) or schema not in _SUPPORTED_SCHEMAS:
        raise ValueError("Desteklenmeyen checkpoint şeması.")
    storage_revision = _integer(data, "storage_revision")
    if storage_revision < 0 or (schema >= 5 and "storage_revision" not in data):
        raise ValueError("Geçersiz checkpoint storage revision.")
    if schema >= 6 and "effect_intents" not in data:
        raise ValueError("Dış işlem intent metadata'sı eksik.")
    plan_data = _mapping(data.get("plan"))
    if schema >= 7 and "routine" not in plan_data:
        raise ValueError("Rutin metadata alanı eksik.")
    steps_raw = plan_data.get("steps")
    if not isinstance(steps_raw, list):
        raise ValueError("geçersiz steps")
    steps: list[PlanStep] = []
    for item in steps_raw:
        step = _mapping(item)
        steps.append(
            PlanStep(
                step_id=_text(step, "step_id"),
                goal=_text(step, "goal"),
                depends_on=_strings(step.get("depends_on")),
                expected_effects=_strings(step.get("expected_effects")),
                allowed_tool_families=_strings(step.get("allowed_tool_families")),
                success_criteria=_strings(step.get("success_criteria")),
                verification_hint=_text(step, "verification_hint"),
                retry_safety=RetrySafety(_text(step, "retry_safety")),
                status=StepStatus(_text(step, "status")),
                attempts=_integer(step, "attempts"),
                verification_checks=_verification_checks(step.get("verification_checks")),
                phase=PlanPhase(str(step.get("phase", PlanPhase.EXECUTION.value))),
                revision=_integer(step, "revision", 0),
                last_progress_fingerprint=str(step.get("last_progress_fingerprint", "")),
            )
        )
    updated_at = data.get("updated_at")
    if not isinstance(updated_at, int | float) or isinstance(updated_at, bool):
        raise ValueError("geçersiz updated_at")
    effects = parse_effects(data.get("effect_intents", []))
    step_attempts = {step.step_id: step.attempts for step in steps}
    if any(
        item.step_id not in step_attempts or item.attempt > step_attempts[item.step_id]
        for item in effects
    ):
        raise ValueError("Dış işlem intent'i plan denemesiyle eşleşmiyor.")
    return WorkflowCheckpoint(
        plan=ExecutionPlan(
            plan_id=_text(plan_data, "plan_id"),
            task=_text(plan_data, "task"),
            steps=tuple(steps),
            status=PlanStatus(_text(plan_data, "status")),
            schema_version=_integer(plan_data, "schema_version", 1),
            routine=decode_routine(plan_data.get("routine")),
        ),
        root=_text(data, "root"),
        conversation_id=_text(data, "conversation_id"),
        completed_step_ids=_strings(data.get("completed_step_ids")),
        updated_at=float(updated_at),
        step_evidence=parse_evidence(data.get("step_evidence", [])),
        budget_usage=parse_budget(data.get("budget_usage", [])),
        condensations=_integer(data, "condensations", 0),
        quality_feedback=_text(data, "quality_feedback") if "quality_feedback" in data else "",
        turn_repair=parse_repair(data.get("turn_repair"), _text(data, "root")),
        storage_revision=storage_revision,
        effect_intents=effects,
        uncovered=_strings(data.get("uncovered", [])),
    )


class JsonCheckpointStore:
    """Workspace/konuşma/plan kimliğiyle atomik yerel devam deposu."""

    def __init__(
        self,
        base_dir: Path,
        *,
        root: Path | None = None,
        conversation_id: str | None = None,
    ) -> None:
        if (root is None) != (conversation_id is None):
            raise ValueError("Checkpoint kökü ve konuşması birlikte belirtilmeli.")
        self._base_dir = base_dir
        self._scope = (str(root.resolve()), conversation_id) if root is not None else None

    @staticmethod
    def _identity(checkpoint: WorkflowCheckpoint) -> tuple[str, str, str]:
        return (
            str(Path(checkpoint.root).resolve()),
            checkpoint.conversation_id,
            checkpoint.plan.plan_id,
        )

    def _canonical(self, identity: tuple[str, str, str]) -> Path:
        digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        return self._base_dir / f"{digest}.json"

    def _legacy_paths(self, plan_id: str) -> tuple[Path, Path]:
        safe_id = _SAFE_ID.sub("_", plan_id).strip("._") or "plan"
        digest = hashlib.sha256(plan_id.encode()).hexdigest()
        return (self._base_dir / f"{safe_id}.json", self._base_dir / f"{digest}.json")

    def save(self, checkpoint: WorkflowCheckpoint, *, expected_revision: int | None = None) -> int:
        identity = self._identity(checkpoint)
        if self._scope is not None and identity[:2] != self._scope:
            raise ValueError("Checkpoint başka konuşma kapsamına yazılamaz.")
        expected = expected_revision
        if expected is None:
            expected = checkpoint.storage_revision
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
            raise ValueError("Beklenen checkpoint revision geçersiz.")
        lease = FileLease(self._canonical(identity).with_suffix(".lock"))
        try:
            if not lease.try_acquire():
                raise CheckpointConflictError("Checkpoint başka işlemde değiştiriliyor.")
            return self._save_locked(checkpoint, identity, expected)
        finally:
            lease.close()

    def _save_locked(
        self,
        checkpoint: WorkflowCheckpoint,
        identity: tuple[str, str, str],
        expected: int,
    ) -> int:
        target = self._canonical(identity)
        current = self._read_path(target) if target.exists() else None
        if target.exists() and current is None:
            # Okunamayan kayıt (bozuk JSON, desteklenmeyen şema, geçersiz alan) bu planın
            # hem devamını hem yeniden kaydını KALICI engelliyordu (M1-43). Kenara alınır
            # (silinmez), uyarı loglanır ve plan sıfırdan yazılır.
            self._quarantine(target)
        elif current is not None and self._identity(current) != identity:
            raise CheckpointConflictError("Checkpoint değişmiş veya desteklenmiyor.")
        if current is None:
            current = next(
                (
                    candidate
                    for path in self._legacy_paths(checkpoint.plan.plan_id)
                    if (candidate := self._read_valid(path)) is not None
                    and self._identity(candidate) == identity
                ),
                None,
            )
        actual = current.storage_revision if current is not None else 0
        if expected != actual:
            raise CheckpointConflictError("Checkpoint revision değişti; eski kayıt yazılmadı.")
        if current == checkpoint:
            return actual
        committed = replace(checkpoint, storage_revision=actual + 1)
        payload = json.dumps(_to_dict(committed), ensure_ascii=False, indent=2)
        atomic_replace_text(target, payload)
        return committed.storage_revision

    def load(self, plan_id: str) -> WorkflowCheckpoint | None:
        return self._load(plan_id)

    def load_bounded(self, plan_id: str, *, read_budget: ReadBudget) -> WorkflowCheckpoint | None:
        """Optional projection only; incomplete bytes never become a checkpoint."""
        try:
            result = self._load(plan_id, read_budget=read_budget)
            read_budget.check()
            return result
        except ReadBudgetExceededError:
            return None

    def _load(
        self, plan_id: str, *, read_budget: ReadBudget | None = None
    ) -> WorkflowCheckpoint | None:
        paths: tuple[Path, ...]
        if self._scope is not None:
            root, conversation = self._scope
            paths = (
                self._canonical((root, conversation or "", plan_id)),
                *self._legacy_paths(plan_id),
            )
        elif read_budget is not None:
            try:
                paths = tuple(
                    Path(entry.path)
                    for entry in read_budget.iterdir(self._base_dir)
                    if entry.name.endswith(".json")
                )
            except FileNotFoundError:
                paths = ()
        else:
            paths = self._paths()
        matches: dict[tuple[str, str, str], WorkflowCheckpoint] = {}
        for path in paths:
            if read_budget is not None:
                read_budget.check()
            checkpoint = self._read_valid(path, read_budget=read_budget)
            if checkpoint is None or checkpoint.plan.plan_id != plan_id:
                continue
            identity = self._identity(checkpoint)
            if self._scope is None or identity[:2] == self._scope:
                matches[identity] = checkpoint
        # Eski plan-only API belirsiz konuşmayı tahmin etmez.
        result = next(iter(matches.values())) if len(matches) == 1 else None
        return result

    @staticmethod
    def _read_path(
        path: Path, *, read_budget: ReadBudget | None = None
    ) -> WorkflowCheckpoint | None:
        try:
            text = (
                path.read_text(encoding="utf-8")
                if read_budget is None
                else read_budget.read_bytes(path).decode("utf-8")
            )
            raw = cast("object", json.loads(text))
            result = _from_dict(raw)
            if read_budget is not None:
                read_budget.check()
            return result
        except (OSError, ValueError, TypeError, KeyError) as error:
            # Neden okunamadığı sessizce kaybolmasın: dosya adı ve hata türü loglanır.
            _logger.warning(
                "checkpoint okunamadı",
                extra={
                    "dosya": path.name,
                    "hata": (
                        type(error).__name__
                        if read_budget is not None
                        else f"{type(error).__name__}: {str(error)[:200]}"
                    ),
                },
            )
            return None

    @staticmethod
    def _quarantine(path: Path) -> None:
        """Okunamayan kaydı `.corrupt` uzantısıyla kenara al (silinmez, `*.json` dışında kalır)."""
        hedef = path.with_suffix(".corrupt")
        sira = 1
        while hedef.exists():
            hedef = path.with_suffix(f".corrupt.{sira}")
            sira += 1
        try:
            path.replace(hedef)
        except OSError as error:
            raise CheckpointConflictError(
                f"Okunamayan checkpoint kenara alınamadı ({path.name}): {error}"
            ) from error
        _logger.warning(
            "okunamayan checkpoint kenara alındı", extra={"dosya": path.name, "yedek": hedef.name}
        )

    def _read_valid(
        self, path: Path, *, read_budget: ReadBudget | None = None
    ) -> WorkflowCheckpoint | None:
        checkpoint = self._read_path(path, read_budget=read_budget)
        if checkpoint is None:
            return None
        canonical = self._canonical(self._identity(checkpoint))
        if path not in {canonical, *self._legacy_paths(checkpoint.plan.plan_id)}:
            return None
        if path != canonical and canonical.exists():
            return None
        return checkpoint

    def _paths(self) -> tuple[Path, ...]:
        try:
            return tuple(self._base_dir.glob("*.json"))
        except OSError:
            return ()

    def purge_completed(self, *, cutoff: float) -> int:
        """`cutoff`tan eski TAMAMLANMIŞ checkpoint'leri sil; silinen sayıyı döndür (M1-44).

        Çalışan, duraklatılmış ve başarısız planlar (devam ettirilebilir) ile okunamayan
        kayıtlar korunur. Önce dosya değişme zamanına bakılır: yalnız eski adaylar okunur.
        Kayıt, yazanla yarışmamak için `save` ile aynı kiralama altında silinir.
        """
        removed = 0
        for path in self._paths():
            try:
                if path.is_symlink() or path.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            checkpoint = self._read_valid(path)
            if (
                checkpoint is None
                or checkpoint.plan.status is not PlanStatus.COMPLETED
                or checkpoint.updated_at >= cutoff
            ):
                continue
            removed += self._remove_locked(path, checkpoint)
        return removed

    def _remove_locked(self, path: Path, checkpoint: WorkflowCheckpoint) -> int:
        lock = self._canonical(self._identity(checkpoint)).with_suffix(".lock")
        lease = FileLease(lock)
        try:
            if not lease.try_acquire():
                return 0  # başka işlem yazıyor; sonraki açılışta yeniden denenir
            path.unlink(missing_ok=True)
            lock.unlink(missing_ok=True)
            return 1
        except OSError:
            return 0
        finally:
            lease.close()

    def find_resumable(self, root: str, conversation_id: str) -> WorkflowCheckpoint | None:
        scope = (str(Path(root).resolve()), conversation_id)
        if self._scope is not None and scope != self._scope:
            return None
        matches: dict[tuple[str, str, str], WorkflowCheckpoint] = {}
        for path in self._paths():
            checkpoint = self._read_valid(path)
            if checkpoint is not None:
                identity = self._identity(checkpoint)
                if identity[:2] == scope and checkpoint.plan.status is not PlanStatus.COMPLETED:
                    matches[identity] = checkpoint
        result = max(matches.values(), key=lambda item: item.updated_at, default=None)
        return result
