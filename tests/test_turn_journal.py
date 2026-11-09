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
            function.__name__ == "save_finished"
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


# --- 30 Ekim ayıklaması (M1-47, M1-48) ------------------------------------- #


def test_arac_argumani_maskelense_de_gecerli_json_kalir(tmp_path):
    """Ölçüldü (30 Ekim): `redact('{"api_key": "sk-…", "x": 1}')` = `{[gizlendi], "x": 1}`
    (geçersiz JSON); geri yüklenen araç çağrısı sağlayıcıda 400 verebilirdi."""
    sir = "sk-or-v1-" + "a" * 48
    gunluk = FileTurnJournal(tmp_path / "j.json", task="t")
    arguman = json.dumps({"api_key": sir, "path": "a.txt", "n": 3})

    gunluk.save(
        [
            Message("user", "yaz"),
            Message("assistant", "", tool_calls=(ToolCall("c1", "write_file", arguman),)),
            Message("tool", "ok", tool_call_id="c1", name="write_file", ok=True),
        ]
    )
    kayit = gunluk.load()

    assert kayit is not None
    geri = json.loads(kayit.messages[1].tool_calls[0].arguments)
    assert geri["path"] == "a.txt" and geri["n"] == 3
    assert sir not in (tmp_path / "j.json").read_text(encoding="utf-8")


def test_okunamayan_mesaj_gunlugun_tamamini_gecersiz_kilar(tmp_path):
    """Sessizce süzülen bozuk mesaj `assistant tool_calls` / `tool` çiftini bozar,
    sağlayıcılar yetim `tool` mesajında 400 verir."""
    yol = tmp_path / "j.json"
    gunluk = FileTurnJournal(yol, task="t")
    gunluk.save(_konusma())
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri["mesajlar"][1] = {"rol": 5}
    yol.write_text(json.dumps(veri), encoding="utf-8")

    assert gunluk.load() is None


def test_kilit_kisa_sure_baska_yazarda_ise_temizleme_atlanmaz(tmp_path):
    """Ölçüldü (30 Ekim): kilit alınamazsa `clear()` sessizce atlanıyor; biten iş bir
    sonraki sekme açılışında 'yarıda kaldı' diye geri yükleniyordu."""
    import threading
    import time

    from fusion_cli.core.file_lease import FileLease

    yol = tmp_path / "j.json"
    gunluk = FileTurnJournal(yol, task="t")
    gunluk.save(_konusma())
    baska = FileLease(yol.with_suffix(".json.lock"))
    assert baska.try_acquire()
    threading.Timer(0.15, baska.close).start()

    baslangic = time.monotonic()
    gunluk.clear()

    assert gunluk.load() is None
    assert time.monotonic() - baslangic < 2.0


async def test_ozgun_segment_snapshot_ozetinden_bagimsiz_append_only_kalir(tmp_path):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("segment1",))
    original = [Message("assistant", "özgün karar"), Message("user", "Asla main'e push etme.")]
    assert await journal.append_original(scope, original)
    path = journal.original_path
    first = path.read_bytes()
    assert await journal.append_original(scope, original)
    assert path.read_bytes() == first
    journal.save([Message("user", "[önceki adımların özeti] kayıplı özet", harness_note=True)])
    reopened = FileTurnJournal(journal.path, original_owner_id="chat1")
    result = await reopened.read_original(scope)
    assert result.status == "redacted_original"
    assert result.messages == tuple(original)
    assert journal.load().messages != result.messages
    assert path.stat().st_mode & 0o777 == 0o600
    journal.clear()
    assert not path.exists()


