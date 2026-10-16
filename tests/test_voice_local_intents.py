"""Yerel konuşma yanıtları gerçek görevleri yutmaz, model çağırmaz."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.appserver.voice_intents import local_voice_reply


@pytest.mark.parametrize(
    "text",
    ["Merhaba Füzyon!", "Fusion, merhaba", "Selam", "Nasılsın füzyon?", "Beni duyuyor musun?"],
)
def test_local_phrase(text):
    assert local_voice_reply(text)


@pytest.mark.parametrize(
    "text",
    [
        "Merhaba Füzyon, projeyi aç",
        "teşekkürler ama devam et",
        "evet",
        "hayır",
        "merhaba dosyasını sil",
        "",
    ],
)
def test_tasks_and_approvals_not_local(text):
    assert local_voice_reply(text) is None


async def test_local_voice_turn_persists_without_model_and_receipt_replay(tmp_path, monkeypatch):
    from fusion_cli.cli import session as cli_session

    model = AsyncMock(side_effect=AssertionError("Yerel selam model çağırmamalı"))
    monkeypatch.setattr(cli_session, "run_agent_task", model)
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    request = Request(
        "local",
        "tur.calistir",
        {"gorev": "Merhaba Füzyon", "sesli": {}, "gonderim_id": "hello-voice"},
    )
    try:
        first = await app._dispatch(request)
        second = await app._dispatch(request)
        assert first["ok"] is True and first["yerel_yanit"] is True
        assert second["makbuz"]["durum"] == "completed"
        assert [message.role for message in app._state.history] == ["user", "assistant"]
        assert app._state.history[-1].content == first["metin"]
        model.assert_not_called()
    finally:
        await app.close()


async def test_preparation_nonblocking_cancelled_handler_close_owns_worker(tmp_path, monkeypatch):
    import asyncio
    import threading

    from fusion_cli.appserver import session as session_module

    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    cleaned = []

    def prepare(text):
        entered.set()
        release.wait(5)
        finished.set()
        return {"ok": True, "hazir_id": "late"}

    monkeypatch.setattr(session_module, "prepare_voice", prepare)
    monkeypatch.setattr(
        session_module,
        "discard_prepared_voice",
        lambda *args: cleaned.append(finished.is_set()) or {"ok": True},
    )
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    task = asyncio.create_task(
        app._dispatch(Request("prepare", "ses.hazirla", {"metin": "Merhaba"}))
    )
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert entered.is_set() and not finished.is_set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        closing = asyncio.create_task(app.close())
        await asyncio.sleep(0.02)
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, 3)
        assert cleaned == [True]
        assert not app._voice_preparations
        assert (await app._dispatch(Request("late", "ses.hazirla", {"metin": "Selam"})))[
            "ok"
        ] is False
    finally:
        release.set()
        if not app._closed:
            await app.close()


async def test_direct_speech_does_not_block_event_loop_while_local_model_busy(
    tmp_path, monkeypatch
):
    import asyncio
    import threading

    from fusion_cli.appserver import session as session_module

    entered, release = threading.Event(), threading.Event()

    def speak(text):
        entered.set()
        release.wait(0.4)
        return {"ok": True, "tur_id": "owned"}

    monkeypatch.setattr(session_module, "voice_speak", speak)
    app = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "home")
    task = asyncio.create_task(app._dispatch(Request("speak", "ses.konus", {"metin": "Merhaba"})))
    try:
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.001)
        assert entered.is_set() and not task.done()
        release.set()
        assert (await task)["ok"] is True
    finally:
        release.set()
        await app.close()
