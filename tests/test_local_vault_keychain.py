"""macOS kasa ana anahtarı önce Keychain'de durur; eski dosya yedekli göç eder (L2-27).

Gerçek Keychain'e DOKUNULMAZ: sahte arka uç enjekte edilir.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fcntl")

from fusion_cli.config import local_vault
from fusion_cli.config.credentials import FernetSecretStore
from fusion_cli.config.local_vault import KeychainError


class SahteAnahtarlik:
    """Bellekte Keychain; istenirse okuma/yazma hata verir ya da yazma sessizce kaybolur."""

    def __init__(self, deger=None, *, okuma_hatasi=False, yazma_hatasi=False, yazma_kaybolur=False):
        self.deger = deger
        self.okuma_hatasi = okuma_hatasi
        self.yazma_hatasi = yazma_hatasi
        self.yazma_kaybolur = yazma_kaybolur
        self.yazimlar = 0

    def get(self):
        if self.okuma_hatasi:
            raise KeychainError("izin yok")
        return self.deger

    def set(self, value):
        if self.yazma_hatasi:
            raise KeychainError("izin yok")
        self.yazimlar += 1
        if not self.yazma_kaybolur:
            self.deger = value


@pytest.fixture(autouse=True)
def eski_anahtari_sorma(monkeypatch):
    monkeypatch.setattr(local_vault, "_legacy_key", lambda: None)


def test_yeni_kurulumda_anahtar_yalniz_keychainde_durur(tmp_path):
    kc = SahteAnahtarlik()
    key = local_vault.local_master_key(tmp_path, keychain=kc)
    assert key and kc.deger == key
    assert not (tmp_path / "vault/master.key").exists()
    # İkinci açılış aynı anahtarı Keychain'den okur, ek yazım yapmaz.
    assert local_vault.local_master_key(tmp_path, keychain=kc) == key
    assert kc.yazimlar == 1


def test_eski_dosya_anahtari_keychaina_tasinir_ve_yedeklenir(tmp_path):
    kasa = tmp_path / "vault"
    kasa.mkdir()
    (kasa / "master.key").write_text("eski-ana-anahtar")
    eski = FernetSecretStore(kasa / "secrets.enc", secret_key="eski-ana-anahtar")
    eski.set("TEST_KEY", "test-value")
    kc = SahteAnahtarlik()

    key = local_vault.local_master_key(tmp_path, keychain=kc)

    assert key == "eski-ana-anahtar" and kc.deger == key
    assert not (kasa / "master.key").exists()
    assert (kasa / "master.key.migrated").read_text() == "eski-ana-anahtar"
    assert (kasa / "master.key.migrated").stat().st_mode & 0o777 == 0o600
    # Depo aynı anahtarla okunmaya devam eder: sırlar kaybolmaz.
    assert FernetSecretStore(kasa / "secrets.enc", secret_key=key).get("TEST_KEY") == "test-value"


def test_goc_idempotenttir(tmp_path):
    kasa = tmp_path / "vault"
    kasa.mkdir()
    (kasa / "master.key").write_text("eski-ana-anahtar")
    kc = SahteAnahtarlik()
    ilk = local_vault.local_master_key(tmp_path, keychain=kc)
    ikinci = local_vault.local_master_key(tmp_path, keychain=kc)
    assert ilk == ikinci == "eski-ana-anahtar"
    assert kc.yazimlar == 1
    assert (kasa / "master.key.migrated").read_text() == "eski-ana-anahtar"


def test_keychain_okunamazsa_dosya_yontemiyle_calisir(tmp_path):
    kasa = tmp_path / "vault"
    kasa.mkdir()
    (kasa / "master.key").write_text("eski-ana-anahtar")
    kc = SahteAnahtarlik(okuma_hatasi=True)
    assert local_vault.local_master_key(tmp_path, keychain=kc) == "eski-ana-anahtar"
    assert (kasa / "master.key").read_text() == "eski-ana-anahtar"  # dosya yerinde


def test_keychaine_yazilamazsa_dosya_yerinde_kalir(tmp_path):
    kasa = tmp_path / "vault"
    kasa.mkdir()
    (kasa / "master.key").write_text("eski-ana-anahtar")
    kc = SahteAnahtarlik(yazma_hatasi=True)
    assert local_vault.local_master_key(tmp_path, keychain=kc) == "eski-ana-anahtar"
    assert (kasa / "master.key").exists()
    assert not (kasa / "master.key.migrated").exists()


def test_yazma_dogrulanamazsa_dosya_silinmez(tmp_path):
    """Keychain yazımı sessizce kaybolursa (okuyunca boş) dosya anahtarı asla bırakılmaz."""
    kasa = tmp_path / "vault"
    kasa.mkdir()
    (kasa / "master.key").write_text("eski-ana-anahtar")
    kc = SahteAnahtarlik(yazma_kaybolur=True)
    assert local_vault.local_master_key(tmp_path, keychain=kc) == "eski-ana-anahtar"
    assert (kasa / "master.key").exists()


def test_yeni_kurulumda_keychain_yoksa_eski_dosya_yontemi(tmp_path):
    kc = SahteAnahtarlik(yazma_hatasi=True)
    key = local_vault.local_master_key(tmp_path, keychain=kc)
    assert (tmp_path / "vault/master.key").read_text() == key
    assert (tmp_path / "vault/master.key").stat().st_mode & 0o777 == 0o600


def test_keychain_hatasinda_mevcut_kasa_icin_yeni_anahtar_uretilmez(tmp_path):
    """Kasa var, anahtar yalnız Keychain'de ve okunamıyor: sahte yeni anahtar üretme."""
    kasa = tmp_path / "vault"
    kasa.mkdir()
    FernetSecretStore(kasa / "secrets.enc", secret_key="gizli").set("A", "1")
    kc = SahteAnahtarlik(okuma_hatasi=True)
    with pytest.raises(ValueError, match="Keychain"):
        local_vault.local_master_key(tmp_path, keychain=kc)
    assert not (kasa / "master.key").exists()