async def test_ozgun_segment_ve_cagri_kimlik_cakismasi_yeni_kaydi_reddeder(tmp_path):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    original = [
        Message("assistant", "", tool_calls=(ToolCall("c1", "read_file", "{}"),)),
        Message("tool", "kanıt", tool_call_id="c1"),
    ]
    assert await journal.append_original(scope, original)
    before = journal.original_path.read_bytes()
    assert not await journal.append_original(scope, [Message("assistant", "farklı")])
    assert not await journal.append_original(
        OriginalTraceScope("chat1", "turn1", ("s2",)), original
    )
    assert journal.original_path.read_bytes() == before


async def test_ozgun_segment_tum_metin_alanlarindaki_sirlari_maskeler(tmp_path):
    from fusion_cli.core.original_trace import OriginalTraceScope

    canary = "sk-or-v1-" + "q" * 48
    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    messages = [
        Message(
            "assistant",
            "api_key=" + canary,
            tool_calls=(
                ToolCall("c1", "write_file", json.dumps({"api_key": canary, "path": "a.py"})),
            ),
        ),
        Message("tool", "password=" + canary, tool_call_id="c1", tool_diff="+token=" + canary),
    ]
    assert await journal.append_original(scope, messages)
    restored = await journal.read_original(scope)
    assert restored.status == "redacted_original"
    assert canary not in journal.original_path.read_text()
    assert canary not in repr(restored.messages)
    assert json.loads(restored.messages[0].tool_calls[0].arguments)["path"] == "a.py"


@pytest.mark.parametrize(
    "owner,turn,segments",
    [
        ("other", "turn1", ("s1",)),
        ("chat1", "other", ("s1",)),
        ("chat1", "../turn1", ("s1",)),
        ("chat1", "turn1", ("../s1",)),
        ("chat1", "turn1", ("s1", "s1")),
        ("chat1", "turn1", ("absent",)),
    ],
)
async def test_ozgun_okuma_sahip_tur_ve_segment_sinirlarini_karistirmaz(
    tmp_path, owner, turn, segments
):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    await journal.append_original(
        OriginalTraceScope("chat1", "turn1", ("s1",)), [Message("user", "özel")]
    )
    result = await journal.read_original(OriginalTraceScope(owner, turn, segments))
    assert result.status != "redacted_original"
    assert result.messages == ()


async def test_snapshot_kaydetmek_ozgun_kaynak_uretmez_ozet_segment_olamaz(tmp_path):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    summary = [Message("user", "[önceki adımların özeti] özet", harness_note=True)]
    journal.save(summary)
    assert (await journal.read_original(scope)).status == "missing"
    assert not await journal.append_original(scope, summary)
    disabled = FileTurnJournal(tmp_path / "off.json")
    assert not await disabled.append_original(scope, [Message("user", "ham")])
    assert not disabled.original_path.exists()


async def test_ozgun_okuma_eksik_ve_butceyi_asan_kaynagi_tam_saymaz(tmp_path):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    assert await journal.append_original(scope, [Message("assistant", "z" * 100)])
    result = await journal.read_original(
        OriginalTraceScope("chat1", "turn1", ("s1",), max_chars=10)
    )
    assert result.status == "truncated" and result.messages == ()
    journal.original_path.write_text(journal.original_path.read_text() + '{"yarım":')
    result = await journal.read_original(scope)
    assert result.status != "redacted_original" and result.messages == ()


@pytest.mark.parametrize("corruption", ["json", "identity", "schema", "messages"])
async def test_bozuk_ozgun_dosya_yeni_eklemeyi_dusurmeden_reddeder(tmp_path, corruption):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    assert await journal.append_original(scope, [Message("assistant", "özgün")])
    record = json.loads(journal.original_path.read_text())
    if corruption == "identity":
        record.pop("tur")
    elif corruption == "schema":
        record["surum"] = True
    elif corruption == "messages":
        record["mesajlar"] = [False]
    journal.original_path.write_text(
        "{bozuk}\n" if corruption == "json" else json.dumps(record) + "\n"
    )
    before = journal.original_path.read_bytes()
    assert not await journal.append_original(
        OriginalTraceScope("chat1", "turn1", ("s2",)), [Message("assistant", "yeni")]
    )
    assert journal.original_path.read_bytes() == before
    assert (await journal.read_original(scope)).status != "redacted_original"


