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
