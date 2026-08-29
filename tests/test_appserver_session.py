"""Oturum ömrü ve istek yönlendirme."""

from __future__ import annotations

import asyncio
import json
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