async def test_ozgun_journal_baska_dosyaya_sembolik_bagla_yazmaz_ve_okumaz(tmp_path):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    target = tmp_path / "other.jsonl"
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    assert await journal.append_original(scope, [Message("assistant", "özgün")])
    journal.original_path.rename(target)
    before = target.read_bytes()
    journal.original_path.symlink_to(target)
    assert not await journal.append_original(
        OriginalTraceScope("chat1", "turn1", ("s2",)), [Message("assistant", "yeni")]
    )
    assert (await journal.read_original(scope)).status != "redacted_original"
    assert target.read_bytes() == before


@pytest.mark.parametrize("partial", [False, True])
async def test_ozgun_segment_tamamlanmamis_arac_grubu_ve_asiri_boyutu_reddeder(tmp_path, partial):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",), max_chars=10)
    messages = (
        [Message("assistant", "", tool_calls=(ToolCall("c1", "read_file", "{}"),))]
        if partial
        else [Message("assistant", "z" * 11)]
    )
    assert not await journal.append_original(scope, messages)
    assert not journal.original_path.exists()


async def test_ozgun_segment_eszamanli_tekrar_yazimda_bir_kez_eklenir(tmp_path):
    import asyncio

    from fusion_cli.core.original_trace import OriginalTraceScope

    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    journals = [FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1") for _ in range(6)]
    # Optional writes have one actual worker and no queue. Busy captures may be
    # skipped, while admitted duplicate segments remain idempotent.
    assert any(
        await asyncio.gather(
            *(
                journal.append_original(scope, [Message("assistant", "özgün")])
                for journal in journals
            )
        )
    )
    assert len(journals[0].original_path.read_text().splitlines()) == 1


async def test_ozgun_depo_tutma_sinirinda_eski_segmenti_silmeden_eklemeyi_reddeder(
    tmp_path, monkeypatch
):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    assert await journal.append_original(scope, [Message("assistant", "ilk")])
    before = journal.original_path.read_bytes()
    monkeypatch.setattr("fusion_cli.memory.turn_journal._ORIGINAL_FILE_BYTES", len(before) + 1)
    assert not await journal.append_original(
        OriginalTraceScope("chat1", "turn1", ("s2",)), [Message("assistant", "yeni")]
    )
    assert journal.original_path.read_bytes() == before


async def test_ozgun_segment_metin_olmayan_kimlik_alaninda_da_sir_saklamaz(tmp_path):
    from fusion_cli.core.original_trace import OriginalTraceScope

    canary = "sk-or-v1-" + "w" * 48
    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    messages = [
        Message("assistant", "", tool_calls=(ToolCall(canary, canary, "{}"),)),
        Message("tool", "sonuç", tool_call_id=canary, name=canary),
    ]
    assert await journal.append_original(scope, messages)
    result = await journal.read_original(scope)
    assert canary not in journal.original_path.read_text()
    assert canary not in repr(result.messages)
    assert result.status == "redacted_original"


@pytest.mark.parametrize(
    "corruption",
    [
        "call_item",
        "role",
        "call_id",
        "call_name",
        "call_arguments",
        "result_id",
        "name",
        "ok",
        "harness",
        "diff",
    ],
)
async def test_strict_original_decoder_rejects_nested_corruption_on_read_and_append(
    tmp_path, corruption
):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    messages = [
        Message("assistant", "", tool_calls=(ToolCall("c1", "read_file", "{}"),)),
        Message("tool", "sonuç", tool_call_id="c1"),
    ]
    assert await journal.append_original(scope, messages)
    raw = json.loads(journal.original_path.read_text())
    assistant, result = raw["mesajlar"]
    if corruption == "call_item":
        assistant["araclar"] = [False]
        raw["mesajlar"] = [assistant]
    elif corruption == "role":
        assistant["rol"] = "invalid"
    elif corruption.startswith("call_"):
        field = {"call_id": "id", "call_name": "ad", "call_arguments": "arguman"}[corruption]
        assistant["araclar"][0][field] = 42
    else:
        field = {
            "result_id": "arac_id",
            "name": "ad",
            "ok": "ok",
            "harness": "harness",
            "diff": "tool_diff",
        }[corruption]
        result[field] = 42
    journal.original_path.write_text(json.dumps(raw) + "\n")
    before = journal.original_path.read_bytes()
    assert (await journal.read_original(scope)).status != "redacted_original"
    assert not await journal.append_original(
        OriginalTraceScope("chat1", "turn1", ("s2",)),
        [Message("assistant", "yeni")],
    )
    assert journal.original_path.read_bytes() == before


@pytest.mark.parametrize("metadata", ["turn", "segment"])
async def test_original_metadata_rejects_recognized_secret_before_writing(tmp_path, metadata):
    from fusion_cli.core.original_trace import OriginalTraceScope

    canary = "sk-or-v1-" + "v" * 48
    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    safe = OriginalTraceScope("chat1", "turn1", ("s1",))
    assert await journal.append_original(safe, [Message("assistant", "koru")])
    before = journal.original_path.read_bytes()
    scope = OriginalTraceScope(
        "chat1",
        canary if metadata == "turn" else "turn1",
        (canary if metadata == "segment" else "s2",),
    )
    assert not await journal.append_original(scope, [Message("assistant", "yeni")])
    assert journal.original_path.read_bytes() == before
    assert canary not in journal.original_path.read_text()
    assert (await journal.read_original(safe)).status == "redacted_original"


async def test_original_metadata_distinct_safe_ids_remain_independent(tmp_path):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    first = OriginalTraceScope("chat1", "turn-a", ("segment-a",))
    second = OriginalTraceScope("chat1", "turn-b", ("segment-b",))
    assert await journal.append_original(first, [Message("assistant", "ilk")])
    assert await journal.append_original(second, [Message("assistant", "ikinci")])
    assert (await journal.read_original(first)).messages[0].content == "ilk"
    assert (await journal.read_original(second)).messages[0].content == "ikinci"


def test_legacy_snapshot_keeps_its_tolerant_nested_call_restore(tmp_path):
    journal = FileTurnJournal(tmp_path / "j.json")
    journal.save([Message("assistant", "eski snapshot")])
    raw = json.loads(journal.path.read_text())
    raw["mesajlar"][0]["araclar"] = [False, {"id": 7, "ad": "read_file", "arguman": "{}"}]
    journal.path.write_text(json.dumps(raw))
    restored = journal.load()
    assert restored is not None
    assert restored.messages[0].tool_calls == (ToolCall("7", "read_file", "{}"),)


@pytest.mark.parametrize("malformed", ["before", "cross_group", "wrong_role"])
async def test_original_disk_batch_grammar_blocks_read_and_later_append(tmp_path, malformed):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    messages = [
        Message("assistant", "", tool_calls=(ToolCall("c1", "read_file", "{}"),)),
        Message("tool", "birinci", tool_call_id="c1"),
        Message("assistant", "", tool_calls=(ToolCall("c2", "read_file", "{}"),)),
        Message("tool", "ikinci", tool_call_id="c2"),
    ]
    assert await journal.append_original(scope, messages)
    raw = json.loads(journal.original_path.read_text())
    first_call, first_result, second_call, second_result = raw["mesajlar"]
    if malformed == "before":
        raw["mesajlar"] = [first_result, first_call, second_call, second_result]
    elif malformed == "cross_group":
        raw["mesajlar"] = [first_call, second_call, second_result, first_result]
    else:
        first_call["rol"] = "user"
    journal.original_path.write_text(json.dumps(raw) + "\n")
    before = journal.original_path.read_bytes()
    assert (await journal.read_original(scope)).status == "incomplete"
    assert not await journal.append_original(
        OriginalTraceScope("chat1", "turn1", ("s2",)),
        [Message("assistant", "yeni")],
    )
    assert journal.original_path.read_bytes() == before


@pytest.mark.parametrize(
    "value_count, output, budget, raw_chars, published_chars, should_append",
    [
        pytest.param(22_000, "ok", 60_000, 44_014, 66_014, False, id="review_example"),
        pytest.param(19_996, "ok", 60_000, 40_006, 60_002, False, id="over_boundary"),
        pytest.param(19_995, "ok", 60_000, 40_004, 59_999, True, id="under_boundary"),
        pytest.param(19_995, "ok!", 60_000, 40_005, 60_000, True, id="exact_boundary"),
        pytest.param(20, "ok", 60, 54, 74, False, id="explicit_scope_budget"),
        pytest.param(None, "ok", 60_000, 44_014, 44_015, True, id="same_raw_size"),
    ],
)
async def test_published_original_record_is_validated_before_append(
    tmp_path, value_count, output, budget, raw_chars, published_chars, should_append
):
    from fusion_cli.core.original_trace import OriginalTraceScope

    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    safe_scope = OriginalTraceScope("chat1", "turn1", ("safe",))
    assert await journal.append_original(safe_scope, [Message("assistant", "güvenli kayıt")])
    before = journal.original_path.read_bytes()
    payload = {"value": "x" * 44_000} if value_count is None else {"values": [0] * value_count}
    arguments = json.dumps(payload, separators=(",", ":"))
    assert len(arguments) + len(output) == raw_chars
    scope = OriginalTraceScope("chat1", "turn1", ("normalized",), max_chars=budget)
    messages = [
        Message("assistant", "", tool_calls=(ToolCall("c1", "read_file", arguments),)),
        Message("tool", output, tool_call_id="c1"),
    ]

    accepted = await journal.append_original(scope, messages)

    assert accepted is should_append
    if should_append:
        published = await journal.read_original(scope)
        assert published.status == "redacted_original"
        assert len(published.messages[0].tool_calls[0].arguments) + len(output) == published_chars
    else:
        assert journal.original_path.read_bytes() == before
    safe = await journal.read_original(safe_scope)
    assert safe.status == "redacted_original"
    assert safe.messages == (Message("assistant", "güvenli kayıt"),)
    next_scope = OriginalTraceScope("chat1", "turn1", ("next",))
    assert await journal.append_original(next_scope, [Message("assistant", "sonraki kısa kayıt")])
    assert (await journal.read_original(next_scope)).status == "redacted_original"


@pytest.mark.parametrize("ending", ["partial", "failed", "cancelled"])
async def test_terminal_unsuccessful_turn_restores_context_without_app_close_claim(
    tmp_path, monkeypatch, ending
):
    """A returned partial/failed outcome or explicit stop is not a process crash."""
    import asyncio

    from fusion_cli.engines.agent.loop import AgentOutcome

    lines = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "terminal-owner"}))
    answer = "Öğretmen bulgularının giderildiği doğrulanamadı."

    async def run(*_args, journal=None, **_kwargs):
        journal.save(_konusma())
        if ending == "cancelled":
            raise asyncio.CancelledError()
        return AgentOutcome(answer, _konusma(), ok=False)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session.handle(Request("turn", "tur.calistir", {"gorev": "siteyi yap"}))
    assert _sonuc(lines, "turn")["ok"] is False

    for _ in range(2):
        reopened = AppSession(lines.append, root=tmp_path, home=tmp_path / "home")
        await reopened.handle(Request("start", "oturum.baslat", {"sohbet_id": "terminal-owner"}))
        assert any(m.role == "tool" and m.name == "write_file" for m in reopened._state.history)
        transcript = load_transcript_messages(
            reopened._state.config.memory_dir, tmp_path, conversation_id="terminal-owner"
        )
        assert not any("uygulama kapandığı için" in m.content for m in transcript)
        if ending != "cancelled":
            assert any(m.content == answer for m in reopened._state.history)
            assert not any("Kullanıcı turu durdurdu" in m.content for m in reopened._state.history)