def test_yedek_dosyadan_anahtar_geri_alinir_keychain_bos_kalirsa(tmp_path):
    """Göçten sonra Keychain öğesi silinirse `.migrated` yedeği kasayı kurtarır."""
    kasa = tmp_path / "vault"
    kasa.mkdir()
    (kasa / "master.key.migrated").write_text("eski-ana-anahtar")
    kc = SahteAnahtarlik()
    assert local_vault.local_master_key(tmp_path, keychain=kc) == "eski-ana-anahtar"
    assert kc.deger == "eski-ana-anahtar"


def test_iki_yerde_farkli_anahtar_varsa_kasayi_cozen_secilir(tmp_path):
    kasa = tmp_path / "vault"
    kasa.mkdir()
    (kasa / "master.key").write_text("dosyadaki")
    FernetSecretStore(kasa / "secrets.enc", secret_key="dosyadaki").set("A", "1")
    kc = SahteAnahtarlik("keychaindeki")
    assert local_vault.local_master_key(tmp_path, keychain=kc) == "dosyadaki"
    assert (kasa / "master.key").exists()  # çelişkide dosyaya dokunulmaz


def test_eski_kok_kasasi_eski_keychain_anahtariyla_tasinir_yeni_anahtar_keychaine(
    tmp_path, monkeypatch
):
    eski = FernetSecretStore(tmp_path / "secrets.enc", secret_key="test-only")
    eski.set("TEST_KEY", "test-value")
    monkeypatch.setattr(local_vault, "_legacy_key", lambda: "test-only")
    kc = SahteAnahtarlik()
    key = local_vault.local_master_key(tmp_path, keychain=kc)
    assert key == "test-only" and kc.deger == "test-only"
    yeni = FernetSecretStore(tmp_path / "vault/secrets.enc", secret_key=key)
    assert yeni.get("TEST_KEY") == "test-value"


def test_hesap_adi_kok_dizine_ozeldir(tmp_path):
    a = local_vault.keychain_account(tmp_path / "a")
    b = local_vault.keychain_account(tmp_path / "b")
    assert a != b and a.startswith("vault-master-key:")


def test_keychain_kapatma_ortami_sistem_arka_ucunu_kullandirmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    assert local_vault.system_keychain(tmp_path) is None


def test_sistem_arka_ucu_keyringe_gider_ve_hatayi_cevirir(tmp_path, monkeypatch):
    """Gerçek Keychain yerine sahte `keyring` ve sahte diyalog kapatıcı kullanılır."""
    import contextlib

    kayit = {}

    def al(servis, hesap):
        return kayit.get((servis, hesap))

    def koy(servis, hesap, deger):
        kayit[(servis, hesap)] = deger

    monkeypatch.setattr("keyring.get_password", al)
    monkeypatch.setattr("keyring.set_password", koy)
    monkeypatch.setattr(local_vault, "_no_keychain_ui", contextlib.nullcontext)
    monkeypatch.delenv("FUSION_KEYCHAIN", raising=False)

    kc = local_vault.system_keychain(tmp_path)
    assert kc is not None and kc.get() is None
    kc.set("deger")
    assert kc.get() == "deger"
    assert next(iter(kayit))[0] == "fusion-cli"

    def patla(*_a):
        raise RuntimeError("anahtar zinciri yok")

    monkeypatch.setattr("keyring.get_password", patla)
    with pytest.raises(KeychainError):
        kc.get()
