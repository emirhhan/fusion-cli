"""Vade teslimi ack gelmeden restartta kaybolmaz."""

from datetime import UTC, datetime, timedelta

from fusion_cli.appserver.schedule import claim_due, save_schedule
from fusion_cli.appserver.schedule_delivery import acknowledge_delivery, pending_deliveries


def prepared(tmp_path):
    now = datetime(2026, 10, 8, tzinfo=UTC)
    path = tmp_path / "schedule.json"
    result = save_schedule(
        {
            "baslik": "Görev",
            "gorev": "incele",
            "kok": str(tmp_path),
            "tur": "bir_kez",
            "zaman": (now + timedelta(minutes=1)).timestamp(),
        },
        path,
        now,
    )
    assert result["ok"]
    return path, now + timedelta(minutes=2)


def test_claim_restart_pending_survives_without_duplicate_legacy_delivery(tmp_path):
    path, now = prepared(tmp_path)
    assert len(claim_due(path, now)["gorevler"]) == 1
    assert claim_due(path, now)["gorevler"] == []
    pending = pending_deliveries(path)
    assert len(pending) == 1 and pending[0].task == "incele"
    assert pending_deliveries(path) == pending


def test_ack_is_idempotent_and_cannot_rebind_task(tmp_path):
    path, now = prepared(tmp_path)
    claim_due(path, now)
    delivery = pending_deliveries(path)[0]
    assert acknowledge_delivery(path, delivery.occurrence_id, "task-one")
    assert pending_deliveries(path) == ()
    assert acknowledge_delivery(path, delivery.occurrence_id, "task-one")
    assert not acknowledge_delivery(path, delivery.occurrence_id, "task-other")


def test_rpc_pending_is_reachable_and_does_not_claim_compute_completed(tmp_path, monkeypatch):
    from fusion_cli.appserver import schedule

    path, now = prepared(tmp_path)
    claim_due(path, now)
    monkeypatch.setattr(schedule, "schedules_path", lambda: path)
    result = schedule.SCHEDULE_ROUTES["zamanlama.teslim_bekleyenler"]({})
    delivery = result["teslimler"][0]
    assert delivery["gorev"] == "incele"
    ack = schedule.SCHEDULE_ROUTES["zamanlama.teslim_onayla"](
        {"occurrence_id": delivery["occurrence_id"], "task_id": "queued-task"}
    )
    assert ack["ok"]


def test_failed_atomic_write_does_not_advance_without_pending(tmp_path, monkeypatch):
    from fusion_cli.appserver import schedule

    path, now = prepared(tmp_path)
    before = path.read_bytes()

    def failed_store(*args):
        raise OSError("Sahte disk yazım hatası")

    monkeypatch.setattr(schedule, "_store", failed_store)
    assert not claim_due(path, now)["ok"]
    assert path.read_bytes() == before
    assert pending_deliveries(path) == ()


def test_two_process_claims_preserve_one_due_occurrence(tmp_path):
    import json
    import subprocess
    import sys

    path, now = prepared(tmp_path)
    script = (
        "import json,sys; from datetime import datetime; "
        "from pathlib import Path; "
        "from fusion_cli.appserver.schedule import claim_due; "
        "print(json.dumps(claim_due(Path(sys.argv[1]),datetime.fromisoformat(sys.argv[2]))))"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(path), now.isoformat()],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    responses = []
    for process in processes:
        output, error = process.communicate(timeout=10)
        assert process.returncode == 0, error
        responses.append(json.loads(output))
    assert sum(len(response["gorevler"]) for response in responses) == 1
    assert len(pending_deliveries(path)) == 1


