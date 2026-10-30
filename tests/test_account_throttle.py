"""Hesap giriş/silme/kurtarma deneme sınırı: hesap başına artan bekleme, kalıcı kilit yok.

Ölçüldü (30 Ekim): `hesap.giris`, `hesap.sil` ve `hesap.kurtar` hatalı denemeyi sınırsız ve
bekletmeden kabul ediyordu (her deneme ≈90 ms scrypt; saniyede ~10 tahmin).
"""

from __future__ import annotations

import pytest

from fusion_cli.accounts.store import SqliteAccountStore
from fusion_cli.accounts.throttle import AttemptThrottle
from fusion_cli.appserver.accounts import AccountService
from fusion_cli.config.paths import ENV_ACCOUNT


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    def now(self) -> float:
        return self.t


# --- AttemptThrottle -------------------------------------------------------- #


def test_serbest_deneme_hakki_icinde_bekleme_yok():
    saat = FakeClock()
    sinir = AttemptThrottle(saat, free_attempts=3)
    for _ in range(3):
        assert sinir.retry_after("a") == 0
        sinir.record_failure("a")
    assert sinir.retry_after("a") > 0  # dördüncüden önce bekleme başlar


def test_bekleme_her_hatada_katlanir_ve_tavanda_durur():
    saat = FakeClock()
    sinir = AttemptThrottle(saat, free_attempts=1, base_delay_s=2.0, max_delay_s=10.0)
    beklemeler = []
    for _ in range(6):
        sinir.record_failure("a")
        beklemeler.append(sinir.retry_after("a"))
        saat.t += beklemeler[-1]  # beklemeyi bitir, yeniden dene
    assert beklemeler == [2.0, 4.0, 8.0, 10.0, 10.0, 10.0]


def test_bekleme_sureye_gore_azalir_ve_biter():
    saat = FakeClock()
    sinir = AttemptThrottle(saat, free_attempts=1, base_delay_s=4.0)
    sinir.record_failure("a")
    saat.t += 1.5
    assert sinir.retry_after("a") == pytest.approx(2.5)
    saat.t += 2.5
    assert sinir.retry_after("a") == 0  # kalıcı kilit yok


def test_hesaplar_birbirinden_bagimsiz():
    saat = FakeClock()
    sinir = AttemptThrottle(saat, free_attempts=1)
    sinir.record_failure("a")
    assert sinir.retry_after("a") > 0 and sinir.retry_after("b") == 0


def test_basari_sayaci_sifirlar():
    saat = FakeClock()
    sinir = AttemptThrottle(saat, free_attempts=2)
    sinir.record_failure("a")
    sinir.record_success("a")
    sinir.record_failure("a")
    assert sinir.retry_after("a") == 0


def test_uzun_bos_sure_sayaci_sifirlar():
    saat = FakeClock()
    sinir = AttemptThrottle(saat, free_attempts=1, idle_reset_s=60)
    for _ in range(4):
        sinir.record_failure("a")
    saat.t += 61
    sinir.record_failure("a")
    assert sinir.retry_after("a") == 2.0  # ilk hata gibi


def test_anahtar_sayisi_sinirlidir():
    saat = FakeClock()
    sinir = AttemptThrottle(saat, free_attempts=1, max_keys=3)
    for ad in "abcde":
        sinir.record_failure(ad)
        saat.t += 1
    assert sinir.tracked_keys() == 3
    assert sinir.retry_after("a") == 0  # en eski unutuldu


# --- AccountService ---------------------------------------------------------- #


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv(ENV_ACCOUNT, "")
    monkeypatch.delenv(ENV_ACCOUNT)
    saat = FakeClock()
    store = SqliteAccountStore(tmp_path / "accounts.db")
    servis = AccountService(store, throttle=AttemptThrottle(saat, free_attempts=3))
    kayit = servis.register(
        {"kullanici_adi": "emir", "eposta": "e@ornek.com", "parola": "parola1234", "avatar": ""}
    )
    return servis, saat, kayit


def _yanlis_giris(servis, kimlik="emir"):
    return servis.login({"kimlik": kimlik, "parola": "yanlis-parola"})


