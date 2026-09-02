"""Oturum ömrü ve istek yönlendirme."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.ui import messages


def _session(tmp_path, satirlar):
    return AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")


def _sonuc(satirlar, kimlik):
    """`satirlar` içinden verilen istek kimliğine ait son sonucu bul."""
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(f"kimlik için sonuç bulunamadı: {kimlik}")


async def test_bilinmeyen_istek_hata_sonucu_doner(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="1", name="olmayan.istek", data={}))

    sonuc = json.loads(satirlar[-1])
    assert sonuc["tip"] == "sonuc"
    assert sonuc["id"] == "1"
    assert sonuc["veri"]["ok"] is False


async def test_durum_istegi_kok_dizini_bildirir(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="2", name="oturum.durum", data={}))

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    assert veri["kok"] == str(tmp_path)


async def test_canli_fusion_gecmisi_de_sirli_mesaji_redakte_eder(tmp_path):
    from fusion_cli.core.types import Message

    oturum = _session(tmp_path, [])
    oturum._state.history = [
        Message("user", "normal oyun geçmişi"),
        Message("assistant", "AUTH_TOKEN=live-secret-value"),
    ]
    satirlar: list[str] = []
    oturum._writer = satirlar.append

    await oturum.handle(Request(id="live-history", name="oturum.gecmis", data={}))

    veri = _sonuc(satirlar, "live-history")
    metin = json.dumps(veri, ensure_ascii=False)
    assert "live-secret-value" not in metin
    assert "AUTH_TOKEN" not in metin
    assert "normal oyun geçmişi" in metin


async def test_yerel_fusion_gecmisi_ayni_proje_icin_devam_baglamina_yuklenir(
    tmp_path, monkeypatch
):
    from fusion_cli.config.loader import load_config

    project = tmp_path / "game"
    project.mkdir()
    memory_dir = tmp_path / "memory"
    digest = hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:16]
    transcript = memory_dir / "transcripts" / digest / "events.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"event": "UserMessage", "text": "Oyunun durumu nedir?"}),
                json.dumps({"event": "ToolExecuted", "name": "read_file"}),
                json.dumps({"event": "TurnAnswered", "text": "Oyun çalışıyor."}),
                "bozuk-json",
                json.dumps({"event": "UserMessage", "text": "Kısa devam"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = replace(load_config(), memory_dir=memory_dir)
    monkeypatch.setattr("fusion_cli.appserver.session.load_config", lambda: config)
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=project, home=tmp_path / "ev")

    await oturum.handle(Request(id="history", name="oturum.gecmis", data={}))

    assert _sonuc(satirlar, "history") == {
        "ok": True,
        "mesajlar": [
            {"rol": "kullanici", "metin": "Oyunun durumu nedir?"},
            {"rol": "asistan", "metin": "Oyun çalışıyor."},
            {"rol": "kullanici", "metin": "Kısa devam"},
        ],
    }
    assert [(message.role, message.content) for message in oturum._state.history] == [
        ("user", "Oyunun durumu nedir?"),
        ("assistant", "Oyun çalışıyor."),
        ("user", "Kısa devam"),
    ]


async def test_yerel_gecmis_yuklenirken_sirlar_maskelenir(tmp_path, monkeypatch):
    from fusion_cli.config.loader import load_config

    project = tmp_path / "game"
    project.mkdir()
    memory_dir = tmp_path / "memory"
    digest = hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:16]
    transcript = memory_dir / "transcripts" / digest / "events.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps({"event": "UserMessage", "text": "TOKEN=secret-value"}) + "\n",
        encoding="utf-8",
    )
    config = replace(load_config(), memory_dir=memory_dir)
    monkeypatch.setattr("fusion_cli.appserver.session.load_config", lambda: config)
    oturum = AppSession(lambda _line: None, root=project, home=tmp_path / "ev")

    assert oturum._state.history[0].content == "[gizlendi]"


async def test_masaustu_turu_ayni_projenin_fusion_gecmisine_kalici_eklenir(
    tmp_path, monkeypatch
):
    from fusion_cli.config.loader import load_config
    from fusion_cli.core.types import Message

    project = tmp_path / "game"
    project.mkdir()
    memory_dir = tmp_path / "memory"
    config = replace(load_config(), memory_dir=memory_dir)
    monkeypatch.setattr("fusion_cli.appserver.session.load_config", lambda: config)

    async def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            ok=True,
            final_text="Devam kaydedildi.",
            messages=[
                Message("user", "Zararsız devam"),
                Message("assistant", "Devam kaydedildi."),
            ],
        )

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", fake_run)
    oturum = AppSession(lambda _line: None, root=project, home=tmp_path / "ev")

    await oturum.handle(
        Request(id="follow-up", name="tur.calistir", data={"gorev": "Zararsız devam"})
    )

    digest = hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:16]
    events_path = memory_dir / "transcripts" / digest / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    assert [(event["event"], event["text"]) for event in events] == [
        ("UserMessage", "Zararsız devam"),
        ("TurnAnswered", "Devam kaydedildi."),
    ]


async def test_sesli_yanit_bekle_istenirse_surec_bitmeden_sonuc_donmez(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    beklenen: list[int] = []
    monkeypatch.setattr(
        "fusion_cli.appserver.session.voice_speak",
        lambda _text: {"ok": True, "pid": 77},
    )
    monkeypatch.setattr(
        "fusion_cli.appserver.session.voice_wait",
        lambda pid: beklenen.append(pid) or True,
    )

    await oturum.handle(
        Request(id="ses-1", name="ses.konus", data={"metin": "Merhaba", "bekle": True})
    )

    assert beklenen == [77]
    assert _sonuc(satirlar, "ses-1")["tamamlandi"] is True


async def test_ses_durdur_yalniz_istenen_tur_kimligini_iletir(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    gorulen: list[object] = []
    monkeypatch.setattr(
        "fusion_cli.appserver.session.voice_stop",
        lambda turn_id: gorulen.append(turn_id)
        or {"ok": True, "durduruldu": True, "tur_id": turn_id},
    )

    await oturum.handle(
        Request(id="ses-stop", name="ses.durdur", data={"tur_id": "turn-42"})
    )

    assert gorulen == ["turn-42"]
    assert _sonuc(satirlar, "ses-stop") == {
        "ok": True,
        "durduruldu": True,
        "tur_id": "turn-42",
    }


async def test_ses_bekle_tur_kimligiyle_gercek_bitisi_bildirir(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    gorulen: list[object] = []
    monkeypatch.setattr(
        "fusion_cli.appserver.session.voice_wait",
        lambda turn_id: gorulen.append(turn_id) or True,
    )

    await oturum.handle(
        Request(id="ses-wait", name="ses.bekle", data={"tur_id": "turn-43"})
    )

    assert gorulen == ["turn-43"]
    assert _sonuc(satirlar, "ses-wait") == {
        "ok": True,
        "tamamlandi": True,
        "tur_id": "turn-43",
    }


async def test_komut_listesi_doner(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="3", name="komut.listele", data={}))

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    assert any(k["ad"] == "help" for k in veri["komutlar"])


async def test_eslesmeyen_cevap_false_doner(tmp_path):
    from fusion_cli.appserver.protocol import Reply

    oturum = _session(tmp_path, [])

    assert oturum.resolve_reply(Reply(id="yok", data={})) is False


async def test_kapanista_bekleyen_sorular_serbest_birakilir(tmp_path):
    """Kapanış bekleyen soruyu sonsuza dek asılı bırakmamalı."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    _kimlik, gelecek = oturum.pending.new_question()

    await oturum.close()
    await asyncio.sleep(0)

    assert gelecek.done()


