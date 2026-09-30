"""Duraklayan tur da geçmişe yazılmalı; soru kalıp cevap kaybolmamalı.

Ölçüldü (7 Eylül, kullanıcının Godot koşuları): plan adımları duraklayınca tur
`ok=False` döndü. Soru transcript'e yazıldı, cevap yazılmadı — kullanıcının
diskindeki `198b3a19…` sohbeti 8 soru ve 0 cevap taşıyor. Sekme yeniden
açıldığında model kendi ne dediğini göremiyor ve kaldığı yerden süremiyor.

Transcript bir BAŞARI kaydı değil, NE OLDUĞU kaydıdır: duraklama da bir cevaptır.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl.transcript_store import load_transcript_messages

pytestmark = pytest.mark.asyncio


def _session(tmp_path, satirlar):
    return AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")


def _sonuc(satirlar, kimlik):
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(f"kimlik için sonuç bulunamadı: {kimlik}")


def _sahte_sonuc(monkeypatch, *, ok, metin):
    from types import SimpleNamespace

    async def _calistir(*_args, **_kwargs):
        return SimpleNamespace(ok=ok, final_text=metin, messages=())

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calistir)


async def _tur(oturum, satirlar, gorev):
    await oturum.handle(Request(id="t", name="tur.calistir", data={"gorev": gorev}))
    return _sonuc(satirlar, "t")


def _kayitli(oturum, tmp_path):
    return [
        (mesaj.role, mesaj.content)
        for mesaj in load_transcript_messages(
            oturum._state.config.memory_dir, tmp_path, conversation_id="sekme"
        )
    ]


async def _sekme(oturum):
    await oturum.handle(Request(id="b", name="oturum.baslat", data={"sohbet_id": "sekme"}))


async def test_duraklayan_turun_cevabi_da_kaydedilir(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)
    _sahte_sonuc(monkeypatch, ok=False, metin="Plan adımı duraklatıldı: asset-acquisition.")

    await _tur(oturum, satirlar, "oyun yap")

    assert _kayitli(oturum, tmp_path) == [
        ("user", "oyun yap"),
        ("assistant", "Plan adımı duraklatıldı: asset-acquisition."),
    ]


async def test_basarili_turun_cevabi_kaydedilmeye_devam_eder(tmp_path, monkeypatch):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)
    _sahte_sonuc(monkeypatch, ok=True, metin="bitti")

    await _tur(oturum, satirlar, "oyun yap")

    assert _kayitli(oturum, tmp_path) == [("user", "oyun yap"), ("assistant", "bitti")]


async def test_bos_cevap_kaydedilmez(tmp_path, monkeypatch):
    """Boş satır geçmişi kirletir ve modele hiçbir şey söylemez."""
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)
    _sahte_sonuc(monkeypatch, ok=False, metin="   ")

    await _tur(oturum, satirlar, "oyun yap")

    assert _kayitli(oturum, tmp_path) == [("user", "oyun yap")]


async def test_iptal_edilen_tur_da_iz_birakir(tmp_path, monkeypatch):
    """İptal de bir cevaptır: soru cevapsız kalırsa devam etmek imkânsızdır."""
    import asyncio

    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)

    async def _bekle(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _bekle)
    tur = asyncio.ensure_future(_tur(oturum, satirlar, "oyun yap"))
    await asyncio.sleep(0)
    await oturum.handle(Request(id="k", name="tur.kes", data={}))
    await tur

    roller = [rol for rol, _ in _kayitli(oturum, tmp_path)]
    assert roller == ["user", "assistant"]


async def test_butceyle_kesilen_cevapsiz_tur_ozetle_doner_ve_kaydedilir(tmp_path, monkeypatch):
    """Ölçüldü (28 Eylül): büyük görev "model bir cevap üretmedi" ile bitiyor,
    kullanıcı neyin yapılıp neyin kaldığını göremiyordu."""
    from types import SimpleNamespace

    from fusion_cli.core.tools import TodoItem, TodoStatus

    async def _calistir(*_args, **_kwargs):
        return SimpleNamespace(
            ok=False,
            final_text="",
            messages=(),
            budget_stopped=True,
            stop_reason="no_progress",
            todos=(
                TodoItem("sunucuyu kur", TodoStatus.COMPLETED),
                TodoItem("arayüzü düzenle", TodoStatus.PENDING),
            ),
        )

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calistir)
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)

    sonuc = await _tur(oturum, satirlar, "büyük işi yap")

    assert sonuc["ok"] is False
    assert "Görevler: 1/2 tamamlandı." in sonuc["metin"]
    assert "devam et" in sonuc["metin"]
    assert _kayitli(oturum, tmp_path)[-1] == ("assistant", sonuc["metin"])


def _kesilen_sonuc(*, degisiklik: int, bekleyen: bool = True):
    from types import SimpleNamespace

    from fusion_cli.core.tools import TodoItem, TodoStatus

    return SimpleNamespace(
        ok=False,
        final_text="",
        messages=(),
        budget_stopped=True,
        stop_reason="no_progress",
        mutating_tool_calls_made=degisiklik,
        todos=(
            TodoItem("sunucuyu kur", TodoStatus.COMPLETED),
            TodoItem("arayüzü düzenle", TodoStatus.PENDING if bekleyen else TodoStatus.COMPLETED),
        ),
    )


async def test_degisiklik_yapan_kesik_tur_kendiliginden_surdurulur(tmp_path, monkeypatch):
    from types import SimpleNamespace

    gorevler: list[str] = []
    sonuclar = [
        _kesilen_sonuc(degisiklik=2),
        SimpleNamespace(ok=True, final_text="Tüm görevler bitti.", messages=()),
    ]

    async def _calistir(gorev, *_args, **_kwargs):
        gorevler.append(gorev)
        return sonuclar.pop(0)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calistir)
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)

    sonuc = await _tur(oturum, satirlar, "büyük işi yap")

    assert sonuc == {"ok": True, "metin": "Tüm görevler bitti."}
    assert len(gorevler) == 2
    assert gorevler[1].startswith("devam et")
    assert any("otomatik devam" in satir for satir in satirlar)


async def test_degisiklik_yapmayan_kesik_tur_surdurulmez(tmp_path, monkeypatch):
    cagri = 0

    async def _calistir(*_args, **_kwargs):
        nonlocal cagri
        cagri += 1
        return _kesilen_sonuc(degisiklik=0)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calistir)
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)

    sonuc = await _tur(oturum, satirlar, "büyük işi yap")

    assert cagri == 1
    assert "devam et" in sonuc["metin"]


async def test_otomatik_devam_sinirli_sayida_yapilir(tmp_path, monkeypatch):
    from fusion_cli.appserver.session import MAX_AUTO_CONTINUE_TURNS

    cagri = 0

    async def _calistir(*_args, **_kwargs):
        nonlocal cagri
        cagri += 1
        return _kesilen_sonuc(degisiklik=1)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calistir)
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)

    await _tur(oturum, satirlar, "büyük işi yap")

    assert cagri == 1 + MAX_AUTO_CONTINUE_TURNS


async def test_gorevler_bittiyse_surdurulmez(tmp_path, monkeypatch):
    cagri = 0

    async def _calistir(*_args, **_kwargs):
        nonlocal cagri
        cagri += 1
        return _kesilen_sonuc(degisiklik=3, bekleyen=False)

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", _calistir)
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    await _sekme(oturum)

    await _tur(oturum, satirlar, "büyük işi yap")

    assert cagri == 1
