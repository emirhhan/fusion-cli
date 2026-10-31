"""`tarayici.*` RPC'leri: profil listesi, dosya önizleme, içe aktarma, silme (P-024).

Çerez değeri hiçbir yanıt satırına çıkmaz.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.config.browser_profiles import BrowserProfileStore

GIZLI = "cerez-degeri-GIZLI-31"


def _sonuc(satirlar, kimlik):
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(f"kimlik için sonuç bulunamadı: {kimlik}")


@pytest.fixture
def oturum(tmp_path):
    satirlar: list[str] = []
    session = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    session._browser_profiles = BrowserProfileStore(
        tmp_path / "bp", secret_key="anahtar", clock=lambda: 2.0
    )
    return session, satirlar


@pytest.fixture
def cerez_dosyasi(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(
        f".example.com\tTRUE\t/\tTRUE\t0\tsid\t{GIZLI}\nother.net\tFALSE\t/\tFALSE\t0\to\t1\n",
        encoding="utf-8",
    )
    return path


async def test_bos_liste_ve_yapilandirma_degerleri(oturum):
    session, satirlar = oturum

    await session.handle(Request(id="1", name="tarayici.profiller", data={}))

    veri = _sonuc(satirlar, "1")
    assert veri["ok"] is True
    assert veri["profiller"] == []
    assert veri["varsayilan"] == "" and veri["headless"] is True and veri["etkin"] is True
    assert veri["anahtar_var"] is True


async def test_dosya_onizleme_yalniz_alan_adi_verir(oturum, cerez_dosyasi):
    session, satirlar = oturum

    await session.handle(
        Request(id="2", name="tarayici.dosya_onizle", data={"yol": str(cerez_dosyasi)})
    )

    veri = _sonuc(satirlar, "2")
    assert veri == {"ok": True, "alan_adlari": ["example.com", "other.net"], "cerez_sayisi": 2}
    assert all(GIZLI not in satir for satir in satirlar)


async def test_ice_aktarma_onayli_alan_adlariyla_yazar_ve_listede_gorunur(oturum, cerez_dosyasi):
    session, satirlar = oturum

    await session.handle(
        Request(
            id="3",
            name="tarayici.ice_aktar",
            data={"ad": "is", "yol": str(cerez_dosyasi), "alan_adlari": ["example.com"]},
        )
    )
    await session.handle(Request(id="4", name="tarayici.profiller", data={}))

    yazma = _sonuc(satirlar, "3")
    assert yazma["ok"] is True, yazma
    assert yazma["profil"]["cerez_sayisi"] == 1
    liste = _sonuc(satirlar, "4")["profiller"]
    assert liste[0]["ad"] == "is"
    assert liste[0]["onayli_alan_adlari"] == ["example.com"]
    assert liste[0]["kaynak"] == "dosya"
    assert all(GIZLI not in satir for satir in satirlar)


async def test_ice_aktarma_gecersiz_ad_ve_eksik_kaynak_turkce_hata(oturum, cerez_dosyasi):
    session, satirlar = oturum

    await session.handle(
        Request(id="5", name="tarayici.ice_aktar", data={"ad": "../x", "yol": str(cerez_dosyasi)})
    )
    await session.handle(Request(id="6", name="tarayici.ice_aktar", data={"ad": "is"}))

    assert _sonuc(satirlar, "5")["ok"] is False
    assert "Profil adı" in _sonuc(satirlar, "5")["metin"]
    assert "Chrome profili" in _sonuc(satirlar, "6")["metin"]


async def test_silme_ve_olmayan_profil(oturum, cerez_dosyasi):
    session, satirlar = oturum
    await session.handle(
        Request(id="7", name="tarayici.ice_aktar", data={"ad": "is", "yol": str(cerez_dosyasi)})
    )

    await session.handle(Request(id="8", name="tarayici.sil", data={"ad": "is"}))
    await session.handle(Request(id="9", name="tarayici.sil", data={"ad": "is"}))

    assert _sonuc(satirlar, "8")["ok"] is True
    assert _sonuc(satirlar, "9")["ok"] is False


async def test_varsayilan_profil_yazilir_ve_oturum_yapilandirmasina_yansir(
    oturum, cerez_dosyasi, tmp_path, monkeypatch
):
    from fusion_cli.appserver import browser_profiles as rpc

    session, satirlar = oturum
    yazilan: dict[str, object] = {}
    monkeypatch.setattr(
        rpc, "write_browser_setting", lambda config, key, value: yazilan.update({key: value})
    )
    await session.handle(
        Request(id="10", name="tarayici.ice_aktar", data={"ad": "is", "yol": str(cerez_dosyasi)})
    )

    await session.handle(Request(id="11", name="tarayici.varsayilan", data={"ad": "is"}))
    await session.handle(Request(id="12", name="tarayici.varsayilan", data={"ad": "yok"}))

    assert _sonuc(satirlar, "11") == {"ok": True, "varsayilan": "is"}
    assert yazilan == {"default_profile": "is"}
    assert session._state.config.browser.default_profile == "is"
    assert _sonuc(satirlar, "12")["ok"] is False


async def test_giris_gecersiz_adres_reddedilir(oturum):
    session, satirlar = oturum

    await session.handle(
        Request(id="13", name="tarayici.giris", data={"ad": "is", "url": "ftp://x"})
    )

    assert _sonuc(satirlar, "13")["ok"] is False


async def test_chrome_ice_aktarma_alan_adi_olmadan_reddedilir(oturum, monkeypatch):
    """Ölçüldü (31 Ekim): arayüz tüm alan adlarını önceden işaretliyordu; RPC de süzgeçsiz
    kabul ediyordu — bütün Chrome oturumu ajana taşınıyordu."""
    from fusion_cli.appserver import browser_profiles as rpc

    monkeypatch.setattr(rpc, "find_chrome_profile", lambda *_: pytest.fail("Chrome'a bakılmamalı"))
    session, satirlar = oturum

    await session.handle(
        Request(id="20", name="tarayici.ice_aktar", data={"ad": "is", "chrome_profil": "Default"})
    )

    veri = _sonuc(satirlar, "20")
    assert veri["ok"] is False and "alan adı" in veri["metin"]


async def test_tarayici_ayar_headless_ve_profiller_yazilir(oturum, monkeypatch):
    from fusion_cli.appserver import browser_profiles as rpc

    session, satirlar = oturum
    yazilan: dict[str, object] = {}
    monkeypatch.setattr(
        rpc, "write_browser_setting", lambda config, key, value: yazilan.update({key: value})
    )

    await session.handle(
        Request(id="21", name="tarayici.ayar", data={"anahtar": "headless", "deger": False})
    )
    await session.handle(
        Request(id="22", name="tarayici.ayar", data={"anahtar": "profiles_enabled", "deger": False})
    )
    await session.handle(
        Request(id="23", name="tarayici.ayar", data={"anahtar": "default_profile", "deger": "x"})
    )
    await session.handle(
        Request(id="24", name="tarayici.ayar", data={"anahtar": "headless", "deger": "evet"})
    )

    assert _sonuc(satirlar, "21") == {"ok": True, "anahtar": "headless", "deger": False}
    assert yazilan == {"headless": False, "profiles_enabled": False}
    assert session._state.config.browser.headless is False
    assert session._state.config.browser.profiles_enabled is False
    assert _sonuc(satirlar, "23")["ok"] is False
    assert _sonuc(satirlar, "24")["ok"] is False
    await session.handle(Request(id="25", name="tarayici.profiller", data={}))
    assert _sonuc(satirlar, "25")["etkin"] is False