async def test_kapanis_tts_childini_diger_surecleri_beklemeden_durdurur(tmp_path):
    """AppSession.close TTS sahipliğini kapanış zincirinin başında bırakmalı."""
    from fusion_cli.appserver import voice

    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    yonetilen_surecler_serbest = asyncio.Event()

    async def _bloklanan_surec_kapanisi():
        await yonetilen_surecler_serbest.wait()

    oturum._processes.close = _bloklanan_surec_kapanisi
    child = await asyncio.to_thread(
        subprocess.Popen, [sys.executable, "-c", "import time; time.sleep(30)"]
    )
    voice._register_speech_process(child, turn_id="session-close-real-child")

    kapanis = asyncio.create_task(oturum.close())
    try:
        await asyncio.wait_for(asyncio.to_thread(child.wait), timeout=2.0)
        assert child.poll() is not None, f"TTS child PID {child.pid} kapanmadı"
    finally:
        yonetilen_surecler_serbest.set()
        await kapanis
        if child.poll() is None:
            child.kill()
        await asyncio.to_thread(child.wait, timeout=2)


def _sahte_gorev(olay: asyncio.Event, yakalanan: dict, *, mesajlar=None, **kwargs):
    """`run_agent_task` yerine geçen, `olay` set edilene kadar bekleyen sahte görev.

    Gerçek `AgentOutcome` gibi `messages` alanı taşır: `AppSession._run_turn`
    turdan sonra bunu `state.history`e yazar (SORUN 2c / C2); bu sahte olmadan
    o yazım testte hiç sınanamaz.
    """
    yakalanan["kwargs"] = kwargs
    sonraki_gecmis = mesajlar if mesajlar is not None else []

    async def _calistir() -> SimpleNamespace:
        await olay.wait()
        return SimpleNamespace(ok=True, final_text="bitti", messages=sonraki_gecmis)

    return _calistir()


