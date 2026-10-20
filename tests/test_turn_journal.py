"""Tur günlüğü: süreç tur ortasında kapanırsa sekme işi kaldığı adımdan sürdürebilmeli."""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.transcript_store import load_transcript_messages
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.memory.turn_journal import FileTurnJournal


def _konusma() -> list[Message]:
    return [
        Message("user", "siteyi yap"),
        Message(
            "assistant",
            "",
            tool_calls=(ToolCall(id="c1", name="write_file", arguments='{"path": "a.html"}'),),
        ),
        Message("tool", "yazıldı", tool_call_id="c1", name="write_file", ok=True),
        Message("user", "doğrulama notu", harness_note=True),
    ]


def test_gunluk_konusmayi_arac_adimlariyla_geri_verir(tmp_path):
    gunluk = FileTurnJournal(tmp_path / "j.json", task="siteyi yap")

    gunluk.save(_konusma())
    kayit = gunluk.load()

    assert kayit is not None
    assert kayit.task == "siteyi yap"
    assert list(kayit.messages) == _konusma()
    assert not kayit.notified


def test_gunluk_sirlari_diske_acik_yazmaz(tmp_path):
    gunluk = FileTurnJournal(tmp_path / "j.json", task="t")
    sir = "sk-or-v1-" + "a" * 48

    gunluk.save([Message("tool", f"anahtar: {sir}", tool_call_id="c", name="read_file")])

    assert sir not in (tmp_path / "j.json").read_text(encoding="utf-8")


def test_gunluk_gorselleri_yazmaz(tmp_path):
    gunluk = FileTurnJournal(tmp_path / "j.json")

    gunluk.save([Message("user", "bak", images=("data:image/png;base64," + "A" * 5000,))])

    assert "base64" not in (tmp_path / "j.json").read_text(encoding="utf-8")


def test_bozuk_gunluk_yok_sayilir(tmp_path):
    yol = tmp_path / "j.json"
    yol.write_text("{yarım", encoding="utf-8")

    assert FileTurnJournal(yol).load() is None


def test_temizlenen_gunluk_yarida_kalmis_sayilmaz(tmp_path):
    gunluk = FileTurnJournal(tmp_path / "j.json", task="t")
    gunluk.save(_konusma())

    gunluk.clear()
    gunluk.clear()

    assert gunluk.load() is None


async def test_dongu_her_arac_turundan_sonra_gunluge_yazar(tmp_path, monkeypatch):
    from dataclasses import replace

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent
    from tests.agent_harness import Publisher, install_provider
    from tests.fakes import (
        AlwaysApprove,
        RecordingSink,
        ScriptedProvider,
        make_config,
        model_result,
        tool_call,
    )

    install_provider(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("list_dir", path=".")]),
                model_result("bitti"),
            ]
        ),
    )
    gunluk = FileTurnJournal(tmp_path / "j.json", task="listele")
    deps = AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    await run_agent("listele", replace(deps, journal=gunluk))

    kayit = gunluk.load()
    assert kayit is not None
    assert any(mesaj.role == "tool" and mesaj.name == "list_dir" for mesaj in kayit.messages)


def _sonuc(satirlar, kimlik):
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(kimlik)


@pytest.mark.asyncio
async def test_sekme_yarida_kalan_isi_geri_yukler_ve_bir_kez_bildirir(tmp_path):
    satirlar: list[str] = []
    ilk = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    await ilk.handle(Request(id="b", name="oturum.baslat", data={"sohbet_id": "sekme"}))
    # Tur sürerken süreç öldü: günlük yazılmış, tur bitmemiş.
    ilk._turn_journal("siteyi yap").save(_konusma())

    for _ in range(2):
        yeni = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
        await yeni.handle(Request(id="b", name="oturum.baslat", data={"sohbet_id": "sekme"}))
        assert yeni._state.history[:-1] == _konusma()
        assert "siteyi yap" in yeni._state.history[-1].content

    bildirimler = [
        mesaj.content
        for mesaj in load_transcript_messages(
            yeni._state.config.memory_dir, tmp_path, conversation_id="sekme"
        )
        if "yarıda kaldı" in mesaj.content
    ]
    assert len(bildirimler) == 1
    assert "siteyi yap" in bildirimler[0]


