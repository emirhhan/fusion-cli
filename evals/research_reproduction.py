"""Gerçek shell çağrısını dondurulmuş kriter ve ürün baytlarıyla ilişkilendirir."""

from __future__ import annotations

import hashlib
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path

from evals.research_types import ReproductionSpec
from fusion_cli.core.events import Event, ToolExecuted, ToolOutcome, ToolStarted


@dataclass(frozen=True, slots=True)
class ReproductionEvidence:
    call_id: str
    command: str
    input_path: str
    before_digest: str
    after_digest: str
    outcome: str


class ReproductionTracker:
    """Araç başlamadan ve bittikten sonra aynı gerçek ürün girdisini ölç."""

    def __init__(self, spec: ReproductionSpec) -> None:
        self.spec = spec
        self.pending: dict[str, tuple[str, str]] = {}
        self.observations: list[ReproductionEvidence] = []

    def observe(self, event: Event, root: Path) -> None:
        if not isinstance(event, (ToolStarted, ToolExecuted)) or event.name != "run_shell":
            return
        command = event.args.get("command")
        if not event.call_id or not isinstance(command, str):
            return
        product = root / self.spec.input_path
        if not product.is_file():
            return
        digest = hashlib.sha256(product.read_bytes()).hexdigest()
        if isinstance(event, ToolStarted):
            self.pending[event.call_id] = (command, digest)
            return
        before = self.pending.pop(event.call_id, None)
        if before is not None and before[0] == command:
            self.observations.append(
                ReproductionEvidence(
                    event.call_id,
                    command,
                    self.spec.input_path,
                    before[1],
                    digest,
                    event.outcome.value,
                )
            )

    def records(self) -> list[dict[str, str]]:
        """Yalnız ölçülmüş çağrıları dış kabul makbuzuna aktar."""
        return [asdict(observation) for observation in self.observations]


def check_reproduction(records: object, spec: ReproductionSpec, fixture: Path, root: Path) -> None:
    """Aynı ürün girdisi ve ilgili kriter gerçek eski/yeni baytlarda çalışmalı."""
    assert isinstance(records, list)
    seed = fixture / "seed" / (spec.input_path + ".asset")
    original = hashlib.sha256(seed.read_bytes()).hexdigest()
    final = hashlib.sha256((root / spec.input_path).read_bytes()).hexdigest()
    assert original != final, "Yeniden üretim farklı ürün sürümlerini ölçmeli"
    before = _matching(records, spec.before_command, spec.input_path, original)
    after = _matching(records, spec.after_command, spec.input_path, final)
    assert before and after, "İlgili kriter gerçek eski ve yeni ürün girdisinde çalıştırılmadı"
    expected = ToolOutcome.OK.value if spec.before_success else ToolOutcome.FAILED.value
    failures = [item for item in before if item["outcome"] == expected]
    successes = [item for item in after if item["outcome"] == ToolOutcome.OK.value]
    assert failures and successes
    assert records.index(failures[0]) < records.index(successes[-1])


def _matching(
    records: list[object], command: str, path: str, digest: str
) -> list[dict[str, object]]:
    return [
        item
        for item in records
        if isinstance(item, dict)
        and item.get("input_path") == path
        and item.get("before_digest") == item.get("after_digest") == digest
        and isinstance(item.get("command"), str)
        and shlex.split(item["command"]) == shlex.split(command)
    ]