async def test_calisan_tur_varken_ikinci_istek_reddedilir(tmp_path, monkeypatch):
    """SORUN 1: ikinci `tur.calistir` mevcut turu üzerine yazmamalı, reddedilmeli."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    olay = asyncio.Event()
    yakalanan: dict = {}
    monkeypatch.setattr(
        "fusion_cli.cli.session.run_agent_task",
        lambda *a, **kw: _sahte_gorev(olay, yakalanan, **kw),
    )

    ilk_gorev = asyncio.ensure_future(
        oturum.handle(Request(id="1", name="tur.calistir", data={"gorev": "ilk iş"}))
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    ilk_tur = oturum._turn
    assert ilk_tur is not None and not ilk_tur.done()

    await oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": "ikinci iş"}))

    ikinci_sonuc = _sonuc(satirlar, "2")
    assert ikinci_sonuc == {"ok": False, "metin": messages.APP_TURN_ALREADY_RUNNING}
    # Mevcut tur bozulmadan aynı görev nesnesiyle devam ediyor.
    assert oturum._turn is ilk_tur
    assert not ilk_tur.done()

    olay.set()
    await ilk_gorev
    birinci_sonuc = _sonuc(satirlar, "1")
    assert birinci_sonuc == {"ok": True, "metin": "bitti"}


async def test_tur_ekleri_yalniz_yol_metadatasi_olarak_baglanca_girer(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    gorulen: dict[str, str] = {}

    def _fake(*_args, **kwargs):
        gorulen["extra_system"] = kwargs["extra_system"]

        async def _run():
            return SimpleNamespace(ok=True, final_text="bitti", messages=[])

        return _run()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _fake)
    attachment = tmp_path / "ornek.png"
    attachment.write_bytes(b"PNG")
    await oturum.handle(
        Request(
            id="ek-1",
            name="tur.calistir",
            data={
                "gorev": "görseli incele",
                "ekler": [
                    {
                        "path": str(attachment),
                        "name": "ornek.png",
                        "kind": "image",
                        "icerik": "BURASI-PROTOKOLE-GIRMEMELI",
                    }
                ],
            },
        )
    )

    assert str(attachment) in gorulen["extra_system"]
    assert '"kind": "image"' in gorulen["extra_system"]
    assert "BURASI-PROTOKOLE-GIRMEMELI" not in gorulen["extra_system"]


async def test_olmayan_ek_acik_hatayla_reddedilir(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    def _calismamali(*_args, **_kwargs):
        raise AssertionError("geçersiz ekte agent turu başlamamalı")

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calismamali)
    await oturum.handle(
        Request(
            id="ek-yok",
            name="tur.calistir",
            data={
                "gorev": "dosyayı incele",
                "ekler": [{"path": str(tmp_path / "silinmis.png"), "name": "silinmis.png"}],
            },
        )
    )

    sonuc = _sonuc(satirlar, "ek-yok")
    assert sonuc["ok"] is False
    assert "silinmis.png" in sonuc["metin"]
    assert "mevcut değil" in sonuc["metin"]


async def test_secret_store_run_command_a_gecirilir(tmp_path, monkeypatch):
    """SORUN 2a: `run_command` her zaman oturumun sır deposuyla çağrılır."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    yakalanan: dict = {}

    def _sahte_run_command(registry, state, name, argument, *, secret_store=None):
        yakalanan["secret_store"] = secret_store
        return {"ok": True, "metin": ""}

    monkeypatch.setattr("fusion_cli.appserver.session.run_command", _sahte_run_command)

    await oturum.handle(Request(id="1", name="komut.calistir", data={"ad": "level", "arguman": ""}))

    assert yakalanan["secret_store"] is oturum._secret_store
    assert yakalanan["secret_store"] is not None


