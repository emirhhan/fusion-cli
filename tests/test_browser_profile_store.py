"""Tarayıcı profili deposu: şifreli çerez dosyası + açık meta veri (P-023).

Ölçüldü (31 Ekim): `user_data_dir()/browser_profiles` diye bir depo yoktu; web MODEL
profilleri (`web_profiles/<sağlayıcı>/<hesap>`) yalnız ChatGPT/Claude/Gemini/Copilot
için ve Chrome kullanıcı veri dizini biçimindeydi, ajanın Playwright bağlamına
`storage_state` olarak verilemiyordu.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.config.browser_profiles import BrowserProfileStore
from fusion_cli.core.cookie_files import Cookie
from fusion_cli.core.errors import BrowserProfileError

GIZLI_DEGER = "cerez-degeri-GIZLI-9f8e7d"


def _cerezler() -> tuple[Cookie, ...]:
    return (
        Cookie(name="sid", value=GIZLI_DEGER, domain=".example.com", secure=True),
        Cookie(name="pref", value="tr", domain="shop.example.org", expires=1893456000.0),
    )


@pytest.fixture
def depo(tmp_path):
    return BrowserProfileStore(
        tmp_path / "browser_profiles", secret_key="test-anahtari", clock=lambda: 1_700_000_000.0
    )


def test_kaydedilen_profil_listede_yalniz_alan_adi_ve_sayi_ile_gorunur(depo):
    ozet = depo.save("is", _cerezler(), source="dosya")

    assert ozet.name == "is"
    assert ozet.domains == ("example.com", "shop.example.org")
    assert ozet.cookie_count == 2
    assert ozet.source == "dosya"
    assert ozet.imported_at == 1_700_000_000.0
    assert ozet.last_used_at is None
    assert [item.name for item in depo.list()] == ["is"]
    assert GIZLI_DEGER not in repr(ozet)


def test_cerez_degeri_diske_acik_yazilmaz(depo, tmp_path):
    depo.save("is", _cerezler(), source="dosya")

    for dosya in (tmp_path / "browser_profiles" / "is").iterdir():
        assert GIZLI_DEGER.encode() not in dosya.read_bytes(), dosya.name
    meta = json.loads((tmp_path / "browser_profiles" / "is" / "profile.json").read_text("utf-8"))
    assert "cookies" not in meta and "value" not in json.dumps(meta)


def test_storage_state_degerleri_geri_verir_ve_son_kullanimi_isaretler(depo):
    depo.save("is", _cerezler(), source="dosya")

    durum = depo.storage_state("is")

    assert durum["cookies"][0]["value"] == GIZLI_DEGER
    assert durum["cookies"][0]["sameSite"] == "Lax"
    assert depo.summary("is").last_used_at == 1_700_000_000.0


def test_izinli_alan_adi_listesi_disindaki_cerezler_tarayiciya_gitmez(depo):
    depo.save("is", _cerezler(), source="dosya", allowed_domains=("example.org",))

    durum = depo.storage_state("is")

    assert [cookie["name"] for cookie in durum["cookies"]] == ["pref"]
    assert depo.summary("is").allowed_domains == ("example.org",)
    # Meta veri yine TÜM alan adlarını listeler; kullanıcı neyi dışarıda bıraktığını görür.
    assert depo.summary("is").domains == ("example.com", "shop.example.org")


def test_guncelleme_izin_listesini_ve_kaynagi_korur(depo):
    depo.save("is", _cerezler(), source="chrome", allowed_domains=("example.com",))

    depo.update_cookies("is", (Cookie(name="sid", value="yeni", domain=".example.com"),))

    ozet = depo.summary("is")
    assert ozet.source == "chrome"
    assert ozet.allowed_domains == ("example.com",)
    assert ozet.cookie_count == 1
    assert depo.storage_state("is")["cookies"][0]["value"] == "yeni"


def test_olmayan_profil_anlasilir_hata_verir(depo):
    with pytest.raises(BrowserProfileError, match="yok"):
        depo.storage_state("yok-boyle")
    with pytest.raises(BrowserProfileError):
        depo.summary("yok-boyle")


def test_silme_dizini_kaldirir_ve_ikinci_silme_false_doner(depo, tmp_path):
    depo.save("is", _cerezler(), source="dosya")

    assert depo.delete("is") is True
    assert not (tmp_path / "browser_profiles" / "is").exists()
    assert depo.delete("is") is False


def test_gecersiz_ad_kaydedilmez(depo):
    with pytest.raises(BrowserProfileError):
        depo.save("../kacis", _cerezler(), source="dosya")


def test_anahtar_yokken_depo_kullanilamaz_ve_sebebini_soyler(tmp_path):
    depo = BrowserProfileStore(tmp_path / "bp", secret_key=None)

    assert depo.available is False
    with pytest.raises(BrowserProfileError, match="anahtar"):
        depo.save("is", _cerezler(), source="dosya")
    assert depo.list() == ()


def test_bozuk_meta_veri_listeyi_cokertmez(depo, tmp_path):
    depo.save("is", _cerezler(), source="dosya")
    (tmp_path / "browser_profiles" / "bozuk").mkdir()
    (tmp_path / "browser_profiles" / "bozuk" / "profile.json").write_text("{bozuk", "utf-8")

    assert [item.name for item in depo.list()] == ["is"]


# --- Bağımsız inceleme bulguları (31 Ekim) ------------------------------------ #


def test_guncelleme_onay_listesi_disindaki_cerezleri_yazmaz(depo):
    """Ölçüldü: kapanışta bağlamın TÜM çerezleri yazılıyordu; onay dışı sitelerin çerezi
    şifreli dosyada ve özetin alan adı listesinde birikiyordu."""
    depo.save("is", _cerezler(), source="dosya", allowed_domains=("example.com",))

    depo.update_cookies(
        "is",
        (
            Cookie(name="sid", value="yeni", domain=".example.com"),
            Cookie(name="trk", value="izleyici", domain="ads.tracker.net"),
        ),
    )

    ozet = depo.summary("is")
    assert ozet.domains == ("example.com",)
    assert ozet.cookie_count == 1
    sifreli = (depo.root / "is" / "cookies.enc").read_bytes()
    assert b"tracker" not in sifreli  # şifreli olsa da yazılmadığını özetten biliyoruz


def test_onay_listesi_bos_profil_guncellemede_suzulmez(depo):
    depo.save("is", _cerezler(), source="giris")

    depo.update_cookies("is", (Cookie(name="t", value="1", domain="other.net"),))

    assert depo.summary("is").domains == ("other.net",)


def test_son_kullanim_damgasi_yazilamazsa_oturum_yine_verilir(depo, tmp_path):
    """Ölçüldü: `last_used_at` yazımı `storage_state`'i düşürüyordu (salt okunur dizin,
    dolu disk); yalnız bir damga yüzünden `browser_open` hata veriyordu."""
    depo.save("is", _cerezler(), source="dosya")
    klasor = tmp_path / "browser_profiles" / "is"
    klasor.chmod(0o500)
    try:
        durum = depo.storage_state("is")
    finally:
        klasor.chmod(0o700)

    assert durum["cookies"][0]["value"] == GIZLI_DEGER
    assert depo.summary("is").last_used_at is None


def test_meta_veri_atomik_yazilir(depo, tmp_path):
    depo.save("is", _cerezler(), source="dosya")
    depo.storage_state("is")

    kalanlar = [p.name for p in (tmp_path / "browser_profiles" / "is").iterdir()]
    # Sır deposu `.bak` bırakır (tasarım); geçici `.tmp` kalmamalı.
    assert not [ad for ad in kalanlar if ad.endswith(".tmp")], kalanlar
    json.loads((tmp_path / "browser_profiles" / "is" / "profile.json").read_text("utf-8"))


def test_ana_anahtar_degisirse_profil_hatasi_doner(depo, tmp_path):
    """Ölçüldü: `FernetSecretStore.get` ConfigError fırlatıyor, araç yalnız
    BrowserProfileError yakalıyordu; kullanıcı profil bağlamı olmayan metin görüyordu."""
    depo.save("is", _cerezler(), source="dosya")
    baska = BrowserProfileStore(tmp_path / "browser_profiles", secret_key="baska-anahtar")

    with pytest.raises(BrowserProfileError, match="is"):
        baska.storage_state("is")


def test_origins_localstorage_saklanir_ve_onayli_alan_adina_suzulur(depo):
    """Ölçüldü: `to_storage_state` hep `origins: []` yazıyordu; JWT'yi localStorage'da
    tutan SPA'lar giriş penceresinden sonra girişsiz görünüyordu."""
    origins = (
        {"origin": "https://app.example.com", "localStorage": [{"name": "jwt", "value": "J1"}]},
        {"origin": "https://other.net", "localStorage": [{"name": "x", "value": "y"}]},
    )
    depo.save("is", _cerezler(), source="giris", allowed_domains=("example.com",), origins=origins)

    durum = depo.storage_state("is")

    assert durum["origins"] == [origins[0]]
    sifresiz = json.dumps(json.loads((depo.root / "is" / "profile.json").read_text("utf-8")))
    assert "J1" not in sifresiz

    depo.update_cookies(
        "is",
        (Cookie(name="sid", value="n", domain=".example.com"),),
        origins=(
            {"origin": "https://app.example.com", "localStorage": [{"name": "jwt", "value": "J2"}]},
        ),
    )
    assert depo.storage_state("is")["origins"][0]["localStorage"][0]["value"] == "J2"
