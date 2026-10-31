"""Arka plan işçi döngüsü: tur, devam mesajı, durdurma, girdi bekleme (P-048)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fusion_cli.cli import background_worker
from fusion_cli.cli.background_worker import FileQuestionPrompter, parse_decision, run_task_loop
from fusion_cli.core.background_store import BackgroundTaskStore
from fusion_cli.core.background_tasks import InboxMessage, TaskStatus
from fusion_cli.core.clock import SystemClock
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.approval import ApprovalAnswer


def _store(tmp_path: Path) -> BackgroundTaskStore:
    return BackgroundTaskStore(tmp_path / "arka-plan", SystemClock())


async def test_gorev_tamamlanir_sonuc_ve_gecmis_yazilir(tmp_path):
    store = _store(tmp_path)
    task = store.create("README yaz", root=tmp_path, owner="sohbet-1")
    seen: list[tuple[str, int]] = []

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        seen.append((prompt, len(history)))
        return "README yazıldı.", True

    assert await run_task_loop(store, task.id, _turn) == 0
    done = store.get(task.id)
    assert done.status is TaskStatus.COMPLETED
    assert done.turns == 1 and done.delivered is False and done.summary == "README yazıldı."
    assert store.read_result(task.id) == "README yazıldı."
    assert [item["role"] for item in store.load_history(task.id)] == ["user", "assistant"]
    assert seen == [("README yaz", 0)]


async def test_tur_sirasinda_gelen_mesaj_ayni_iscide_yeni_tur_olur(tmp_path):
    store = _store(tmp_path)
    task = store.create("ilk iş", root=tmp_path)
    prompts: list[str] = []

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        prompts.append(prompt)
        if len(prompts) == 1:
            store.append_inbox(task.id, InboxMessage("ikinci iş", "kullanici", 1.0))
        return f"bitti {len(prompts)}", True

    assert await run_task_loop(store, task.id, _turn) == 0
    assert prompts == ["ilk iş", "ikinci iş"]
    assert store.get(task.id).turns == 2
    assert len(store.load_history(task.id)) == 4


async def test_yeniden_baslayan_isci_gelen_kutusuyla_devam_eder(tmp_path):
    store = _store(tmp_path)
    task = store.update(store.create("ilk", root=tmp_path).id, turns=1, status=TaskStatus.QUEUED)
    store.save_history(
        task.id, [{"role": "user", "content": "ilk"}, {"role": "assistant", "content": "ok"}]
    )
    store.append_inbox(task.id, InboxMessage("yabancı istek", "baska-oturum", 1.0, trusted=False))
    prompts: list[str] = []

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        prompts.append(prompt)
        assert len(history) == 2
        return "tamam", True

    assert await run_task_loop(store, task.id, _turn) == 0
    assert 'guvenilmez="evet"' in prompts[0] and "yabancı istek" in prompts[0]


async def test_durdurma_istegi_suren_turu_keser(tmp_path):
    store = _store(tmp_path)
    task = store.create("uzun iş", root=tmp_path)
    started = asyncio.Event()

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        started.set()
        await asyncio.sleep(30)
        return "olmamalı", True

    async def _stop() -> None:
        await started.wait()
        store.request_stop(task.id)

    code, _ = await asyncio.gather(run_task_loop(store, task.id, _turn), _stop())
    assert code == 130
    assert store.get(task.id).status is TaskStatus.STOPPED


async def test_basarisiz_tur_gorevi_basarisiz_kapatir(tmp_path):
    store = _store(tmp_path)
    task = store.create("iş", root=tmp_path)

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        return "", False

    assert await run_task_loop(store, task.id, _turn) == 1
    assert store.get(task.id).status is TaskStatus.FAILED


async def test_beklenmeyen_hata_sirsiz_notla_kaydedilir(tmp_path):
    store = _store(tmp_path)
    task = store.create("iş", root=tmp_path)

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        raise RuntimeError("sk-gizli-anahtar")

    assert await run_task_loop(store, task.id, _turn) == 1
    failed = store.get(task.id)
    assert failed.status is TaskStatus.FAILED
    assert "RuntimeError" in failed.note and "sk-gizli" not in failed.note


async def test_soru_girdi_bekliyor_durumuna_gecer_ve_cevapla_surer(tmp_path, monkeypatch):
    monkeypatch.setattr(background_worker, "_POLL_S", 0.01)
    store = _store(tmp_path)
    task = store.update(store.create("iş", root=tmp_path).id, status=TaskStatus.WORKING)
    prompter = FileQuestionPrompter(store, task.id, timeout_s=5)

    async def _answer() -> None:
        # Dosya tabanlı sözleşme: işçi soru dosyasını yazana kadar yoklanır (olay yok).
        while store.pending_question(task.id) is None:  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        assert store.get(task.id).status is TaskStatus.NEEDS_INPUT
        store.answer(task.id, "mavi")

    reply, _ = await asyncio.gather(prompter.ask("Hangi renk?"), _answer())
    assert reply == "mavi"
    assert store.get(task.id).status is TaskStatus.WORKING
    assert store.get(task.id).question == ""


async def test_cevapsiz_soru_sure_dolunca_varsayim_notu_doner(tmp_path, monkeypatch):
    monkeypatch.setattr(background_worker, "_POLL_S", 0.01)
    store = _store(tmp_path)
    task = store.create("iş", root=tmp_path)
    reply = await FileQuestionPrompter(store, task.id, timeout_s=0.05).ask("Hangi renk?")
    assert "cevap vermedi" in reply


def test_karar_cevaplari_turkce_kisaltmalari_tanir():
    assert parse_decision("Evet") is ApprovalAnswer.ONCE
    assert parse_decision("oturum") is ApprovalAnswer.SESSION
    assert parse_decision("hayır") is ApprovalAnswer.DENY
    assert parse_decision("belki") is ApprovalAnswer.UNAVAILABLE


async def test_siradayken_durdurulan_gorevin_iscisi_calismaz(tmp_path):
    store = _store(tmp_path)
    task = store.create("iş", root=tmp_path)
    from fusion_cli.tools.agent_tasks import stop_task

    stop_task(store, task)
    ran: list[str] = []

    async def _turn(current, prompt: str, history: list[Message]) -> tuple[str, bool]:
        ran.append(prompt)
        return "olmamalı", True

    assert await run_task_loop(store, task.id, _turn) == 130
    assert ran == [] and store.get(task.id).status is TaskStatus.STOPPED