async def test_run_command_secici_alani_tele_oldugu_gibi_yazilir(tmp_path):
    """SORUN 2b: `run_command`'ın döndürdüğü `secici` alanı kaybolmadan tele gider."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="1", name="komut.calistir", data={"ad": "level", "arguman": ""}))

    sonuc = _sonuc(satirlar, "1")
    assert sonuc["ok"] is True
    assert "secici" in sonuc
    assert sonuc["secici"]["adim"] == "kademe"


async def test_history_run_agent_task_a_gecirilir(tmp_path, monkeypatch):
    """SORUN 2c / C2: `run_agent_task`'e oturumun sohbet geçmişi geçirilir VE
    turun ürettiği yeni geçmiş bir SONRAKİ `tur.calistir`e taşınır — aksi halde
    her tur sıfırdan başlar, çok turlu sohbet hiç çalışmaz (bkz.
    `docs/superpowers/sdd/final-fix-report.md` C2)."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    ilk_turun_ciktisi = [SimpleNamespace(role="assistant", content="ilk turun cevabı")]
    gorulen_gecmisler: list[object] = []

    def _sahte(*_args, **kwargs):
        gorulen_gecmisler.append(kwargs["history"])

        async def _calistir() -> SimpleNamespace:
            return SimpleNamespace(ok=True, final_text="bitti", messages=ilk_turun_ciktisi)

        return _calistir()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _sahte)

    await oturum.handle(Request(id="1", name="tur.calistir", data={"gorev": "ilk iş"}))

    # İlk turda geçmiş boştu ve `AppSession` bunu kendi durumundan geçirdi.
    assert gorulen_gecmisler[0] == []
    # Turun ürettiği yeni geçmiş durumda saklandı — sonraki tur bunu görecek.
    assert oturum._state.history is ilk_turun_ciktisi

    await oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": "ikinci iş"}))

    # C2: ikinci tur BİRİNCİ turun ürettiği geçmişi gördü — sıfırdan başlamadı.
    assert gorulen_gecmisler[1] is ilk_turun_ciktisi


async def test_model_olayi_oturum_kullanimina_yansir(tmp_path, monkeypatch):
    """Gerçek tur yolu sink'i kullanır; sayaç yalnız birim testinde kalmamalı."""
    from fusion_cli.core.events import ModelCallFinished
    from fusion_cli.core.types import ModelResult, TokenUsage

    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    def _sahte(*_args, **kwargs):
        kwargs["sinks"][0].handle(
            ModelCallFinished(
                role="agent",
                result=ModelResult(
                    name="agent",
                    model="test/model",
                    text="bitti",
                    latency_ms=25,
                    ok=True,
                    usage=TokenUsage(
                        prompt_tokens=40,
                        completion_tokens=10,
                        cost_usd=0.002,
                    ),
                ),
            )
        )

        async def _calistir():
            return SimpleNamespace(ok=True, final_text="bitti", messages=[])

        return _calistir()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _sahte)

    await oturum.handle(Request(id="tur", name="tur.calistir", data={"gorev": "iş"}))
    await oturum.handle(Request(id="kullanim", name="kullanim.durum", data={}))

    kullanim = _sonuc(satirlar, "kullanim")["kullanim"]
    assert kullanim["cagri"] == 1
    assert kullanim["toplam_token"] == 50
    assert kullanim["maliyet_usd"] == 0.002
    assert kullanim["modeller"][0]["model"] == "test/model"


async def test_devralinan_kunye_yalniz_sonraki_tura_extra_system_olarak_gecer(
    tmp_path, monkeypatch
):
    """CLI ile aynı sözleşme: devralma künyesi tur BAŞLARKEN tüketilir.

    Böylece aynı dış konuşma sonraki bağımsız turlara tekrar tekrar enjekte
    edilmez. Tur sonradan başarısız olsa bile başlayan turun bağlamına girmiştir.
    """
    lines: list[str] = []
    session = _session(tmp_path, lines)
    session._state.pending_digest = "<devralinan_oturum>kanıt</devralinan_oturum>"
    seen: list[str] = []

    def _fake(*_args, **kwargs):
        seen.append(kwargs["extra_system"])

        async def _run():
            return SimpleNamespace(ok=True, final_text="bitti", messages=[])

        return _run()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _fake)

    await session.handle(Request(id="digest-1", name="tur.calistir", data={"gorev": "devam"}))
    await session.handle(Request(id="digest-2", name="tur.calistir", data={"gorev": "sonra"}))

    assert seen == ["<devralinan_oturum>kanıt</devralinan_oturum>", ""]
    assert session._state.pending_digest is None


