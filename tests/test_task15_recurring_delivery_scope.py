"""Outbox public sınırı: JSON restart, tek vade ve değişmez teslim bağlamı."""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.schedule_delivery import DELIVERY_FIELD, add_delivery


def test_delivery_json_restart_keeps_one_occurrence_and_queue_ack_unknown() -> None:
    item = {
        "id": "task15-offline-schedule",
        "baslik": "Sentetik görev",
        "gorev": "Sentetik girdiyi incele",
        "kok": "/synthetic/task15-workspace",
    }
    accepted = add_delivery(item, 1000.0)
    restarted = json.loads(json.dumps(accepted))
    retried = add_delivery(restarted, 1000.0)
    assert retried[DELIVERY_FIELD] == accepted[DELIVERY_FIELD]
    assert len(retried[DELIVERY_FIELD]) == 1
    assert retried[DELIVERY_FIELD][0]["task_id"] is None
    next_due = add_delivery(retried, 2000.0)
    assert len(next_due[DELIVERY_FIELD]) == 2
    assert next_due[DELIVERY_FIELD][0] == accepted[DELIVERY_FIELD][0]


@pytest.mark.parametrize("field", ["gorev", "kok"])
def test_duplicate_occurrence_rejects_changed_execution_scope(field: str) -> None:
    item = {
        "id": "task15-offline-schedule",
        "baslik": "Sentetik görev",
        "gorev": "Sentetik girdiyi incele",
        "kok": "/synthetic/task15-workspace",
    }
    accepted = add_delivery(item, 1000.0)
    restarted = json.loads(json.dumps(accepted))
    changed = {**restarted, field: "sentetik-farkli-baglam"}
    before = json.dumps(changed, sort_keys=True)
    with pytest.raises(ValueError):
        add_delivery(changed, 1000.0)
    assert json.dumps(changed, sort_keys=True) == before
