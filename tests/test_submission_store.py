"""Makbuz indeksi için namespace, atomik claim ve kurtarma sözleşmesi."""

from __future__ import annotations

import asyncio

import pytest


def _store(tmp_path):
    from fusion_cli.memory.submission_store import SubmissionStore

    return SubmissionStore(tmp_path / "makbuz.sqlite3")


def _key(profile="profil", root="/proje", conversation="sohbet"):
    from fusion_cli.core.submission import SubmissionKey

    return SubmissionKey(
        profile_id=profile, root=root, conversation_id=conversation, request_id="istek"
    )


async def test_concurrent_claim_yalniz_bir_sahip_uretir(tmp_path):
    store = _store(tmp_path)
    first, second = await asyncio.gather(store.claim(_key()), store.claim(_key()))
    assert sum(result.is_owner for result in (first, second)) == 1
    assert first.receipt == second.receipt


@pytest.mark.parametrize("dimension", ["profile", "root", "conversation"])
async def test_namespace_ayri_claim_uretir(tmp_path, dimension):
    store = _store(tmp_path)
    first = await store.claim(_key())
    second = await store.claim(_key(**{dimension: "başka"}))
    assert first.is_owner and second.is_owner
    assert first.receipt.key != second.receipt.key


async def test_restart_unfinished_makbuz_kurtarma_ister(tmp_path):
    first_store = _store(tmp_path)
    first = await first_store.claim(_key())
    await first_store.finish(first.receipt, state="running")
    await first_store.close()
    second = await _store(tmp_path).claim(_key())
    assert first.is_owner
    assert not second.is_owner
    assert second.receipt.state.value == "recoveryRequired"


async def test_failed_duplicate_yeni_attempt_acmaz(tmp_path):
    store = _store(tmp_path)
    first = await store.claim(_key())
    await store.finish(first.receipt, state="failed", error_code="executor_failed")
    duplicate = await store.claim(_key())
    assert not duplicate.is_owner
    assert duplicate.receipt.state.value == "failed"
    assert duplicate.receipt.attempt_id == first.receipt.attempt_id


async def test_canli_owner_yeni_adapter_acilisinda_kurtarmaya_donmez(tmp_path):
    first_store = _store(tmp_path)
    first = await first_store.claim(_key())
    duplicate = await _store(tmp_path).claim(_key())
    assert first.is_owner
    assert not duplicate.is_owner
    assert duplicate.receipt.state.value == "accepted"
    await first_store.finish(first.receipt, state="running")
    await first_store.close()
    restored = await _store(tmp_path).claim(_key())
    assert not restored.is_owner
    assert restored.receipt.state.value == "recoveryRequired"


async def test_explicit_retry_eski_attempt_final_ile_ezilmez(tmp_path):
    store = _store(tmp_path)
    first = await store.claim(_key())
    await store.finish(first.receipt, state="failed", error_code="no_tool_effect")
    second = await store.retry(_key())
    assert second.is_owner
    assert second.receipt.attempt_id != first.receipt.attempt_id
    late = await store.finish(first.receipt, state="completed")
    assert late.attempt_id == second.receipt.attempt_id
    assert late.state.value == "accepted"
    assert (await store.lookup(_key())) == second.receipt


async def test_recovery_explicit_retry_ile_otomatik_yurutulmez(tmp_path):
    store = _store(tmp_path)
    claim = await store.claim(_key())
    await store.finish(claim.receipt, state="running")
    await store.close()
    retry = await _store(tmp_path).retry(_key())
    assert not retry.is_owner
    assert retry.receipt.state.value == "recoveryRequired"


async def test_makbuz_metadata_icerik_tasiyamaz_ve_sohbet_omrune_baglidir(tmp_path):
    store = _store(tmp_path)
    first = await store.claim(_key())
    await store.finish(first.receipt, state="completed")
    await store.move_conversation("profil", "/proje", "sohbet", "/hedef")
    assert await store.lookup(_key()) is None
    moved = await store.lookup(_key(root="/hedef"))
    assert moved is not None and moved.state.value == "completed"
    await store.delete_conversation("profil", "/hedef", "sohbet")
    assert await store.lookup(_key(root="/hedef")) is None
    assert b"prompt" not in (tmp_path / "makbuz.sqlite3").read_bytes()
    assert b"final_text" not in (tmp_path / "makbuz.sqlite3").read_bytes()


async def test_belirsiz_executor_hatasi_explicit_retry_ile_yinelenmez(tmp_path):
    store = _store(tmp_path)
    first = await store.claim(_key())
    await store.finish(first.receipt, state="failed", error_code="executor_failed")
    retry = await store.retry(_key())
    assert not retry.is_owner
    assert retry.receipt.attempt_id == first.receipt.attempt_id


async def test_close_gercek_claim_thread_commit_bariyerini_drain_eder(tmp_path, monkeypatch):
    from threading import Event

    store = _store(tmp_path)
    entered = Event()
    release = Event()
    epoch = store._epoch

    def blocked_epoch():
        value = epoch()
        entered.set()
        assert release.wait(5)
        return value

    monkeypatch.setattr(store, "_epoch", blocked_epoch)
    claim = asyncio.create_task(store.claim(_key()))
    assert await asyncio.to_thread(entered.wait, 5)
    claim.cancel()
    with pytest.raises(asyncio.CancelledError):
        await claim
    closing = asyncio.create_task(store.close())
    await asyncio.sleep(0.02)
    assert not closing.done()
    release.set()
    await closing
    fresh = _store(tmp_path)
    receipt = await fresh.lookup(_key())
    assert receipt.state.value == "cancelled"
    assert receipt.error_code == "before_execution_failed"
    assert (await fresh.retry(_key())).is_owner


@pytest.mark.parametrize(
    "state,error_code", [("failed", "no_tool_effect"), ("cancelled", "before_execution_failed")]
)
async def test_pending_move_explicit_retry_makbuzu_degistirmez_cleanup_kurtarilir(
    tmp_path, state, error_code
):
    store = _store(tmp_path)
    source = _key()
    target = _key(root="/hedef")
    first = await store.claim(source)
    failed = await store.finish(first.receipt, state=state, error_code=error_code)
    await store.prepare_move("profil", "/proje", "sohbet", "/hedef")
    before = await store.lookup(target)
    retry = await store.retry(target)
    assert not retry.is_owner
    assert retry.receipt == before
    assert await store.lookup(target) == before
    assert retry.receipt.attempt_id == failed.attempt_id
    await store.move_conversation("profil", "/proje", "sohbet", "/hedef")
    assert await store.lookup(source) is None
    assert not await store.move_prepared("profil", "/proje", "sohbet", "/hedef")
    after = await store.retry(target)
    assert after.is_owner
    assert after.receipt.attempt_id != before.attempt_id