def test_ucuncu_hatadan_sonra_giris_bekletilir_dogru_parola_bile_reddedilir(rig):
    servis, _, _ = rig
    for _ in range(3):
        assert "hatalı" in _yanlis_giris(servis)["metin"]

    yanit = servis.login({"kimlik": "emir", "parola": "parola1234"})

    assert yanit["ok"] is False and yanit["bekleme_sn"] > 0
    assert "saniye" in yanit["metin"]


def test_bekleme_bitince_dogru_parola_girer_ve_sayac_sifirlanir(rig):
    servis, saat, _ = rig
    for _ in range(3):
        _yanlis_giris(servis)
    saat.t += 3

    assert servis.login({"kimlik": "emir", "parola": "parola1234"})["ok"] is True
    for _ in range(3):  # sayaç sıfırlandı: yeniden üç serbest deneme
        assert "bekleme_sn" not in _yanlis_giris(servis)


def test_bekleme_sirasinda_gelen_istekler_sayaci_buyutmez(rig):
    servis, saat, _ = rig
    for _ in range(3):
        _yanlis_giris(servis)
    ilk = _yanlis_giris(servis)["bekleme_sn"]
    for _ in range(20):
        _yanlis_giris(servis)
    saat.t += ilk
    assert "bekleme_sn" not in _yanlis_giris(servis)  # 4. gerçek hata: 2 sn beklemesi başlar


def test_ayni_hesap_kullanici_adi_ve_eposta_ile_ortak_sayilir(rig):
    servis, _, _ = rig
    _yanlis_giris(servis, "emir")
    _yanlis_giris(servis, "e@ornek.com")
    _yanlis_giris(servis, "EMIR")
    assert "bekleme_sn" in _yanlis_giris(servis, "e@ornek.com")


def test_var_olmayan_kullanici_da_ayni_sekilde_sinirlanir_varligi_sizmaz(rig):
    servis, _, _ = rig
    for _ in range(3):
        _yanlis_giris(servis, "yok-boyle-biri")
    assert "bekleme_sn" in _yanlis_giris(servis, "yok-boyle-biri")


def test_baska_hesap_etkilenmez(rig):
    servis, _, _ = rig
    servis.register(
        {"kullanici_adi": "ikinci", "eposta": "i@ornek.com", "parola": "ikinci12345", "avatar": ""}
    )
    for _ in range(4):
        _yanlis_giris(servis, "emir")
    assert servis.login({"kimlik": "ikinci", "parola": "ikinci12345"})["ok"] is True


def test_hesap_silme_hatali_denemeleri_de_sinirlanir(rig):
    servis, _, kayit = rig
    kimlik = kayit["hesap"]["kimlik"]
    for _ in range(3):
        assert servis.remove({"kimlik": kimlik, "parola": "yanlis"})["ok"] is False

    yanit = servis.remove({"kimlik": kimlik, "parola": "parola1234"})

    assert yanit["ok"] is False and yanit["bekleme_sn"] > 0
    assert len(servis.status()["hesaplar"]) == 1  # silinmedi


def test_silme_ve_giris_ayni_hesap_sayacini_paylasir(rig):
    servis, _, kayit = rig
    kimlik = kayit["hesap"]["kimlik"]
    for _ in range(2):
        _yanlis_giris(servis)
    servis.remove({"kimlik": kimlik, "parola": "yanlis"})
    assert "bekleme_sn" in _yanlis_giris(servis)


def test_kurtarma_hatali_kodu_sinirlanir(rig):
    servis, _, _ = rig
    istek = {"kimlik": "emir", "kurtarma_kodu": "YANLIS-KOD-0000", "yeni_parola": "yeniparola12"}
    for _ in range(3):
        assert servis.recover(istek)["ok"] is False
    assert "bekleme_sn" in servis.recover(istek)


def test_kurtarmada_kisa_yeni_parola_deneme_sayilmaz(rig):
    servis, _, _ = rig
    istek = {"kimlik": "emir", "kurtarma_kodu": "X", "yeni_parola": "kisa"}
    for _ in range(6):
        servis.recover(istek)
    assert "bekleme_sn" not in servis.recover(istek)


def test_bos_parolayla_silme_istegi_deneme_sayilmaz(rig):
    servis, _, kayit = rig
    kimlik = kayit["hesap"]["kimlik"]
    for _ in range(10):
        servis.remove({"kimlik": kimlik})
    assert servis.remove({"kimlik": kimlik, "parola": "parola1234"})["ok"] is True
