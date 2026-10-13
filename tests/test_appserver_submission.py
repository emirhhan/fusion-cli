"""Kalıcı gönderimin mevcut oturum sınırındaki regresyonları."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


@pytest.mark.parametrize("restart", [False, True])
async def test_tamamlanan_gonderim_tekrari_executor_calistirmaz(tmp_path, monkeypatch, restart):
    effects = []

    async def execute(task, config, **kwargs):
        effects.append(task)
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    request = Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "kalici"})
    first = await session._dispatch(request)
    if restart:
        session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    replay = await session._dispatch(request)
    assert replay["makbuz"] == first["makbuz"]
    assert effects == ["iş"]


async def test_concurrent_duplicate_yeni_busy_reddi_yerine_makbuz_doner(tmp_path, monkeypatch):
    import asyncio

    entered = asyncio.Event()
    release = asyncio.Event()
    effects = []

    async def execute(task, config, **kwargs):
        effects.append(task)
        entered.set()
        await release.wait()
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    first_request = Request(
        id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "kalici"}
    )
    first_task = asyncio.create_task(session._dispatch(first_request))
    await entered.wait()
    try:
        duplicate = await session._dispatch(
            Request(id="2", name="tur.calistir", data=first_request.data)
        )
        assert duplicate["ok"] is True
        assert duplicate["makbuz"]["gonderim_id"] == "kalici"
        assert effects == ["iş"]
    finally:
        release.set()
        await first_task


async def test_completed_lookup_kayip_ek_validasyonundan_once_yapilir(tmp_path, monkeypatch):
    effects = []

    async def execute(task, config, **kwargs):
        effects.append(task)
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    attachment = tmp_path / "ek.txt"
    attachment.write_text("test eki")
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    request = Request(
        id="1",
        name="tur.calistir",
        data={
            "gorev": "iş",
            "gonderim_id": "kalici",
            "ekler": [{"path": str(attachment), "name": "ek.txt"}],
        },
    )
    first = await session._dispatch(request)
    attachment.unlink()
    replay = await session._dispatch(request)
    assert replay["makbuz"] == first["makbuz"]
    assert effects == ["iş"]


async def test_ayni_profil_kok_farkli_sohbet_gonderimleri_izole(tmp_path, monkeypatch):
    effects = []

    async def execute(task, config, **kwargs):
        effects.append(task)
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    request = Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "kalici"})
    for conversation in ("ilk", "ikinci"):
        await session._dispatch(
            Request(id="başlat", name="oturum.baslat", data={"sohbet_id": conversation})
        )
        await session._dispatch(request)
    assert effects == ["iş", "iş"]


async def test_makbuz_deposu_yazilamazsa_executor_baslamaz(tmp_path, monkeypatch):
    effects = []

    async def execute(task, config, **kwargs):
        effects.append(task)
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    async def fail_lookup(key):
        raise OSError("test depolama arızası")

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    monkeypatch.setattr(session._submission_store, "lookup", fail_lookup)
    result = await session._dispatch(
        Request(
            id="1",
            name="tur.calistir",
            data={
                "gorev": "iş",
                "gonderim_id": "kalici",
            },
        )
    )
    assert result["ok"] is False
    assert effects == []


async def test_accepted_writer_kaybi_isin_sahipligini_iptal_etmez(tmp_path, monkeypatch):
    effects = []

    async def execute(task, config, **kwargs):
        effects.append(task)
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    def failing_writer(line):
        raise OSError("test yanıt kaybı")

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(failing_writer, root=tmp_path, home=tmp_path / "ev")
    request = Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "kalici"})
    first = await session._dispatch(request)
    duplicate = await session._dispatch(request)
    assert first["makbuz"] == duplicate["makbuz"]
    assert first["makbuz"]["durum"] == "completed"
    assert effects == ["iş"]


async def test_transport_bekleyicisi_iptali_owned_executor_ve_finali_iptal_etmez(
    tmp_path, monkeypatch
):
    import asyncio

    entered = asyncio.Event()
    release = asyncio.Event()
    effects = []

    async def execute(task, config, **kwargs):
        effects.append(task)
        entered.set()
        await release.wait()
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    request = Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "kalici"})
    waiter = asyncio.create_task(session._dispatch(request))
    await entered.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    owned = session._submission_task
    assert owned is not None and not owned.cancelled()
    release.set()
    await owned
    duplicate = await session._dispatch(request)
    assert duplicate["makbuz"]["durum"] == "completed"
    assert effects == ["iş"]


async def test_guvenli_explicit_retry_ayni_kullanici_mesajiyla_yeni_attempt_acar(
    tmp_path, monkeypatch
):
    effects = []

    async def execute(task, config, **kwargs):
        effects.append(task)
        return SimpleNamespace(
            ok=len(effects) > 1, final_text="sonuç", messages=[], tool_calls_made=0, tool_uses=()
        )

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    request = Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "kalici"})
    first = await session._dispatch(request)
    duplicate = await session._dispatch(request)
    assert duplicate["makbuz"] == first["makbuz"]
    assert effects == ["iş"]
    retry = await session._dispatch(
        Request(id="2", name="tur.calistir", data={**request.data, "yeniden_dene": True})
    )
    assert retry["makbuz"]["tur_id"] != first["makbuz"]["tur_id"]
    assert effects == ["iş", "iş"]
    records = [
        json.loads(line) for line in session._transcript_store.events_path.read_text().splitlines()
    ]
    assert len([record for record in records if record["event"] == "UserMessage"]) == 1


async def test_failed_effect_sonrasi_explicit_retry_observation_olmadan_yurutulmez(
    tmp_path, monkeypatch
):
    effects = []

    async def execute(task, config, **kwargs):
        effects.append("dış etki")
        return SimpleNamespace(
            ok=False,
            final_text="sonuç kayıp",
            messages=[],
            tool_calls_made=1,
            tool_uses=("mutating",),
        )

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    request = Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "kalici"})
    first = await session._dispatch(request)
    retry = await session._dispatch(
        Request(id="2", name="tur.calistir", data={**request.data, "yeniden_dene": True})
    )
    assert retry["ok"] is False
    assert retry["makbuz"] == first["makbuz"]
    assert "dış etkisini doğrula" in retry["metin"]
    assert effects == ["dış etki"]


async def test_makbuz_db_prompt_ek_final_ve_ham_hata_icermez(tmp_path, monkeypatch):
    async def execute(task, config, **kwargs):
        return SimpleNamespace(ok=True, final_text="FINAL_SENTINEL_A04", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    attachment = tmp_path / "ek.txt"
    attachment.write_text("ATTACHMENT_SENTINEL_A04")
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    await session._dispatch(
        Request(
            id="1",
            name="tur.calistir",
            data={
                "gorev": "PROMPT_SENTINEL_A04",
                "gonderim_id": "kalici",
                "ekler": [{"path": str(attachment), "name": "ek.txt"}],
            },
        )
    )
    metadata = session._submission_store._path.read_bytes()
    for sentinel in (b"PROMPT_SENTINEL_A04", b"FINAL_SENTINEL_A04", b"ATTACHMENT_SENTINEL_A04"):
        assert sentinel not in metadata


async def test_auto_continue_ayni_attempt_icin_olay_sirasi_paylasir(tmp_path, monkeypatch):
    from fusion_cli.core.events import StatusChanged

    lines = []

    async def execute(task, config, **kwargs):
        kwargs["sinks"][0].handle(StatusChanged("çalışıyor"))
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    monkeypatch.setattr(
        "fusion_cli.appserver.session._should_auto_continue", lambda outcome, n: n == 0
    )
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "ev")
    await session._dispatch(
        Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "devam"})
    )
    events = [json.loads(line) for line in lines]
    ids = [event["veri"]["event_id"] for event in events if "event_id" in event.get("veri", {})]
    assert len(ids) >= 3
    assert len(ids) == len(set(ids))
    assert [int(identifier.rsplit(":", 1)[1]) for identifier in ids] == list(range(1, len(ids) + 1))


@pytest.mark.parametrize("boundary", ["lookup", "claim"])
async def test_close_bekleyen_admission_executor_baslatmaz(tmp_path, monkeypatch, boundary):
    import asyncio

    entered = asyncio.Event()
    effects = []
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")

    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()

    async def execute(task, config, **kwargs):
        effects.append(task)
        return SimpleNamespace(ok=True, final_text="bitti", messages=[])

    monkeypatch.setattr(session._submission_store, boundary, blocked)
    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    waiter = asyncio.create_task(
        session._dispatch(
            Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "kapan"})
        )
    )
    await entered.wait()
    await session.close()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert effects == []
    assert session._admission_tasks == set()
    assert session._submission_task is None
    assert (
        await session._submit_turn(
            Request(id="2", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "sonra"})
        )
    )["ok"] is False


async def test_bos_failure_retry_reload_tek_kimlikli_final(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.transcript_store import load_transcript_messages

    calls = 0

    async def execute(task, config, **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            ok=calls > 1,
            final_text="bitti" if calls > 1 else "",
            messages=[],
            budget_stopped=False,
            tool_calls_made=0,
            tool_uses=(),
        )

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    data = {"gorev": "iş", "gonderim_id": "tekfinal"}
    await session._dispatch(Request(id="1", name="tur.calistir", data=data))
    await session._dispatch(
        Request(id="2", name="tur.calistir", data={**data, "yeniden_dene": True})
    )
    history = load_transcript_messages(
        session._state.config.memory_dir,
        tmp_path,
        conversation_id=session._transcript_store.session_id,
    )
    finals = [message for message in history if message.role == "assistant"]
    assert len(finals) == 1
    assert finals[0].message_id == "tekfinal:assistant"
    assert finals[0].content == "bitti"


async def test_move_metadata_finalize_failure_hedefte_tekrar_etki_yok(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.transcript_store import TranscriptStore
    from fusion_cli.core.submission import SubmissionKey

    source = tmp_path / "kaynak"
    target = tmp_path / "hedef"
    source.mkdir()
    target.mkdir()
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    profile = str(session._state.config.memory_dir.resolve())
    TranscriptStore(
        session._state.config.memory_dir, source, conversation_id="tasinan"
    ).record_user("iş")
    key = SubmissionKey(profile, str(source.resolve()), "tasinan", "once")
    claim = await session._submission_store.claim(key)
    await session._submission_store.finish(claim.receipt, state="completed")
    finish_move = session._submission_store.move_conversation

    async def fail_finalize(*args):
        raise OSError("test metadata write failure")

    monkeypatch.setattr(session._submission_store, "move_conversation", fail_finalize)
    data = {"sohbet_id": "tasinan", "kaynak_kok": str(source), "hedef_kok": str(target)}
    assert (await session._move_conversation(data))["ok"] is False
    target_key = SubmissionKey(profile, str(target.resolve()), "tasinan", "once")
    replay = await session._submission_store.claim(target_key)
    assert not replay.is_owner
    assert replay.receipt.state.value == "completed"
    monkeypatch.setattr(session._submission_store, "move_conversation", finish_move)
    assert (await session._move_conversation(data))["ok"] is True
    assert await session._submission_store.lookup(key) is None


async def test_cancelled_final_reload_kalici_kimlik_tasir(tmp_path, monkeypatch):
    import asyncio

    from fusion_cli.cli.repl.transcript_store import load_transcript_messages

    entered = asyncio.Event()

    async def execute(task, config, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    waiter = asyncio.create_task(
        session._dispatch(
            Request(id="1", name="tur.calistir", data={"gorev": "iş", "gonderim_id": "iptal"})
        )
    )
    await entered.wait()
    session._cancel_turn()
    await waiter
    history = load_transcript_messages(
        session._state.config.memory_dir,
        tmp_path,
        conversation_id=session._transcript_store.session_id,
    )
    assert [message.message_id for message in history if message.role == "assistant"] == [
        "iptal:assistant"
    ]


async def test_move_collision_metadata_degistirmez_ve_unrelated_cleanup_yapmaz(tmp_path):
    from fusion_cli.cli.repl.transcript_store import TranscriptStore
    from fusion_cli.core.submission import SubmissionKey

    source, target = tmp_path / "kaynak", tmp_path / "hedef"
    source.mkdir()
    target.mkdir()
    session = AppSession(lambda line: None, root=tmp_path, home=tmp_path / "ev")
    profile = str(session._state.config.memory_dir.resolve())
    for root in (source, target):
        TranscriptStore(session._state.config.memory_dir, root, conversation_id="ayni").record_user(
            str(root)
        )
    source_key = SubmissionKey(profile, str(source.resolve()), "ayni", "source-only")
    claim = await session._submission_store.claim(source_key)
    await session._submission_store.finish(claim.receipt, state="completed")
    data = {"sohbet_id": "ayni", "kaynak_kok": str(source), "hedef_kok": str(target)}
    assert (await session._move_conversation(data))["ok"] is False
    target_key = SubmissionKey(profile, str(target.resolve()), "ayni", "source-only")
    assert await session._submission_store.lookup(target_key) is None
    assert (await session._submission_store.claim(target_key)).is_owner
    data["kaynak_kok"] = str(tmp_path / "olmayan")
    assert (await session._move_conversation(data))["ok"] is False
    assert await session._submission_store.lookup(source_key) is not None
