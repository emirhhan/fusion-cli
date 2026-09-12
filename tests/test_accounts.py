"""Yerel hesap deposu, parola karması ve hesap başına yapılandırma.

Hesaplar sunucuda değil kullanıcının bilgisayarındadır; testler de o sözü
denetler: parola düz metin tutulmaz, kurtarma kodu tek kullanımlıktır ve bir
hesabın ayarları diğerini görmez.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.accounts.avatars import AVATAR_MAX_BYTES, is_image_avatar, store_avatar_image
from fusion_cli.accounts.passwords import (
    PASSWORD_MIN_CHARS,
    format_recovery_code,
    generate_recovery_code,
    hash_secret,
    normalize_recovery_code,
    verify_secret,
)
from fusion_cli.accounts.session import (
    activate_account,
    adopt_legacy_config,
    clear_active_account,
    forget_remembered_account,
    remember_account,
    remembered_account,
    remove_account_files,
)
from fusion_cli.accounts.store import AccountError, SqliteAccountStore
from fusion_cli.config.paths import ENV_ACCOUNT, account_config_dir, user_config_dir


@pytest.fixture
def store(tmp_path):
    return SqliteAccountStore(tmp_path / "accounts.db")


@pytest.fixture
def yerel_kok(tmp_path, monkeypatch):
    """Yapılandırma kökünü teste taşı; gerçek kullanıcı dizinine dokunulmasın."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    # Üretim kodu `FUSION_ACCOUNT`u KENDİSİ yazar; monkeypatch yalnız kendi
    # yaptığı değişikliği geri alır. Anahtarı önce sahiplenip sonra siliyoruz,
    # böylece teardown onu mutlaka eski hâline döndürür — aksi halde etkin hesap
    # sonraki testlere sızıyor ve onlar var olmayan bir dizine yazmaya kalkıyordu.
    monkeypatch.setenv(ENV_ACCOUNT, "")
    monkeypatch.delenv(ENV_ACCOUNT)
    return tmp_path


class TestParolaKarmasi:
    def test_karma_duz_parolayi_tasimaz(self):
        kayit = hash_secret("cok-gizli-parola")

        assert "cok-gizli-parola" not in kayit
        assert kayit.startswith("scrypt$")

    def test_ayni_parola_her_seferinde_farkli_karma_verir(self):
        """Tuz olmadan aynı parolalar aynı karmayı verir ve bu, bir veritabanı
        sızıntısında hangi kullanıcıların aynı parolayı kullandığını açık eder."""
        assert hash_secret("parola1234") != hash_secret("parola1234")

    def test_dogru_parola_dogrulanir_yanlis_reddedilir(self):
        kayit = hash_secret("parola1234")

        assert verify_secret("parola1234", kayit) is True
        assert verify_secret("parola1235", kayit) is False

    def test_bozuk_kayit_istisna_degil_ret_uretir(self):
        """Veritabanı elle kurcalanmışsa doğru davranış girişi reddetmektir;
        uygulamayı çökertmek değil."""
        for bozuk in ("", "scrypt$yok", "duz-metin", "scrypt$a$b$c$d$e"):
            assert verify_secret("parola1234", bozuk) is False


class TestKurtarmaKodu:
    def test_okunabilir_gruplara_ayrilir(self):
        kod = generate_recovery_code()

        assert "-" in kod
        assert all(parca.isalnum() for parca in kod.split("-"))

    def test_karisabilen_harfler_alfabede_yok(self):
        """Kodu elle yazan kullanıcı O/0 ve I/1 arasında kalmamalı."""
        harfler = set(normalize_recovery_code(generate_recovery_code()))

        assert not harfler & {"O", "I", "L", "U"}

    def test_tire_bosluk_ve_kucuk_harf_farki_onemsizdir(self):
        kod = generate_recovery_code()

        dagitik = kod.lower().replace("-", " ")
        assert normalize_recovery_code(dagitik) == normalize_recovery_code(kod)
        assert format_recovery_code(normalize_recovery_code(kod)) == kod