async def test_kapanista_calisan_tur_gercekten_iptal_edilir(tmp_path, monkeypatch):
    """SORUN 3: `close()` bekleyen turu yalnızca serbest bırakmaz, gerçekten iptal eder."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    olay = asyncio.Event()
    yakalanan: dict = {}
    monkeypatch.setattr(
        "fusion_cli.cli.session.run_agent_task",
        lambda *a, **kw: _sahte_gorev(olay, yakalanan, **kw),
    )

    gorev = asyncio.ensure_future(
        oturum.handle(Request(id="1", name="tur.calistir", data={"gorev": "iş"}))
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    calisan_tur = oturum._turn
    assert calisan_tur is not None and not calisan_tur.done()

    await oturum.close()
    await asyncio.sleep(0)

    assert calisan_tur.cancelled()
    await gorev
    sonuc = _sonuc(satirlar, "1")
    assert sonuc == {"ok": False, "metin": messages.APP_TURN_CANCELLED}


async def test_c1_komutla_degisen_config_calisan_tura_ulasir(tmp_path, monkeypatch):
    """C1: `/provider` gibi bir komutun kurduğu YENİ config, sonraki tura ulaşmalı.

    Önceki halde `AppSession.__init__` `self._config`i ayrıca saklıyordu; komut
    akışları yalnız `state.config`i güncelliyordu ve `_run_turn` hâlâ eski
    `self._config`i kullanıyordu — kullanıcı `ok:true` alırdı ama tur eski
    sağlayıcıyla koşardı.
    """
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    baslangic_saglayici = oturum._state.config.runtime.provider

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "provider", "arguman": "nvidia"})
    )
    komut_sonucu = _sonuc(satirlar, "1")
    assert komut_sonucu["ok"] is True
    assert oturum._state.config.runtime.provider == "nvidia"
    assert oturum._state.config.runtime.provider != baslangic_saglayici

    gorulen: dict = {}

    def _sahte(*args, **_kwargs):
        gorulen["config"] = args[1]

        async def _calistir() -> SimpleNamespace:
            return SimpleNamespace(ok=True, final_text="bitti", messages=[])

        return _calistir()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _sahte)

    await oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": "iş"}))

    assert gorulen["config"] is oturum._state.config
    assert gorulen["config"].runtime.provider == "nvidia"

    durum_sonucu_icin = await oturum.handle(Request(id="3", name="oturum.durum", data={}))
    del durum_sonucu_icin  # `handle` sonucu yazmaz, tel'e yazar; bkz. `_sonuc`.
    durum = _sonuc(satirlar, "3")
    assert durum["model"] == oturum._state.config.agent.model


async def test_c4_security_komutu_calisan_tura_gecer(tmp_path, monkeypatch):
    """C4: `/security` `state.approval`i değiştirir; `_run_turn` bunu ANINDA görmeli.

    Önceki halde `_run_turn` `self._mode` (AUTO'ya çivili sabit alan) kullanıyordu;
    kullanıcı "mod değişti" mesajı alırdı ama tur AUTO ile koşmaya devam ederdi —
    bu, yıkıcı işlemlerde otomatik onay demek olduğundan bir güvenlik sapmasıydı.
    """
    from fusion_cli.engines.agent.approval import ApprovalMode

    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    assert oturum._state.approval is ApprovalMode.AUTO

    await oturum.handle(
        Request(id="1", name="komut.calistir", data={"ad": "security", "arguman": ""})
    )
    assert oturum._state.approval is ApprovalMode.SECURITY

    gorulen: dict = {}

    def _sahte(*_args, **kwargs):
        gorulen["mode"] = kwargs["mode"]

        async def _calistir() -> SimpleNamespace:
            return SimpleNamespace(ok=True, final_text="bitti", messages=[])

        return _calistir()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _sahte)

    await oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": "iş"}))

    assert gorulen["mode"] is ApprovalMode.SECURITY


async def test_c4_oturum_baslat_onay_modu_ve_motoru_kurar(tmp_path, monkeypatch):
    """C4: `oturum.baslat` isteği spec'te tanımlı ama hiç uygulanmamıştı.

    Kurduğu onay modu hem `oturum.durum`e hem de sonraki `tur.calistir`e
    yansımalı.
    """
    from fusion_cli.engines.agent.approval import ApprovalMode

    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(
        Request(id="1", name="oturum.baslat", data={"mod": "plan", "motor": "agent"})
    )
    baslat_sonuc = _sonuc(satirlar, "1")
    assert baslat_sonuc["ok"] is True
    assert baslat_sonuc["mod"] == "plan"
    assert baslat_sonuc["motor"] == "agent"
    assert oturum._state.approval is ApprovalMode.PLAN

    gorulen: dict = {}

    def _sahte(*_args, **kwargs):
        gorulen["mode"] = kwargs["mode"]

        async def _calistir() -> SimpleNamespace:
            return SimpleNamespace(ok=True, final_text="bitti", messages=[])

        return _calistir()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _sahte)
    await oturum.handle(Request(id="2", name="tur.calistir", data={"gorev": "iş"}))

    assert gorulen["mode"] is ApprovalMode.PLAN


async def test_oturum_baslat_gecersiz_mod_hata_doner(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="1", name="oturum.baslat", data={"mod": "olmayan-mod"}))

    sonuc = _sonuc(satirlar, "1")
    assert sonuc["ok"] is False


async def test_oturum_durum_motor_alanini_dondurur(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request(id="1", name="oturum.durum", data={}))

    veri = _sonuc(satirlar, "1")
    assert veri["motor"] == "agent"


async def test_tur_kes_calisan_turu_gercekten_iptal_eder(tmp_path, monkeypatch):
    """`tur.kes` denetimde SIFIR testli bulunmuştu: çalışan bir turu gerçekten
    iptal ettiğini burada doğrula (yalnız `ok:true` dönüp turu yaşatmadığını)."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    olay = asyncio.Event()
    yakalanan: dict = {}
    monkeypatch.setattr(
        "fusion_cli.cli.session.run_agent_task",
        lambda *a, **kw: _sahte_gorev(olay, yakalanan, **kw),
    )

    gorev = asyncio.ensure_future(
        oturum.handle(Request(id="1", name="tur.calistir", data={"gorev": "iş"}))
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    calisan_tur = oturum._turn
    assert calisan_tur is not None and not calisan_tur.done()

    await oturum.handle(Request(id="2", name="tur.kes", data={}))

    kesme_sonucu = _sonuc(satirlar, "2")
    assert kesme_sonucu == {"ok": True, "metin": messages.APP_TURN_CANCELLED}

    await gorev
    assert calisan_tur.cancelled()
    tur_sonucu = _sonuc(satirlar, "1")
    assert tur_sonucu == {"ok": False, "metin": messages.APP_TURN_CANCELLED}
    assert oturum._turn is None


async def test_web_baglan_oturumu_yapilandirmaya_yazar(tmp_path):
    """Giriş penceresi kapandıktan sonra oturum gerçekten kaydedilmeli.

    Eskiden yalnız profil klasörüne bakılıyordu; oturum `web_sessions`'a
    yazılmadığı için Fusion o sağlayıcıyı hiç kullanamıyordu.
    """
    from dataclasses import replace

    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    oturum._state.config = replace(oturum._state.config, source=tmp_path / "config.yaml")

    await oturum.handle(
        Request(id="1", name="web.baglan", data={"saglayici": "chatgpt_web", "hesap": "main"})
    )

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    kayitli = oturum._state.config.web_sessions
    assert [item.provider for item in kayitli] == ["chatgpt_web"]
    assert kayitli[0].enabled is True


async def test_web_cikis_oturumu_kaldirir(tmp_path):
    from dataclasses import replace

    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    oturum._state.config = replace(oturum._state.config, source=tmp_path / "config.yaml")
    await oturum.handle(
        Request(id="1", name="web.baglan", data={"saglayici": "chatgpt_web", "hesap": "main"})
    )

    await oturum.handle(
        Request(id="2", name="web.cikis", data={"saglayici": "chatgpt_web", "hesap": "main"})
    )

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is True
    assert oturum._state.config.web_sessions == ()


async def test_web_dogrula_kayitsiz_saglayiciyi_reddeder(tmp_path):
    """Doğrulama uydurmaz: kayıtlı oturum yoksa açıkça hayır der."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(
        Request(id="1", name="web.dogrula", data={"saglayici": "chatgpt_web", "hesap": "main"})
    )

    veri = json.loads(satirlar[-1])["veri"]
    assert veri["ok"] is False