@pytest.mark.asyncio
async def test_biten_tur_gunlugu_siler(tmp_path, monkeypatch):
    from types import SimpleNamespace

    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    await oturum.handle(Request(id="b", name="oturum.baslat", data={"sohbet_id": "sekme"}))

    async def _calistir(*_args, journal=None, **_kwargs):
        journal.save(_konusma())
        return SimpleNamespace(ok=True, final_text="bitti", messages=())

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calistir)
    await oturum.handle(Request(id="t", name="tur.calistir", data={"gorev": "siteyi yap"}))

    assert _sonuc(satirlar, "t")["ok"]
    assert oturum._turn_journal("").load() is None


@pytest.mark.parametrize("ending", ["failed", "cleanup_failed", "cancelled"])
async def test_unfinished_turn_keeps_answer_and_tool_journal(tmp_path, monkeypatch, ending):
    import asyncio

    from fusion_cli.core.errors import CleanupFailedError
    from fusion_cli.engines.agent.loop import AgentOutcome

    lines = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "journal-owner"}))

    async def run(*args, journal=None, **kwargs):
        journal.save(_konusma())
        if ending == "cleanup_failed":
            raise CleanupFailedError("cleanup unknown")
        if ending == "cancelled":
            raise asyncio.CancelledError()
        return AgentOutcome("Kontrol başarısız", _konusma(), ok=False)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session.handle(Request("turn", "tur.calistir", {"gorev": "siteyi yap"}))
    entry = session._turn_journal("").load()
    assert entry is not None
    assert any(message.name == "write_file" for message in entry.messages)
    assert any(message.content == "doğrulama notu" for message in entry.messages)


@pytest.mark.parametrize(
    "change", [{"mesajlar": None}, {"zaman": "invalid"}, {"zaman": float("nan")}, {"surum": True}]
)
def test_malformed_journal_envelope_cannot_crash_restore(tmp_path, change):
    path = tmp_path / "journal.json"
    payload = {"surum": 1, "mesajlar": [], "zaman": 1, "gorev": "task", "bildirildi": False}
    payload.update(change)
    path.write_text(json.dumps(payload))
    assert FileTurnJournal(path).load() is None


def test_gunluk_baska_yazarin_gecici_dosyasina_dokunmaz(tmp_path):
    path = tmp_path / "j.json"
    other_temporary = path.with_suffix(".tmp")
    other_temporary.write_text("başka yazıcının verisi", encoding="utf-8")

    journal = FileTurnJournal(path, task="görev")
    journal.save(_konusma())

    assert journal.load() is not None
    assert other_temporary.read_text(encoding="utf-8") == "başka yazıcının verisi"
    assert path.stat().st_mode & 0o777 == 0o600


def test_eski_bildirim_yeni_tur_kaydini_geri_alamaz(tmp_path):
    journal = FileTurnJournal(tmp_path / "j.json", task="görev")
    journal.save([Message("user", "eski")])
    old = journal.load()
    assert old is not None
    journal.save([Message("user", "yeni")])
    journal.mark_notified(old)
    current = journal.load()
    assert current is not None
    assert current.messages[0].content == "yeni"
    assert not current.notified


def test_temizlenmis_tur_eski_bildirimle_dirilmez(tmp_path):
    journal = FileTurnJournal(tmp_path / "j.json")
    journal.save(_konusma())
    old = journal.load()
    assert old is not None
    journal.clear()
    journal.mark_notified(old)
    assert journal.load() is None


@pytest.mark.parametrize("reopen", [False, True])
async def test_durdur_devam_et_arac_gecmisini_korur(tmp_path, monkeypatch, reopen):
    import asyncio

    from fusion_cli.engines.agent.loop import AgentOutcome

    session = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "home")
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "resume"}))
    seen = []

    async def run(task, _config, *, journal, history, **_kwargs):
        if task == "siteyi yap":
            journal.save(_konusma())
            raise asyncio.CancelledError()
        seen.extend(history)
        return AgentOutcome("bitti", list(history), ok=True)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session.handle(Request("first", "tur.calistir", {"gorev": "siteyi yap"}))
    if reopen:
        session = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "home")
        await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "resume"}))
    await session.handle(Request("next", "tur.calistir", {"gorev": "Devam et"}))

    assert any(m.name == "write_file" and m.role == "tool" for m in seen)
    assert sum(m.role == "user" and m.content == "siteyi yap" for m in seen) == 1
    assert any(str(tmp_path.resolve()) in m.content and "yeniden" in m.content for m in seen)