async def test_terminal_journal_does_not_hide_another_conversations_real_interruption(
    tmp_path, monkeypatch
):
    from fusion_cli.engines.agent.loop import AgentOutcome

    session = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "home")
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "finished"}))

    async def run(*_args, journal=None, **_kwargs):
        journal.save(_konusma())
        return AgentOutcome("Doğrulanamadı", _konusma(), ok=False)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session.handle(Request("turn", "tur.calistir", {"gorev": "siteyi yap"}))
    await session.handle(Request("switch", "oturum.baslat", {"sohbet_id": "orphan"}))
    session._turn_journal("gerçekten kesilen iş").save(_konusma())
    reopened = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "home")
    await reopened.handle(Request("start", "oturum.baslat", {"sohbet_id": "orphan"}))
    transcript = load_transcript_messages(
        reopened._state.config.memory_dir, tmp_path, conversation_id="orphan"
    )
    assert sum("uygulama kapandığı için" in m.content for m in transcript) == 1
    assert any("gerçekten kesilen iş" in m.content for m in transcript)


def test_new_running_snapshot_replaces_finished_marker(tmp_path):
    journal = FileTurnJournal(tmp_path / "journal.json", task="first")
    journal.save_finished(_konusma())
    finished = journal.load()
    assert finished is not None and finished.execution_finished
    journal.mark_notified(finished)
    notified = journal.load()
    assert notified is not None and notified.execution_finished
    # A new turn can crash before returning; the previous finish must not hide it.
    FileTurnJournal(journal.path, task="next").save([Message("user", "next")])
    running = journal.load()
    assert running is not None and not running.execution_finished
    assert running.task == "next"
    journal.mark_notified(finished)
    assert journal.load() == running


