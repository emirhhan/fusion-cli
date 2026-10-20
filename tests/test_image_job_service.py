"""Görsel işinin kabul, sahiplik, iptal ve güncel çıktı servis sözleşmesi."""

from __future__ import annotations

import asyncio

from PIL import Image

from fusion_cli.appserver.image_jobs import ImageJobService
from fusion_cli.core.submission import SubmissionKey
from fusion_cli.memory.image_job_store import ImageJobStore


def _key(root):
    return SubmissionKey("offline", str(root), "conversation", "image:request-1")


def _output(root):
    path = root / "image.png"
    Image.new("RGB", (12, 7), "blue").save(path)
    return {"ok": True, "saglayici": "offline", "dosyalar": [{"yol": str(path)}]}


async def _terminal(service, key):
    async with asyncio.timeout(3):
        while True:
            result = await service.status(key)
            if result.get("state") not in {"accepted", "running"}:
                return result


async def test_image_job_duplicate_ack_has_one_render_and_observed_output(tmp_path):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def render():
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return _output(tmp_path)

    try:
        first = await service.start(_key(tmp_path), "a" * 64, render)
        await entered.wait()
        duplicate = await service.start(_key(tmp_path), "a" * 64, render)
        assert first["jobId"] == duplicate["jobId"] and calls == 1
        conflict = await service.start(_key(tmp_path), "b" * 64, render)
        assert conflict["ok"] is False and calls == 1
        release.set()
        completed = await _terminal(service, _key(tmp_path))
        assert completed["ok"] and completed["state"] == "completed"
        assert completed["dosyalar"][0]["genislik"] == 12
        assert completed["dosyalar"][0]["yukseklik"] == 7
    finally:
        release.set()
        await service.close()
        await store.close()


async def test_image_job_cancel_waits_for_cleanup_and_duplicate_cancel_does_not_interrupt_it(
    tmp_path,
):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)
    entered, cleaning, release, cleaned = (asyncio.Event() for _ in range(4))

    async def render():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            cleaned.set()

    tasks = []
    try:
        await service.start(_key(tmp_path), "a" * 64, render)
        await entered.wait()
        tasks.append(asyncio.create_task(service.cancel(_key(tmp_path))))
        await asyncio.wait_for(cleaning.wait(), 2)
        assert not tasks[0].done()
        tasks.append(asyncio.create_task(service.cancel(_key(tmp_path))))
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(*tasks)
        assert cleaned.is_set() and all(result["state"] == "cancelled" for result in results)
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await service.close()
        await store.close()


async def test_start_caller_cancellation_does_not_cancel_accepted_job(tmp_path, monkeypatch):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)
    claimed, admit, rendered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = store.claim_image

    async def blocked_claim(*args):
        result = await original(*args)
        claimed.set()
        await admit.wait()
        return result

    async def render():
        rendered.set()
        return _output(tmp_path)

    monkeypatch.setattr(store, "claim_image", blocked_claim)
    task = asyncio.create_task(service.start(_key(tmp_path), "a" * 64, render))
    try:
        await claimed.wait()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        admit.set()
        await asyncio.wait_for(rendered.wait(), 2)
        assert (await _terminal(service, _key(tmp_path)))["state"] == "completed"
    finally:
        admit.set()
        await service.close()
        await store.close()


async def test_completed_job_reload_checks_current_files_without_provider_retry(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    store = ImageJobStore(path)
    service = ImageJobService(store, tmp_path)

    async def render():
        return _output(tmp_path)

    try:
        await service.start(_key(tmp_path), "a" * 64, render)
        assert (await _terminal(service, _key(tmp_path)))["state"] == "completed"
    finally:
        await service.close()
        await store.close()
    reopened = ImageJobStore(path)
    service = ImageJobService(reopened, tmp_path)
    calls = 0

    async def forbidden_render():
        nonlocal calls
        calls += 1
        raise AssertionError("tamamlanmış iş yeniden üretilemez")

    try:
        assert (await service.start(_key(tmp_path), "a" * 64, forbidden_render))[
            "state"
        ] == "completed"
        (tmp_path / "image.png").unlink()
        missing = await service.status(_key(tmp_path))
        assert not missing["ok"] and missing["code"] == "artifact_changed" and calls == 0
    finally:
        await service.close()
        await reopened.close()


async def test_provider_error_message_is_not_persisted_or_returned(tmp_path):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)
    sentinel = "synthetic-provider-credential"

    async def render():
        raise RuntimeError(sentinel)

    try:
        await service.start(_key(tmp_path), "a" * 64, render)
        result = await _terminal(service, _key(tmp_path))
        assert not result["ok"] and result["state"] == "failed"
        assert sentinel not in str(result)
        assert sentinel not in str(await store.lookup_image(_key(tmp_path)))
    finally:
        await service.close()
        await store.close()