def test_existing_corrupt_store_never_looks_empty_or_gets_overwritten(tmp_path, monkeypatch):
    from fusion_cli.appserver import schedule

    path, now = prepared(tmp_path)
    for content in ("{broken", "{}", '["invalid"]'):
        path.write_text(content)
        monkeypatch.setattr(schedule, "schedules_path", lambda: path)
        assert not schedule.SCHEDULE_ROUTES["zamanlama.teslim_bekleyenler"]({})["ok"]
        result = save_schedule(
            {
                "baslik": "Yeni",
                "gorev": "incele",
                "kok": str(tmp_path),
                "tur": "aralik",
                "dakika": 15,
            },
            path,
            now,
        )
        assert not result["ok"]
        assert path.read_text() == content


def test_existing_store_read_error_is_honest_not_empty(tmp_path, monkeypatch):
    from pathlib import Path

    from fusion_cli.appserver import schedule

    path, _ = prepared(tmp_path)
    original = Path.read_text

    def denied(actual, *args, **kwargs):
        if actual == path:
            raise PermissionError("Sahte okuma engeli")
        return original(actual, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    monkeypatch.setattr(schedule, "schedules_path", lambda: path)
    assert not schedule.SCHEDULE_ROUTES["zamanlama.teslim_bekleyenler"]({})["ok"]


def test_explicit_delete_cancels_pending_but_disable_does_not_claim_execution(tmp_path):
    from fusion_cli.appserver.schedule import delete_schedule, set_enabled

    path, now = prepared(tmp_path)
    claimed = claim_due(path, now)["gorevler"][0]
    assert set_enabled({"id": claimed["id"], "etkin": False}, path, now)["ok"]
    assert len(pending_deliveries(path)) == 1
    assert delete_schedule({"id": claimed["id"]}, path)["ok"]
    assert pending_deliveries(path) == ()


def test_nested_corrupt_outbox_blocks_all_schedule_mutations(tmp_path):
    import json

    from fusion_cli.appserver import schedule

    path, now = prepared(tmp_path)
    items = json.loads(path.read_text())
    identifier = items[0]["id"]
    items[0]["teslimler"] = [{"task_id": "partial-corrupt"}]
    path.write_text(json.dumps(items))
    original = path.read_bytes()
    assert not schedule.claim_due(path, now)["ok"]
    assert not schedule.set_enabled({"id": identifier, "etkin": False}, path, now)["ok"]
    assert not schedule.run_now({"id": identifier}, path, now)["ok"]
    assert not schedule.delete_schedule({"id": identifier}, path)["ok"]
    assert not save_schedule(
        {"baslik": "Yeni", "gorev": "incele", "kok": str(tmp_path), "tur": "aralik", "dakika": 15},
        path,
        now,
    )["ok"]
    assert path.read_bytes() == original


def test_ack_lock_failure_returns_honest_rpc_error(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from fusion_cli.appserver import schedule, schedule_delivery

    path, now = prepared(tmp_path)
    claim_due(path, now)
    delivery = pending_deliveries(path)[0]

    @contextmanager
    def failed_lock(path):
        raise PermissionError("Sahte kilit engeli")
        yield

    monkeypatch.setattr(schedule_delivery, "store_lock", failed_lock)
    monkeypatch.setattr(schedule, "schedules_path", lambda: path)
    result = schedule.SCHEDULE_ROUTES["zamanlama.teslim_onayla"](
        {"occurrence_id": delivery.occurrence_id, "task_id": "queued"}
    )
    assert not result["ok"]
    assert len(pending_deliveries(path)) == 1


def test_invalid_utf8_outbox_is_preserved_with_honest_error(tmp_path, monkeypatch):
    from fusion_cli.appserver import schedule

    path, now = prepared(tmp_path)
    content = b"\xff\xfeinvalid"
    path.write_bytes(content)
    monkeypatch.setattr(schedule, "schedules_path", lambda: path)
    assert not schedule.SCHEDULE_ROUTES["zamanlama.teslim_bekleyenler"]({})["ok"]
    assert not save_schedule(
        {"baslik": "Yeni", "gorev": "incele", "kok": str(tmp_path), "tur": "aralik", "dakika": 15},
        path,
        now,
    )["ok"]
    assert path.read_bytes() == content