@pytest.mark.parametrize("marker", [None, "true", 1, [], {}])
def test_legacy_or_invalid_finished_marker_keeps_crash_recovery(tmp_path, marker):
    journal = FileTurnJournal(tmp_path / "journal.json", task="task")
    journal.save(_konusma())
    raw = json.loads(journal.path.read_text())
    raw["execution_finished"] = marker
    journal.path.write_text(json.dumps(raw))
    entry = journal.load()
    assert entry is not None and not entry.execution_finished


async def test_finished_snapshot_closes_unresolved_tool_calls_before_continuation(
    tmp_path, monkeypatch
):
    from fusion_cli.engines.agent.loop import AgentOutcome

    session = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "home")
    await session.handle(Request("start", "oturum.baslat", {"sohbet_id": "budget-stopped"}))
    pending = [
        Message("user", "dosyayı yaz"),
        Message("assistant", "", tool_calls=(ToolCall("unresolved", "write_file", "{}"),)),
    ]

    async def run(*_args, journal=None, **_kwargs):
        journal.save(pending)
        # A round limit can stop after the model proposed a call, before execution.
        return AgentOutcome("Araç bütçesi doldu", pending, ok=False)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session.handle(Request("turn", "tur.calistir", {"gorev": "dosyayı yaz"}))
    reopened = AppSession(lambda _line: None, root=tmp_path, home=tmp_path / "home")
    await reopened.handle(Request("start", "oturum.baslat", {"sohbet_id": "budget-stopped"}))
    history = reopened._state.history
    result = next((m for m in history if m.tool_call_id == "unresolved"), None)
    assert result is not None and result.role == "tool" and result.ok is False
    assert history.index(result) == 2  # Close the call before the terminal answer.
    assert not any("Kullanıcı turu durdurdu" in m.content for m in history)
