"""Hesap RPC sözleşmesi: ne döndüğü ve daha önemlisi NE DÖNMEDİĞİ."""

from __future__ import annotations

import pytest

from fusion_cli.accounts.store import SqliteAccountStore
from fusion_cli.appserver.accounts import AccountService
from fusion_cli.config.paths import ENV_ACCOUNT


@pytest.fixture
def servis(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    # Üretim kodu `FUSION_ACCOUNT`u KENDİSİ yazar; monkeypatch yalnız kendi
    # yaptığı değişikliği geri alır. Anahtarı önce sahiplenip sonra siliyoruz,
    # böylece teardown onu mutlaka eski hâline döndürür — aksi halde etkin hesap
    # sonraki testlere sızıyor ve onlar var olmayan bir dizine yazmaya kalkıyordu.
    monkeypatch.setenv(ENV_ACCOUNT, "")
    monkeypatch.delenv(ENV_ACCOUNT)
    return AccountService(SqliteAccountStore(tmp_path / "accounts.db"))


def _kayit(servis, ad="emirhan", posta="e@ornek.com", parola="parola1234"):
    return servis.register(
        {"kullanici_adi": ad, "eposta": posta, "parola": parola, "avatar": "🏍️"}
    )


def test_ilk_acilista_kurulum_gerekli_bildirilir(servis):
    durum = servis.status()

    assert durum["ok"] is True
    assert durum["kurulum_gerekli"] is True
    assert durum["hesaplar"] == []


def test_kayit_hesabi_acar_ve_kurtarma_kodunu_bir_kez_verir(servis):
    sonuc = _kayit(servis)

    assert sonuc["ok"] is True
    assert sonuc["kurtarma_kodu"]
    assert sonuc["hesap"]["kullanici_adi"] == "emirhan"
    # Kod YALNIZ kayıtta döner; durum çağrısı onu bir daha göstermez.
    assert "kurtarma_kodu" not in servis.status()


def test_yanitlar_parola_veya_karma_tasimaz(servis):
    """Hesap bilgisi arayüze kadar gider; karma oraya kadar gitmemeli."""
    sonuc = _kayit(servis)
    giris = servis.login({"kimlik": "emirhan", "parola": "parola1234"})

    for yanit in (sonuc["hesap"], giris["hesap"], servis.status()["hesaplar"][0]):
        assert "parola" not in yanit
        assert not any("hash" in anahtar or "karma" in anahtar for anahtar in yanit)
    assert "parola1234" not in str(sonuc) + str(giris)


def test_kayit_sonrasi_hesap_etkin_ve_hatirlanir(servis):
    sonuc = _kayit(servis)

    assert servis.status()["etkin"] == sonuc["hesap"]["kimlik"]


def test_cikis_etkin_hesabi_birakir(servis):
    _kayit(servis)

    assert servis.logout()["ok"] is True
    assert servis.status()["etkin"] == ""


def test_hatali_giris_hangisinin_yanlis_oldugunu_soylemez(servis):
    """Var olan kullanıcı adlarını deneme yanılmayla bulmak kolaylaşmamalı."""
    _kayit(servis)

    yok = servis.login({"kimlik": "bulunmayan", "parola": "parola1234"})
    yanlis = servis.login({"kimlik": "emirhan", "parola": "yanlisparola"})

    assert yok["ok"] is False and yanlis["ok"] is False
    assert yok["metin"] == yanlis["metin"]


def test_kurtarma_kodu_yeni_parola_belirler(servis):
    sonuc = _kayit(servis)

    kurtarma = servis.recover(
        {
            "kimlik": "emirhan",
            "kurtarma_kodu": sonuc["kurtarma_kodu"],
            "yeni_parola": "yeniparola99",
        }
    )

    assert kurtarma["ok"] is True
    assert servis.login({"kimlik": "emirhan", "parola": "yeniparola99"})["ok"] is True


def test_silinen_hesap_listeden_ve_etkinden_dusulur(servis):
    sonuc = _kayit(servis)
    kimlik = sonuc["hesap"]["kimlik"]

    assert servis.remove({"kimlik": kimlik})["ok"] is True

    durum = servis.status()
    assert durum["hesaplar"] == []
    assert durum["etkin"] == ""


def test_hatirlanan_hesap_silinmisse_acik_hesap_yok_sayilir(servis):
    """Veritabanı elle silinmiş olabilir; işaretçi tek başına kanıt değildir."""
    sonuc = _kayit(servis)
    servis._store.delete(sonuc["hesap"]["kimlik"])

    assert servis.status()["etkin"] == ""


def test_ikinci_hesap_ilk_hesabin_ayarlarini_devralmaz(servis):
    """Devralma yalnız HESAPSIZ kurulumdan ilk hesaba olur."""
    _kayit(servis)
    ikinci = _kayit(servis, ad="ikinci", posta="i@ornek.com")

    assert ikinci["ok"] is True
    assert ikinci["devralinan_ayarlar"] == []
