"""Arka plan görev deposu ve başlatma yardımcıları (P-048)."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from fusion_cli.core.background_store import BackgroundTaskStore
from fusion_cli.core.background_tasks import (
    HEARTBEAT_FILE,
    STALE_AFTER_S,
    BackgroundTaskError,
    InboxMessage,
    TaskStatus,
    normalize_name,
)
from fusion_cli.tools import agent_tasks


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.value = now

    def now(self) -> float:
        return self.value

    def monotonic(self) -> float:
        return self.value


def _store(tmp_path: Path, clock: FakeClock | None = None) -> BackgroundTaskStore:
    ids = (f"{n:x}0000000" for n in itertools.count(0xA))
    return BackgroundTaskStore(
        tmp_path / "arka-plan", clock or FakeClock(), new_id=lambda: next(ids)
    )


def _message(text: str = "devam et") -> InboxMessage:
    return InboxMessage(text=text, sender="test", sent_at=1.0)


def test_gorev_olusturulur_listelenir_ve_ad_ile_bulunur(tmp_path):
    store = _store(tmp_path)
    first = store.create("testleri yaz", root=tmp_path, name="Test Yazıcı")
    second = store.create("belgeyi güncelle", root=tmp_path)

    assert first.status is TaskStatus.QUEUED
    assert first.name == "test-yazıcı"
    assert second.name == f"gorev-{second.id[:4]}"
    assert store.resolve("test-yazıcı").id == first.id
    assert store.resolve(second.id[:4]).id == second.id
    assert {task.id for task in store.tasks(root=tmp_path)} == {first.id, second.id}
    assert store.tasks(root=tmp_path / "baska") == ()


def test_ayni_ad_ikinci_goreve_ek_alir(tmp_path):
    store = _store(tmp_path)
    store.create("a", root=tmp_path, name="inceleme")
    assert store.create("b", root=tmp_path, name="inceleme").name == "inceleme-2"


def test_bos_ya_da_cok_uzun_gorev_reddedilir(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(BackgroundTaskError):
        store.create("   ", root=tmp_path)
    with pytest.raises(BackgroundTaskError):
        store.create("x" * 20_001, root=tmp_path)


def test_bilinmeyen_ya_da_gecersiz_kimlik_acik_hata_verir(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(BackgroundTaskError):
        store.get("../../etc")
    with pytest.raises(BackgroundTaskError):
        store.resolve("yok")


def test_nabzi_bayatlayan_calisan_gorev_yarim_kaldi_gorunur(tmp_path):
    clock = FakeClock()
    store = _store(tmp_path, clock)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.WORKING)
    store.heartbeat(task.id)
    assert store.get(task.id).status is TaskStatus.WORKING

    clock.value += STALE_AFTER_S + 60
    nabiz = store.task_dir(task.id) / HEARTBEAT_FILE
    import os

    os.utime(nabiz, (clock.value - STALE_AFTER_S - 5, clock.value - STALE_AFTER_S - 5))
    assert store.get(task.id).status is TaskStatus.LOST


def test_mesaj_calisan_goreve_eklenir_isci_gerekmez(tmp_path):
    store = _store(tmp_path)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.WORKING)
    store.heartbeat(task.id)

    assert store.append_inbox(task.id, _message()) is False
    assert [m.text for m in store.take_inbox(task.id)] == ["devam et"]
    assert store.take_inbox(task.id) == ()


def test_mesaj_bitmis_gorevi_yeniden_siraya_alir(tmp_path):
    store = _store(tmp_path)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.COMPLETED)
    store.request_stop(task.id)

    assert store.append_inbox(task.id, _message()) is True
    assert store.get(task.id).status is TaskStatus.QUEUED
    assert not store.stop_requested(task.id)


def test_bitis_gelen_kutusu_doluysa_yazilmaz(tmp_path):
    store = _store(tmp_path)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.WORKING)
    store.heartbeat(task.id)
    store.append_inbox(task.id, _message("ek iş"))

    current, messages = store.finish_unless_inbox(task.id, status=TaskStatus.COMPLETED)
    assert current.status is TaskStatus.WORKING
    assert [m.text for m in messages] == ["ek iş"]

    done, rest = store.finish_unless_inbox(task.id, status=TaskStatus.COMPLETED)
    assert done.status is TaskStatus.COMPLETED and rest == ()


def test_soru_cevap_istek_kimligiyle_eslesir(tmp_path):
    store = _store(tmp_path)
    task = store.create("iş", root=tmp_path)
    with pytest.raises(BackgroundTaskError):
        store.answer(task.id, "evet")

    store.ask(task.id, "3", {"tur": "onay", "ozet": "run_shell onayı"})
    assert store.answer(task.id, " evet ") == "3"
    assert store.take_answer(task.id, "2") is None
    assert store.take_answer(task.id, "3") == "evet"
    assert store.pending_question(task.id) is None


def test_calisan_gorev_silinemez_biten_silinir(tmp_path):
    store = _store(tmp_path)
    task = store.create("iş", root=tmp_path)
    with pytest.raises(BackgroundTaskError):
        store.remove(task.id)
    store.update(task.id, status=TaskStatus.COMPLETED)
    store.remove(task.id)
    assert store.tasks() == ()


def test_ad_normallestirme_kabuk_dostu():
    assert normalize_name("  Kod İnceleme / v2 ") == "kod-inceleme-v2"
    assert normalize_name("***") == ""


# --------------------------------------------------------------- başlatma


def _launcher(calls: list[list[str]]) -> agent_tasks.Launcher:
    def _launch(argv: list[str], cwd: Path, log: Path, err: Path) -> int:
        calls.append(argv)
        return 4242

    return _launch


def test_baslatma_isci_komutunu_kimlikle_calistirir(tmp_path):
    store = _store(tmp_path)
    calls: list[list[str]] = []
    task = agent_tasks.start_task(
        store,
        agent_tasks.LaunchRequest(prompt="raporu yaz", root=tmp_path, owner="sohbet-1"),
        max_active=4,
        launcher=_launcher(calls),
    )
    assert task.pid == 4242 and task.owner == "sohbet-1"
    assert calls[0][-1] == task.id and "--dizin" in calls[0]
    assert calls[0][calls[0].index("--dizin") + 1] == str(store.base_dir)


def test_etkin_gorev_tavani_asilamaz(tmp_path):
    store = _store(tmp_path)
    calls: list[list[str]] = []
    request = agent_tasks.LaunchRequest(prompt="iş", root=tmp_path)
    agent_tasks.start_task(store, request, max_active=1, launcher=_launcher(calls))
    with pytest.raises(BackgroundTaskError, match="en çok 1"):
        agent_tasks.start_task(store, request, max_active=1, launcher=_launcher(calls))


def test_baslatma_dusunce_gorev_basarisiz_isaretlenir(tmp_path):
    store = _store(tmp_path)

    def _bozuk(argv: list[str], cwd: Path, log: Path, err: Path) -> int:
        raise OSError("izin yok")

    with pytest.raises(BackgroundTaskError, match="başlatılamadı"):
        agent_tasks.start_task(
            store,
            agent_tasks.LaunchRequest(prompt="iş", root=tmp_path),
            max_active=0,
            launcher=_bozuk,
        )
    assert store.tasks()[0].status is TaskStatus.FAILED


def test_bitmis_goreve_mesaj_isciyi_yeniden_baslatir(tmp_path):
    store = _store(tmp_path)
    calls: list[list[str]] = []
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.COMPLETED)

    agent_tasks.send_to_task(
        store, task, "şunu da yap", sender="kullanici", launcher=_launcher(calls)
    )
    assert len(calls) == 1
    assert store.get(task.id).status is TaskStatus.QUEUED


def test_teslim_yalniz_sahibine_ve_bir_kez(tmp_path):
    store = _store(tmp_path)
    mine = store.create("iş", root=tmp_path, owner="sohbet-1")
    other = store.create("iş", root=tmp_path, owner="sohbet-2")
    for task in (mine, other):
        store.update(task.id, status=TaskStatus.COMPLETED, delivered=False, summary="bitti")
    store.write_result(mine.id, "Sonuç: 3 dosya değişti.")

    delivered = agent_tasks.collect_deliveries(store, "sohbet-1")
    assert [task.id for task in delivered] == [mine.id]
    assert agent_tasks.collect_deliveries(store, "sohbet-1") == ()
    block = agent_tasks.delivery_block(store, delivered)
    assert "<arka_plan_sonuclari " in block and "3 dosya değişti" in block


def test_sirada_kalan_gorev_dogrudan_durdurulur(tmp_path):
    store = _store(tmp_path)
    task = store.create("iş", root=tmp_path)
    assert agent_tasks.stop_task(store, task).status is TaskStatus.STOPPED
    with pytest.raises(BackgroundTaskError):
        agent_tasks.stop_task(store, store.get(task.id))


def test_calisan_gorev_durdurma_istegi_birakir(tmp_path):
    store = _store(tmp_path)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.WORKING)
    store.heartbeat(task.id)
    agent_tasks.stop_task(store, store.get(task.id))
    assert store.stop_requested(task.id)


def test_zorla_durdurma_kimligi_dogrulanamayan_surece_dokunmaz(tmp_path, monkeypatch):
    store = _store(tmp_path)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.WORKING, pid=1)
    store.heartbeat(task.id)
    killed: list[int] = []
    monkeypatch.setattr(
        agent_tasks, "terminate_process_tree", lambda pid, force: killed.append(pid)
    )
    with pytest.raises(BackgroundTaskError, match="doğrulanamadı"):
        agent_tasks.stop_task(store, store.get(task.id), force=True)
    assert killed == []
