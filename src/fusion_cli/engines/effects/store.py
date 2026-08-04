"""Effect workflow kayıtlarını atomik ve kullanıcıya özel dizinde sakla."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .model import WorkflowRecord, WorkflowStatus, root_key


class WorkflowStore:
    """Kapanma sonrasında yeniden denemeye elveren küçük JSON deposu."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.base_dir.chmod(0o700)
        except OSError:
            pass

    def save(self, record: WorkflowRecord) -> Path:
        target = self.base_dir / f"{record.workflow_id}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(record.as_json(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, target)
        return target

    def load(self, workflow_id: str) -> WorkflowRecord | None:
        path = self.base_dir / f"{workflow_id}.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return None
        return WorkflowRecord.from_json(raw)

    def find_open(self, root: Path, kind: str) -> WorkflowRecord | None:
        wanted_root = root_key(root)
        candidates: list[WorkflowRecord] = []
        for path in self.base_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                record = WorkflowRecord.from_json(raw)
                status = WorkflowStatus(record.status)
            except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
                continue
            if record.root == wanted_root and record.kind == kind and not status.terminal:
                candidates.append(record)
        return max(candidates, key=lambda item: item.updated_at, default=None)
