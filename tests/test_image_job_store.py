"""Görsel işi mevcut gönderim otoritesinde tek kabul ve kalıcı çıktı taşır."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from contextlib import closing
from dataclasses import replace

import pytest

from fusion_cli.core.image_jobs import ImageJobConflictError, ImageOutputReceipt
from fusion_cli.core.submission import SubmissionKey, SubmissionState
from fusion_cli.memory.image_job_store import ImageJobStore


def _key(root, request="image:request-1"):
    return SubmissionKey("offline-profile", str(root), "conversation", request)


def _output(root):
    return ImageOutputReceipt(str(root / "image.png"), 512, 512, "a" * 64, "offline")


async def test_parallel_image_claim_has_one_owner_and_changed_input_is_rejected(tmp_path):
    stores = [ImageJobStore(tmp_path / "submissions.sqlite3") for _ in range(2)]
    try:
        claims = await asyncio.gather(
            *(store.claim_image(_key(tmp_path), "b" * 64) for store in stores)
        )
        assert sum(claim.is_owner for claim in claims) == 1
        assert claims[0].record.receipt == claims[1].record.receipt
        with pytest.raises(ImageJobConflictError):
            await stores[0].claim_image(_key(tmp_path), "c" * 64)
    finally:
        await asyncio.gather(*(store.close() for store in stores))


async def test_image_completion_and_outputs_survive_reload_without_second_execution(tmp_path):
    store = ImageJobStore(tmp_path / "submissions.sqlite3")
    claim = await store.claim_image(_key(tmp_path), "b" * 64)
    output = _output(tmp_path)
    try:
        result = await store.finish_image(
            claim.record.receipt, state="completed", outputs=(output,)
        )
        assert result.receipt.state is SubmissionState.COMPLETED
        assert result.outputs == (output,)
        duplicate = await store.claim_image(_key(tmp_path), "b" * 64)
        assert not duplicate.is_owner and duplicate.record == result
    finally:
        await store.close()
    reloaded = ImageJobStore(tmp_path / "submissions.sqlite3")
    try:
        assert await reloaded.lookup_image(_key(tmp_path)) == result
    finally:
        await reloaded.close()


async def test_stale_terminal_receipt_cannot_change_image_outputs(tmp_path):
    store = ImageJobStore(tmp_path / "submissions.sqlite3")
    try:
        claim = await store.claim_image(_key(tmp_path), "b" * 64)
        output = _output(tmp_path)
        completed = await store.finish_image(
            claim.record.receipt, state="completed", outputs=(output,)
        )
        with pytest.raises(ImageJobConflictError):
            await store.finish_image(
                claim.record.receipt, state="completed", outputs=(replace(output, digest="d" * 64),)
            )
        assert await store.lookup_image(_key(tmp_path)) == completed
    finally:
        await store.close()


async def test_running_image_after_owner_close_requires_recovery_not_provider_retry(tmp_path):
    path = tmp_path / "submissions.sqlite3"
    original = ImageJobStore(path)
    claim = await original.claim_image(_key(tmp_path), "b" * 64)
    await original.finish(claim.record.receipt, state="running")
    await original.close()
    restarted = ImageJobStore(path)
    try:
        record = await restarted.lookup_image(_key(tmp_path))
        assert record.receipt.state is SubmissionState.RECOVERY_REQUIRED
        duplicate = await restarted.claim_image(_key(tmp_path), "b" * 64)
        assert not duplicate.is_owner and duplicate.record.outputs == ()
    finally:
        await restarted.close()


async def test_image_metadata_moves_and_deletes_with_existing_conversation_transaction(tmp_path):
    store = ImageJobStore(tmp_path / "submissions.sqlite3")
    key = _key(tmp_path / "first")
    target = str(tmp_path / "second")
    try:
        claim = await store.claim_image(key, "b" * 64)
        await store.finish_image(
            claim.record.receipt, state="completed", outputs=(_output(tmp_path),)
        )
        await store.move_conversation(key.profile_id, key.root, key.conversation_id, target)
        moved_key = replace(key, root=target)
        assert await store.lookup_image(key) is None
        assert (await store.lookup_image(moved_key)).outputs == (_output(tmp_path),)
        await store.delete_conversation(key.profile_id, target, key.conversation_id)
        assert await store.lookup_image(moved_key) is None
    finally:
        await store.close()


async def test_failed_output_commit_rolls_back_terminal_submission_marker(tmp_path, monkeypatch):
    store = ImageJobStore(tmp_path / "submissions.sqlite3")
    claim = await store.claim_image(_key(tmp_path), "b" * 64)
    original_connect = store._connect

    class FailOutputCommit:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def close(self):
            self.connection.close()

        def execute(self, sql, args=()):
            if sql.startswith("UPDATE image_jobs SET outputs"):
                raise OSError("kontrollü metadata commit hatası")
            return self.connection.execute(sql, args)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(store, "_connect", lambda: FailOutputCommit(original_connect()))
            with pytest.raises(OSError, match="kontrollü metadata"):
                await store.finish_image(
                    claim.record.receipt, state="completed", outputs=(_output(tmp_path),)
                )
        unchanged = await store.lookup_image(_key(tmp_path))
        assert unchanged.receipt.state is SubmissionState.ACCEPTED and unchanged.outputs == ()
    finally:
        await store.close()


async def test_active_image_cannot_be_moved_or_deleted_and_move_rolls_back(tmp_path):
    store = ImageJobStore(tmp_path / "submissions.sqlite3")
    key = _key(tmp_path)
    target = str(tmp_path / "other")
    try:
        claim = await store.claim_image(key, "b" * 64)
        with pytest.raises(ImageJobConflictError):
            await store.move_conversation(key.profile_id, key.root, key.conversation_id, target)
        with pytest.raises(ImageJobConflictError):
            await store.delete_conversation(key.profile_id, key.root, key.conversation_id)
        assert await store.lookup_image(key) == claim.record
        assert await store.lookup_image(replace(key, root=target)) is None
        assert not await store.move_prepared(key.profile_id, key.root, key.conversation_id, target)
    finally:
        await store.close()


async def test_future_image_metadata_is_not_overwritten_on_replay(tmp_path):
    path = tmp_path / "submissions.sqlite3"
    store = ImageJobStore(path)
    key = _key(tmp_path)
    try:
        await store.claim_image(key, "b" * 64)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("UPDATE image_jobs SET schema_version=999")
        with pytest.raises(ImageJobConflictError):
            await store.claim_image(key, "b" * 64)
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("SELECT schema_version FROM image_jobs").fetchone() == (999,)
    finally:
        await store.close()


async def test_another_live_store_cannot_finish_owner_image(tmp_path):
    path = tmp_path / "submissions.sqlite3"
    owner, stranger = ImageJobStore(path), ImageJobStore(path)
    try:
        claim = await owner.claim_image(_key(tmp_path), "b" * 64)
        with pytest.raises(ImageJobConflictError):
            await stranger.finish_image(
                claim.record.receipt, state="completed", outputs=(_output(tmp_path),)
            )
        assert (await owner.lookup_image(_key(tmp_path))).receipt.state is SubmissionState.ACCEPTED
    finally:
        await asyncio.gather(owner.close(), stranger.close())


async def test_another_live_store_cannot_mark_image_running(tmp_path):
    path = tmp_path / "submissions.sqlite3"
    owner, stranger = ImageJobStore(path), ImageJobStore(path)
    try:
        claim = await owner.claim_image(_key(tmp_path), "b" * 64)
        with pytest.raises(ImageJobConflictError):
            await stranger.finish(claim.record.receipt, state="running")
        assert (await owner.lookup_image(_key(tmp_path))).receipt.state is SubmissionState.ACCEPTED
    finally:
        await asyncio.gather(owner.close(), stranger.close())


async def test_generic_agent_claim_and_retry_cannot_repurpose_image_namespace(tmp_path):
    path = tmp_path / "submissions.sqlite3"
    owner = ImageJobStore(path)
    key = _key(tmp_path)
    try:
        await owner.claim_image(key, "b" * 64)
        with pytest.raises(ImageJobConflictError):
            await owner.claim(key)
    finally:
        await owner.close()
    restarted = ImageJobStore(path)
    try:
        with pytest.raises(ImageJobConflictError):
            await restarted.retry(key)
        assert (await restarted.lookup_image(key)).receipt.state is SubmissionState.CANCELLED
    finally:
        await restarted.close()


async def test_delete_guard_and_delete_exclude_concurrent_image_admission(tmp_path, monkeypatch):
    path = tmp_path / "submissions.sqlite3"
    deleter, claimant = ImageJobStore(path), ImageJobStore(path)
    key = _key(tmp_path)
    claim = await deleter.claim_image(key, "b" * 64)
    await deleter.finish_image(
        claim.record.receipt, state="completed", outputs=(_output(tmp_path),)
    )
    deleting, attempting, release = threading.Event(), threading.Event(), threading.Event()

    class BoundaryConnection:
        def __init__(self, connection, deletion):
            self.connection, self.deletion = connection, deletion

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def close(self):
            self.connection.close()

        def execute(self, sql, args=()):
            if self.deletion and sql.startswith("DELETE FROM image_jobs"):
                deleting.set()
                assert release.wait(5), "test silme sınırını serbest bırakmadı"
            if not self.deletion and sql == "BEGIN IMMEDIATE":
                attempting.set()
            return self.connection.execute(sql, args)

    original_delete, original_claim = deleter._connect, claimant._connect
    delete_task = claim_task = None
    try:
        with monkeypatch.context() as patch:
            patch.setattr(deleter, "_connect", lambda: BoundaryConnection(original_delete(), True))
            patch.setattr(claimant, "_connect", lambda: BoundaryConnection(original_claim(), False))
            delete_task = asyncio.create_task(
                deleter.delete_conversation(key.profile_id, key.root, key.conversation_id)
            )
            assert await asyncio.to_thread(deleting.wait, 2)
            claim_task = asyncio.create_task(
                claimant.claim_image(replace(key, request_id="image:concurrent"), "c" * 64)
            )
            try:
                assert await asyncio.to_thread(attempting.wait, 2)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(claim_task), 0.1)
            finally:
                release.set()
                await asyncio.gather(delete_task, claim_task, return_exceptions=True)
        assert (
            await claimant.lookup_image(replace(key, request_id="image:concurrent"))
        ) is not None
    finally:
        release.set()
        await asyncio.gather(
            *(task for task in (delete_task, claim_task) if task is not None),
            return_exceptions=True,
        )
        await asyncio.gather(deleter.close(), claimant.close())


@pytest.mark.parametrize("bad", ["error_on_success", "duplicate_path", "generic_terminal"])
async def test_inconsistent_image_completion_never_becomes_terminal_success(tmp_path, bad):
    store = ImageJobStore(tmp_path / "submissions.sqlite3")
    try:
        claim = await store.claim_image(_key(tmp_path), "b" * 64)
        with pytest.raises(ImageJobConflictError):
            if bad == "generic_terminal":
                await store.finish(claim.record.receipt, state="completed")
            else:
                output = _output(tmp_path)
                await store.finish_image(
                    claim.record.receipt,
                    state="completed",
                    outputs=(output, output) if bad == "duplicate_path" else (output,),
                    error_code="provider_failed" if bad == "error_on_success" else None,
                )
        assert (await store.lookup_image(_key(tmp_path))).receipt.state is SubmissionState.ACCEPTED
    finally:
        await store.close()


async def test_image_job_listing_is_scoped_paged_and_survives_reopen(tmp_path):
    store = ImageJobStore(tmp_path / "jobs.sqlite3")
    scope = _key(tmp_path)
    try:
        for name in ("image:a", "image:b", "image:c"):
            await store.claim_image(replace(scope, request_id=name), "a" * 64)
        await store.claim_image(
            replace(scope, conversation_id="other", request_id="image:x"), "a" * 64
        )
        await store.claim(replace(scope, request_id="agent-request"))
        first, cursor = await store.list_images(scope, limit=2)
        assert [record.receipt.key.request_id for record in first] == ["image:a", "image:b"]
        assert cursor == "image:b"
        second, cursor = await store.list_images(scope, after=cursor, limit=2)
        assert [record.receipt.key.request_id for record in second] == ["image:c"]
        assert cursor is None
    finally:
        await store.close()
    reopened = ImageJobStore(tmp_path / "jobs.sqlite3")
    try:
        records, _ = await reopened.list_images(scope)
        assert len(records) == 3
    finally:
        await reopened.close()