async def test_iptal_ilk_aractan_once_olsa_da_gunluk_kalir(tmp_path, monkeypatch):
    import asyncio

    session = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "home")
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "resume"}))

    async def run(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session.handle(Request("first", "tur.calistir", {"gorev": "siteyi yap"}))

    entry = session._turn_journal("").load()
    assert entry is not None
    assert entry.task == "siteyi yap"
    assert any(m.content == "siteyi yap" for m in entry.messages)


def test_yarim_arac_grubunda_biten_sonuc_korunur_belirsiz_cagri_tekrarlanmaz():
    from fusion_cli.core.turn_resume import interrupted_history

    calls = (
        ToolCall("done", "write_file", '{"path":"a.txt"}'),
        ToolCall("unknown", "run_shell", '{"command":"external-action"}'),
    )
    original = [
        Message("user", "dosyayı yaz sonra uzak işlemi yap"),
        Message("assistant", "", tool_calls=calls),
        Message("tool", "yazıldı", tool_call_id="done", name="write_file", ok=True),
    ]
    history = interrupted_history(original, task="asıl iş", root="/proje ")
    assert history[:3] == original
    unknown = history[3]
    assert unknown.tool_call_id == "unknown" and unknown.ok is False
    assert "gerçekleşmiş olabilir" in unknown.content
    assert "'/proje '" in history[-1].content
    assert interrupted_history(history, task="asıl iş", root="/proje ") == history


@pytest.mark.parametrize("internal", [False, True])
async def test_arac_grubu_ortasinda_iptal_biten_aracin_sonucunu_saklar(
    tmp_path, monkeypatch, internal
):
    import asyncio
    from dataclasses import replace

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent
    from tests.agent_harness import Publisher, install_provider
    from tests.fakes import (
        AlwaysApprove,
        RecordingSink,
        ScriptedProvider,
        make_config,
        model_result,
        tool_call,
    )

    call = tool_call("list_dir", path=".")
    install_provider(monkeypatch, ScriptedProvider([model_result(tool_calls=[call])]))
    journal = FileTurnJournal(tmp_path / "j.json", task="listele")
    deps = AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    async def interrupted(_calls, messages, *_args, **_kwargs):
        messages.append(Message("tool", "dosyalar", tool_call_id=call.id, name="list_dir", ok=True))
        raise asyncio.CancelledError()

    monkeypatch.setattr("fusion_cli.engines.agent.loop._run_tools", interrupted)
    with pytest.raises(asyncio.CancelledError):
        await run_agent("listele", replace(deps, journal=journal), internal=internal)
    entry = journal.load()
    assert entry is not None
    assert any(m.name == "list_dir" and m.content == "dosyalar" for m in entry.messages)


async def test_devam_turu_iptal_gunlugu_kalici_olana_kadar_baslamaz(tmp_path, monkeypatch):
    import asyncio

    from fusion_cli.appserver import session as module
    from fusion_cli.core.turn_resume import RESUME_PREFIX
    from fusion_cli.engines.agent.loop import AgentOutcome

    session = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "home")
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "resume"}))
    started, saving, release, continued = (asyncio.Event() for _ in range(4))
    original_thread = module.await_owned_thread

    async def thread(function, *args, **kwargs):
        if (
            function.__name__ == "save"
            and args
            and any(m.content.startswith(RESUME_PREFIX) for m in args[0])
            and not saving.is_set()
        ):
            saving.set()
            await release.wait()
        return await original_thread(function, *args, **kwargs)

    async def run(task, _config, *, journal, history, **_kwargs):
        if task == "siteyi yap":
            journal.save(_konusma())
            started.set()
            await asyncio.Event().wait()
        continued.set()
        return AgentOutcome("bitti", list(history), ok=True)

    monkeypatch.setattr(module, "await_owned_thread", thread)
    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    first = asyncio.create_task(session._run_turn("siteyi yap"))
    await asyncio.wait_for(started.wait(), 5)
    session._cancel_turn()
    await asyncio.wait_for(saving.wait(), 5)
    second = asyncio.create_task(session._run_turn("Devam et"))
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(continued.wait(), 0.05)
    finally:
        release.set()
        await asyncio.gather(first, second)
    assert continued.is_set()


def test_gunluk_diffi_maskeli_korur_ve_eski_kayitla_uyumludur(tmp_path):
    gunluk = FileTurnJournal(tmp_path / "j.json")
    gunluk.save([Message("tool", "ok", ok=True, tool_diff="+password=ornek")])
    entry = gunluk.load()
    assert entry is not None
    assert entry.messages[0].tool_diff == "+[gizlendi]"
    raw = json.loads(gunluk.path.read_text())
    assert raw["surum"] == 1
    raw["mesajlar"][0].pop("tool_diff")
    gunluk.path.write_text(json.dumps(raw))
    legacy = gunluk.load()
    assert legacy is not None
    assert legacy.messages[0].tool_diff is None