async def test_close_finishes_accepted_admission_without_starting_provider(tmp_path, monkeypatch):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)
    claimed, release = asyncio.Event(), asyncio.Event()
    original = store.claim_image
    calls = 0

    async def blocked_claim(*args):
        record = await original(*args)
        claimed.set()
        await release.wait()
        return record

    async def render():
        nonlocal calls
        calls += 1
        return _output(tmp_path)

    monkeypatch.setattr(store, "claim_image", blocked_claim)
    start = asyncio.create_task(service.start(_key(tmp_path), "a" * 64, render))
    try:
        await claimed.wait()
        await asyncio.wait_for(service.close(), 2)
        await asyncio.gather(start, return_exceptions=True)
        assert calls == 0
        assert (await service.status(_key(tmp_path)))["state"] == "cancelled"
        assert not (await service.start(_key(tmp_path), "a" * 64, render))["ok"]
    finally:
        release.set()
        await service.close()
        await store.close()


async def test_cancel_after_completion_commit_keeps_completed_receipt(tmp_path, monkeypatch):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)
    committed, release = asyncio.Event(), asyncio.Event()
    original = store.finish_image

    async def committed_then_block(*args, **kwargs):
        result = await original(*args, **kwargs)
        if kwargs["state"] == "completed":
            committed.set()
            await release.wait()
        return result

    async def render():
        return _output(tmp_path)

    monkeypatch.setattr(store, "finish_image", committed_then_block)
    try:
        await service.start(_key(tmp_path), "a" * 64, render)
        await asyncio.wait_for(committed.wait(), 2)
        result = await service.cancel(_key(tmp_path))
        assert result["ok"] and result["state"] == "completed" and result["dosyalar"]
    finally:
        release.set()
        await service.close()
        await store.close()


async def test_storage_loss_after_render_is_recovery_required_and_never_replays_provider(
    tmp_path, monkeypatch
):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)
    calls = 0

    async def broken_finish(*args, **kwargs):
        raise OSError("sentetik depo hatası")

    async def render():
        nonlocal calls
        calls += 1
        return _output(tmp_path)

    monkeypatch.setattr(store, "finish_image", broken_finish)
    try:
        await service.start(_key(tmp_path), "a" * 64, render)
        result = await _terminal(service, _key(tmp_path))
        assert not result["ok"] and result["state"] == "recoveryRequired"
        assert not (await service.start(_key(tmp_path), "a" * 64, render))["ok"]
        assert calls == 1
    finally:
        await service.close()
        await store.close()


async def test_provider_swallowing_cancel_cannot_publish_completed_job(tmp_path):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)
    entered = asyncio.Event()

    async def render():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return _output(tmp_path)

    try:
        await service.start(_key(tmp_path), "a" * 64, render)
        await entered.wait()
        result = await service.cancel(_key(tmp_path))
        assert not result["ok"] and result["state"] == "cancelled"
    finally:
        await service.close()
        await store.close()


async def test_provider_rejected_result_is_not_reported_as_storage_failure(tmp_path):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    service = ImageJobService(store, tmp_path)

    async def render():
        return {"ok": False, "metin": "private-provider-detail"}

    try:
        await service.start(_key(tmp_path), "a" * 64, render)
        result = await _terminal(service, _key(tmp_path))
        assert result["code"] == "provider_failed"
        assert "private-provider-detail" not in str(result)
    finally:
        await service.close()
        await store.close()