class TestHesapDeposu:
    def test_hesap_acilir_ve_listelenir(self, store):
        sonuc = store.create(username="emirhan", email="e@ornek.com", password="parola1234")

        assert sonuc.account.username == "emirhan"
        assert sonuc.recovery_code
        assert [hesap.username for hesap in store.list_accounts()] == ["emirhan"]

    def test_kisa_parola_ve_bozuk_eposta_reddedilir(self, store):
        with pytest.raises(AccountError, match=str(PASSWORD_MIN_CHARS)):
            store.create(username="a", email="a@b.com", password="kisa")
        with pytest.raises(AccountError, match="e-posta"):
            store.create(username="a", email="eposta-degil", password="parola1234")

    def test_ayni_kullanici_adi_ikinci_kez_acilamaz(self, store):
        store.create(username="emirhan", email="e@ornek.com", password="parola1234")

        with pytest.raises(AccountError, match="Kullanıcı adı"):
            store.create(username="EMIRHAN", email="baska@ornek.com", password="parola1234")

    def test_giris_kullanici_adi_veya_eposta_ile_yapilir(self, store):
        store.create(username="emirhan", email="e@ornek.com", password="parola1234")

        assert store.authenticate(identifier="emirhan", password="parola1234") is not None
        assert store.authenticate(identifier="e@ornek.com", password="parola1234") is not None
        assert store.authenticate(identifier="emirhan", password="yanlis1234") is None
        assert store.authenticate(identifier="yok", password="parola1234") is None

    def test_kurtarma_kodu_parolayi_degistirir_ve_tek_kullanimliktir(self, store):
        sonuc = store.create(username="emirhan", email="e@ornek.com", password="parola1234")

        degisti = store.reset_password(
            identifier="emirhan", recovery_code=sonuc.recovery_code, new_password="yeniparola1"
        )

        assert degisti is True
        assert store.authenticate(identifier="emirhan", password="yeniparola1") is not None
        # Aynı kod ikinci kez çalışmaz: ele geçen bir kod sonsuza kadar geçerli olamaz.
        assert (
            store.reset_password(
                identifier="emirhan",
                recovery_code=sonuc.recovery_code,
                new_password="ucuncuparola",
            )
            is False
        )

    def test_yanlis_kurtarma_kodu_parolayi_degistirmez(self, store):
        store.create(username="emirhan", email="e@ornek.com", password="parola1234")

        assert (
            store.reset_password(
                identifier="emirhan", recovery_code="AAAA-BBBB-CCCC-DDDD", new_password="yeni12345"
            )
            is False
        )
        assert store.authenticate(identifier="emirhan", password="parola1234") is not None

    def test_profil_guncellenir(self, store):
        hesap = store.create(
            username="emirhan", email="e@ornek.com", password="parola1234"
        ).account

        yeni = store.update_profile(
            hesap.account_id, username="emir", email="yeni@ornek.com", avatar="🏍️"
        )

        assert (yeni.username, yeni.email, yeni.avatar) == ("emir", "yeni@ornek.com", "🏍️")

    def test_silinen_hesap_listede_kalmaz(self, store):
        hesap = store.create(
            username="emirhan", email="e@ornek.com", password="parola1234"
        ).account

        assert store.delete(hesap.account_id) is True
        assert store.list_accounts() == ()
        assert store.delete(hesap.account_id) is False


