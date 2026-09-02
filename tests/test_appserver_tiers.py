"""Masaüstü composer'ındaki kademe (düşünme düzeyi) seçicisinin protokolü.

Kademe merdiveni yapılandırmada zaten vardı (`config.tiers`) ve TUI'de
çalışıyordu; masaüstünde yüzeyi yoktu. Bu testler yüzeyin sözleşmesini
sabitler — özellikle sağlayıcı kilidini: kademe modelleri NVIDIA'da barındığı
için NVIDIA dışı bir sağlayıcı seçiliyken seçim DEĞİŞTİRİLEMEZ olmalıdır ve
bunu istemci tahmin etmemeli, sunucu söylemelidir.
"""

from __future__ import annotations

import json

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


def _session(tmp_path, satirlar):
    return AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")


def _sonuc(satirlar, kimlik):
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(kimlik)


async def test_kademe_listele_tanimli_kademeleri_etiketiyle_dondurur(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request("1", "kademe.listele", {}))

    veri = _sonuc(satirlar, "1")
    assert veri["ok"] is True
    adlar = [k["ad"] for k in veri["kademeler"]]
    assert adlar == ["low", "medium", "high", "ultra", "premium"]
    assert all(k["etiket"] for k in veri["kademeler"])
    assert veri["etkin"] in adlar


async def test_kademe_sec_baş_modeli_ve_hakemi_birlikte_degistirir(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    onceki = oturum._state.config.agent.model

    await oturum.handle(Request("2", "kademe.sec", {"ad": "ultra"}))

    veri = _sonuc(satirlar, "2")
    assert veri["ok"] is True
    assert veri["etkin"] == "ultra"
    assert oturum._state.config.agent.model != onceki
    assert "ultra" in oturum._state.config.agent.model


async def test_bilinmeyen_kademe_acik_hata_verir(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)

    await oturum.handle(Request("3", "kademe.sec", {"ad": "yok-boyle"}))

    veri = _sonuc(satirlar, "3")
    assert veri["ok"] is False
    assert "yok-boyle" in veri["metin"]


async def test_nvidia_disi_saglayicida_kademe_duzenlenemez_ve_gerekce_bildirilir(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    oturum._state.config = _saglayici(oturum._state.config, "openrouter")

    await oturum.handle(Request("4", "kademe.listele", {}))

    veri = _sonuc(satirlar, "4")
    assert veri["duzenlenebilir"] is False
    assert veri["metin"]


async def test_kilitliyken_kademe_secimi_reddedilir(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    oturum._state.config = _saglayici(oturum._state.config, "openrouter")
    onceki = oturum._state.config.agent.model

    await oturum.handle(Request("5", "kademe.sec", {"ad": "ultra"}))

    veri = _sonuc(satirlar, "5")
    assert veri["ok"] is False
    assert oturum._state.config.agent.model == onceki


async def test_nvidia_saglayicisinda_kademe_duzenlenebilir(tmp_path):
    satirlar: list[str] = []
    oturum = _session(tmp_path, satirlar)
    oturum._state.config = _saglayici(oturum._state.config, "nvidia")

    await oturum.handle(Request("6", "kademe.listele", {}))

    assert _sonuc(satirlar, "6")["duzenlenebilir"] is True


def _saglayici(config, deger):
    """Yapılandırmanın sağlayıcı tercihini değiştir; `Config` frozen'dır."""
    from dataclasses import replace

    return replace(config, runtime=replace(config.runtime, provider=deger))
