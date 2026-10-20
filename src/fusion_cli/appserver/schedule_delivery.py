"""Yerel vade teslimlerini takvim kaydı içinde ack gelene kadar korur."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path

DELIVERY_FIELD = "teslimler"


@dataclass(frozen=True, slots=True)
class ScheduleDelivery:
    """Task kimliği kuyruğa teslim ack'idir; hesaplamanın tamamlandığı iddiası değil."""

    occurrence_id: str
    schedule_id: str
    due_at: float
    title: str
    task: str
    root: str
    task_id: str | None = None


def add_delivery(item: Mapping[str, object], due_at: float) -> dict[str, object]:
    """Aynı vade kimliği tekrar eklenmez; takvimle aynı atomic yazıma katılır."""
    identifier = item.get("id")
    title, task, root = item.get("baslik"), item.get("gorev"), item.get("kok")
    if not all(isinstance(value, str) and value for value in (identifier, title, task, root)):
        raise ValueError("Teslim için görev kimliği ve bağlamı gerekli.")
    assert isinstance(identifier, str) and isinstance(title, str)
    assert isinstance(task, str) and isinstance(root, str)
    occurrence = hashlib.sha256(json.dumps([identifier, due_at]).encode()).hexdigest()
    deliveries = _records(item)
    for delivery in deliveries:
        if delivery.occurrence_id == occurrence and (
            delivery.schedule_id != identifier or delivery.task != task or delivery.root != root
        ):
            raise ValueError("Aynı vade farklı görev veya çalışma alanına bağlanamaz.")
    if not any(delivery.occurrence_id == occurrence for delivery in deliveries):
        deliveries = (
            *deliveries,
            ScheduleDelivery(occurrence, identifier, due_at, title, task, root),
        )
    return {**item, DELIVERY_FIELD: [asdict(delivery) for delivery in deliveries]}


def _records(item: Mapping[str, object]) -> tuple[ScheduleDelivery, ...]:
    value = item.get(DELIVERY_FIELD, [])
    if not isinstance(value, list):
        raise ValueError("Kalıcı teslim listesi geçersiz.")
    parsed = []
    for record in value:
        if not isinstance(record, dict) or set(record) != set(
            ScheduleDelivery.__dataclass_fields__
        ):
            raise ValueError("Kalıcı teslim kaydı geçersiz.")
        for key in ("occurrence_id", "schedule_id", "title", "task", "root"):
            if not isinstance(record[key], str) or not record[key]:
                raise ValueError("Kalıcı teslim bağlamı geçersiz.")
        due = record["due_at"]
        if type(due) not in (int, float) or not math.isfinite(due):
            raise ValueError("Kalıcı teslim vadesi geçersiz.")
        if record["task_id"] is not None and (
            not isinstance(record["task_id"], str) or not record["task_id"]
        ):
            raise ValueError("Kalıcı teslim task kimliği geçersiz.")
        parsed.append(ScheduleDelivery(**record))
    return tuple(parsed)


def validate_deliveries(item: Mapping[str, object]) -> None:
    """İç outbox bozuksa takvim değişikliği dahil hiçbir yazmaya izin verme."""
    _records(item)


def pending_deliveries(path: Path) -> tuple[ScheduleDelivery, ...]:
    from .schedule import _load

    return tuple(
        delivery for item in _load(path) for delivery in _records(item) if delivery.task_id is None
    )


def acknowledge_delivery(path: Path, occurrence_id: str, task_id: str) -> bool:
    """Aynı task ack'i idempotent; başka task'a yeniden bağlama reddedilir."""
    from .schedule import _load, _store

    if not occurrence_id or not task_id:
        return False
    with store_lock(path):
        items = _load(path)
        for index, item in enumerate(items):
            deliveries = _records(item)
            for delivery in deliveries:
                if delivery.occurrence_id != occurrence_id:
                    continue
                if delivery.task_id is not None:
                    return delivery.task_id == task_id
                items[index] = {
                    **item,
                    DELIVERY_FIELD: [
                        asdict(replace(entry, task_id=task_id))
                        if entry == delivery
                        else asdict(entry)
                        for entry in deliveries
                    ],
                }
                _store(path, items)
                return True
    return False


@contextmanager
def store_lock(path: Path) -> Iterator[None]:
    """Aynı yerel takvimin süreçler arası read-modify-write işlemini sırala."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+b") as lock:
        if sys.platform == "win32":
            import msvcrt

            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