class TestHesapYapilandirmasi:
    def test_etkin_hesap_yapilandirma_dizinini_ayirir(self, yerel_kok):
        hesapsiz = user_config_dir()

        activate_account("hesap-1")
        birinci = user_config_dir()
        activate_account("hesap-2")
        ikinci = user_config_dir()
        clear_active_account()

        assert birinci != ikinci
        assert birinci != hesapsiz
        assert user_config_dir() == hesapsiz

    def test_beni_hatirla_secimi_saklar_ve_cikis_siler(self, yerel_kok):
        remember_account("hesap-1")
        assert remembered_account() == "hesap-1"

        forget_remembered_account()
        assert remembered_account() == ""

    def test_ilk_hesap_eski_ayarlari_kopyalar_kaynagi_bozmaz(self, yerel_kok):
        """Hesap açmak, çalışan bir kurulumu geri alınamaz biçimde değiştirmemeli."""
        from fusion_cli.config.paths import base_config_dir

        eski = base_config_dir()
        eski.mkdir(parents=True, exist_ok=True)
        (eski / "config.yaml").write_text("runtime:\n  provider: gemini_web\n", encoding="utf-8")

        kopyalanan = adopt_legacy_config("hesap-1")

        assert "config.yaml" in kopyalanan
        assert (account_config_dir("hesap-1") / "config.yaml").exists()
        # Kaynak YERİNDE kalır.
        assert (eski / "config.yaml").exists()

    def test_devralma_var_olan_hesap_ayarini_ezmez(self, yerel_kok):
        from fusion_cli.config.paths import base_config_dir

        eski = base_config_dir()
        eski.mkdir(parents=True, exist_ok=True)
        (eski / "config.yaml").write_text("eski", encoding="utf-8")
        hedef = account_config_dir("hesap-1")
        hedef.mkdir(parents=True, exist_ok=True)
        (hedef / "config.yaml").write_text("hesabın kendi ayarı", encoding="utf-8")

        kopyalanan = adopt_legacy_config("hesap-1")

        assert kopyalanan == ()
        assert (hedef / "config.yaml").read_text(encoding="utf-8") == "hesabın kendi ayarı"

    def test_hesap_silinince_ayarlari_da_gider(self, yerel_kok):
        hedef = account_config_dir("hesap-1")
        hedef.mkdir(parents=True, exist_ok=True)
        (hedef / "config.yaml").write_text("veri", encoding="utf-8")

        remove_account_files("hesap-1")

        assert not hedef.exists()


class TestAvatar:
    def test_gorsel_hesabin_dizinine_kopyalanir(self, yerel_kok, tmp_path):
        """Kaynağa bağlı kalmak kırılgandı: kullanıcı dosyayı taşıyınca ya da
        harici diski çıkarınca avatar kaybolurdu."""
        kaynak = tmp_path / "profil.png"
        kaynak.write_bytes(b"sahte-png")

        yol = store_avatar_image("hesap-1", str(kaynak))

        assert Path(yol).exists()
        assert Path(yol).parent == account_config_dir("hesap-1")
        # Kaynak YERİNDE kalır.
        assert kaynak.exists()

    def test_desteklenmeyen_bicim_reddedilir(self, yerel_kok, tmp_path):
        kaynak = tmp_path / "profil.svg"
        kaynak.write_text("<svg/>", encoding="utf-8")

        with pytest.raises(ValueError, match="desteklenen biçimler"):
            store_avatar_image("hesap-1", str(kaynak))

    def test_cok_buyuk_dosya_reddedilir(self, yerel_kok, tmp_path):
        kaynak = tmp_path / "buyuk.png"
        kaynak.write_bytes(b"0" * (AVATAR_MAX_BYTES + 1))

        with pytest.raises(ValueError, match="MB"):
            store_avatar_image("hesap-1", str(kaynak))

    def test_olmayan_dosya_reddedilir(self, yerel_kok, tmp_path):
        with pytest.raises(ValueError, match="bulunamadı"):
            store_avatar_image("hesap-1", str(tmp_path / "yok.png"))

    def test_yeni_avatar_eskisini_birakmaz(self, yerel_kok, tmp_path):
        """Biçim değiştiren kullanıcının eski dosyası dizinde öksüz kalmamalı."""
        ilk = tmp_path / "ilk.png"
        ilk.write_bytes(b"png")
        eski_yol = Path(store_avatar_image("hesap-1", str(ilk)))

        ikinci = tmp_path / "ikinci.jpg"
        ikinci.write_bytes(b"jpg")
        yeni_yol = Path(store_avatar_image("hesap-1", str(ikinci)))

        assert yeni_yol.exists()
        assert not eski_yol.exists()

    def test_emoji_ile_dosya_ayrimi_yol_ayiracina_bakar(self):
        assert is_image_avatar("/hesap/avatar.png") is True
        assert is_image_avatar("C:\\hesap\\avatar.png") is True
        assert is_image_avatar("🏍️") is False
