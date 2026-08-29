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


def _sahte_gorev(olay: asyncio.Event, yakalanan: dict, **kwargs):
    """`run_agent_task` yerine geçen, `olay` set edilene kadar bekleyen sahte görev."""
    yakalanan["kwargs"] = kwargs

    async def _calistir() -> SimpleNamespace:
        await olay.wait()
        return SimpleNamespace(ok=True, final_text="bitti")

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
    """SORUN 2c: `run_agent_task`'e oturumun sohbet geçmişi geçirilir."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    olay = asyncio.Event()
    olay.set()
    yakalanan: dict = {}
    monkeypatch.setattr(
        "fusion_cli.cli.session.run_agent_task",
        lambda *a, **kw: _sahte_gorev(olay, yakalanan, **kw),
    )

    await oturum.handle(Request(id="1", name="tur.calistir", data={"gorev": "iş"}))

    assert yakalanan["kwargs"]["history"] is oturum._state.history


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
