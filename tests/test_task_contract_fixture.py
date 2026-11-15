"""Görev sözleşmesi Python ve TypeScript tarafında aynı (plan §2: şema fixture'ı).

`app/src/protocol/fixtures/task-contract.json` iki tarafın ortak kaynağıdır;
`taskContract.test.ts` aynı dosyayı TypeScript doğrulayıcısına okutur.
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

from fusion_cli.core.task_protocol import (
    SCHEMA_VERSION,
    TERMINAL_STATUSES,
    OperationOutcome,
    RunEvent,
    RunStatus,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "app/src/protocol/fixtures/task-contract.json"


def test_fixture_python_sozlesmesiyle_ayni():
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    assert fixture["schema_version"] == SCHEMA_VERSION
    assert fixture["run_statuses"] == [status.value for status in RunStatus]
    assert set(fixture["terminal_statuses"]) == {status.value for status in TERMINAL_STATUSES}
    assert fixture["operation_outcomes"] == [outcome.value for outcome in OperationOutcome]
    assert set(fixture["event_example"]) == {field.name for field in fields(RunEvent)}
