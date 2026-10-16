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
        assert yeni._state.history == _konusma()

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
