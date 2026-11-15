"""İşçi ömür kilidi: canlı işçi nabzı bayatlasa da "yarım kaldı" sayılmaz (P-048)."""

from __future__ import annotations

import os
from pathlib import Path

from fusion_cli.cli import background_worker
from fusion_cli.core.background_store import BackgroundTaskStore
from fusion_cli.core.background_tasks import (
    HEARTBEAT_FILE,
    STALE_AFTER_S,
    WORKER_LOCK_FILE,
    InboxMessage,
    TaskStatus,
)
from fusion_cli.core.file_lease import FileLease
from fusion_cli.core.types import Message
from fusion_cli.tools import agent_tasks


class FakeClock:
    def __init__(self, now: float = 10_000.0) -> None:
        self.value = now

    def now(self) -> float:
        return self.value

    def monotonic(self) -> float:
        return self.value


def _stale_working(tmp_path: Path) -> tuple[BackgroundTaskStore, str, FakeClock]:
    clock = FakeClock()
    store = BackgroundTaskStore(tmp_path / "arka-plan", clock)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.WORKING)
    store.heartbeat(task.id)
    clock.value += STALE_AFTER_S + 60
    old = clock.value - STALE_AFTER_S - 5
    os.utime(store.task_dir(task.id) / HEARTBEAT_FILE, (old, old))
    return store, task.id, clock


def test_kilidi_tutan_isci_nabzi_bayatlasa_da_calisiyor_gorunur(tmp_path):
    # Ölçüldü (31 Ekim): uyku/uzun blok sonrası nabız bayatlayınca canlı işçi LOST
    # sayılıyor, gelen mesaj ikinci bir işçi başlatıyordu (iki işçi aynı kayıtta).
    store, task_id, _clock = _stale_working(tmp_path)
    lease = FileLease(store.task_dir(task_id) / WORKER_LOCK_FILE)
    assert lease.try_acquire()
    try:
        assert store.get(task_id).status is TaskStatus.WORKING
        assert store.append_inbox(task_id, InboxMessage("devam", "k", 1.0)) is False
    finally:
        lease.close()


def test_kilidi_birakilan_gorev_nabiz_taze_olsa_da_yarim_kalir(tmp_path):
    clock = FakeClock()
    store = BackgroundTaskStore(tmp_path / "arka-plan", clock)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.WORKING)
    store.heartbeat(task.id)
    lease = FileLease(store.task_dir(task.id) / WORKER_LOCK_FILE)
    assert lease.try_acquire()
    lease.close()  # işçi öldü: işletim sistemi kilidi bıraktı

    assert store.get(task.id).status is TaskStatus.LOST


def test_eski_kayitta_kilit_dosyasi_yoksa_nabiz_kurali_gecerli(tmp_path):
    store, task_id, _clock = _stale_working(tmp_path)
    assert store.get(task_id).status is TaskStatus.LOST


async def test_kilit_baska_iscideyken_ikinci_isci_calismaz(tmp_path, monkeypatch):
    monkeypatch.setattr(background_worker, "_LEASE_WAIT_S", 0.05)
    store = agent_tasks.task_store(tmp_path)
    task = store.create("ilk iş", root=tmp_path)
    lease = FileLease(store.task_dir(task.id) / WORKER_LOCK_FILE)
    assert lease.try_acquire()
    calls: list[str] = []

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        calls.append(prompt)
        return "bitti", True

    try:
        assert await background_worker.run_task_loop(store, task.id, _turn) == 0
    finally:
        lease.close()
    assert calls == []
    assert store.get(task.id).status is TaskStatus.QUEUED


async def test_isci_bitince_kilidi_birakir(tmp_path):
    store = agent_tasks.task_store(tmp_path)
    task = store.create("iş", root=tmp_path)

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        assert not FileLease(store.task_dir(task.id) / WORKER_LOCK_FILE).try_acquire()
        return "bitti", True

    assert await background_worker.run_task_loop(store, task.id, _turn) == 0
    probe = FileLease(store.task_dir(task.id) / WORKER_LOCK_FILE)
    assert probe.try_acquire()
    probe.close()
