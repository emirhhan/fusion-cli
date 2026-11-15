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
        sonuc = store.create(username="kullanici", email="e@ornek.com", password="parola1234")

        assert sonuc.account.username == "kullanici"
        assert sonuc.recovery_code
        assert [hesap.username for hesap in store.list_accounts()] == ["kullanici"]

    def test_kisa_parola_ve_bozuk_eposta_reddedilir(self, store):
        with pytest.raises(AccountError, match=str(PASSWORD_MIN_CHARS)):
            store.create(username="a", email="a@b.com", password="kisa")
        with pytest.raises(AccountError, match="e-posta"):
            store.create(username="a", email="eposta-degil", password="parola1234")

    def test_ayni_kullanici_adi_ikinci_kez_acilamaz(self, store):
        store.create(username="kullanici", email="e@ornek.com", password="parola1234")

        with pytest.raises(AccountError, match="Kullanıcı adı"):
            store.create(username="KULLANICI", email="baska@ornek.com", password="parola1234")

    def test_giris_kullanici_adi_veya_eposta_ile_yapilir(self, store):
        store.create(username="kullanici", email="e@ornek.com", password="parola1234")

        assert store.authenticate(identifier="kullanici", password="parola1234") is not None
        assert store.authenticate(identifier="e@ornek.com", password="parola1234") is not None
        assert store.authenticate(identifier="kullanici", password="yanlis1234") is None
        assert store.authenticate(identifier="yok", password="parola1234") is None

    def test_kurtarma_kodu_parolayi_degistirir_ve_tek_kullanimliktir(self, store):
        sonuc = store.create(username="kullanici", email="e@ornek.com", password="parola1234")

        degisti = store.reset_password(
            identifier="kullanici", recovery_code=sonuc.recovery_code, new_password="yeniparola1"
        )

        assert degisti is True
        assert store.authenticate(identifier="kullanici", password="yeniparola1") is not None
        # Aynı kod ikinci kez çalışmaz: ele geçen bir kod sonsuza kadar geçerli olamaz.
        assert (
            store.reset_password(
                identifier="kullanici",
                recovery_code=sonuc.recovery_code,
                new_password="ucuncuparola",
            )
            is False
        )

    def test_yanlis_kurtarma_kodu_parolayi_degistirmez(self, store):
        store.create(username="kullanici", email="e@ornek.com", password="parola1234")

        assert (
            store.reset_password(
                identifier="kullanici",
                recovery_code="AAAA-BBBB-CCCC-DDDD",
                new_password="yeni12345",
            )
            is False
        )
        assert store.authenticate(identifier="kullanici", password="parola1234") is not None

    def test_profil_guncellenir(self, store):
        hesap = store.create(
            username="kullanici", email="e@ornek.com", password="parola1234"
        ).account

        yeni = store.update_profile(
            hesap.account_id, username="emir", email="yeni@ornek.com", avatar="🏍️"
        )

        assert (yeni.username, yeni.email, yeni.avatar) == ("emir", "yeni@ornek.com", "🏍️")

    def test_silinen_hesap_listede_kalmaz(self, store):
        hesap = store.create(
            username="kullanici", email="e@ornek.com", password="parola1234"
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


class TestHesapDuzeltmeleriD4:
    """30 Ekim triyajı: C1-07/08/09/10/11/37/38/48."""

    def test_kurtarma_kodu_80_bit_16_karakter(self):
        """Eskiden bayt başına bir harf: 10 karakter = 50 bit (C1-09)."""
        kod = generate_recovery_code()

        assert len(normalize_recovery_code(kod)) == 16
        assert kod.count("-") == 3

    def test_karisan_harfler_silinmez_esleme_yapilir(self):
        """O→0, I/L→1 eşlenir; U yok sayılır (C1-10)."""
        assert normalize_recovery_code("o-i-l-U 0") == "0110"
        kod = generate_recovery_code()
        # kullanıcı 0'ı O, 1'i I diye yazsa bile aynı kod doğrulanır
        karisik = kod.replace("0", "O").replace("1", "I")
        assert normalize_recovery_code(karisik) == normalize_recovery_code(kod)

    def test_olmayan_hesapta_yeni_karma_uretilmez(self, store, monkeypatch):
        """Süre sızıntısı: sahte karma bir kez üretilir, çağrı başına tek doğrulama (C1-07)."""
        from fusion_cli.accounts import store as depo

        depo._sahte_karma.cache_clear()
        cagrilar = {"hash": 0, "verify": 0}
        gercek_hash, gercek_verify = depo.hash_secret, depo.verify_secret
        monkeypatch.setattr(
            depo,
            "hash_secret",
            lambda s: (cagrilar.__setitem__("hash", cagrilar["hash"] + 1), gercek_hash(s))[1],
        )
        monkeypatch.setattr(
            depo,
            "verify_secret",
            lambda a, b: (
                cagrilar.__setitem__("verify", cagrilar["verify"] + 1),
                gercek_verify(a, b),
            )[1],
        )

        for _ in range(3):
            assert store.authenticate(identifier="yok", password="parola1234") is None
        assert (
            store.reset_password(identifier="yok", recovery_code="X", new_password="parola1234")
            is False
        )

        assert cagrilar["hash"] == 1  # yalnız ilk çağrıda, bir kez
        assert cagrilar["verify"] == 4  # her çağrıda tek doğrulama

    def test_kullanici_adinda_at_yasak(self, store):
        """`b@c.com` kullanıcı adı başka hesabın e-postasıyla çakışmasın (C1-08)."""
        with pytest.raises(AccountError, match="@"):
            store.create(username="b@c.com", email="x@ornek.com", password="parola1234")

    def test_eski_at_iceren_kullanici_adinda_girisi_e_posta_once_arar(self, store):
        """Eski kayıtta kullanıcı adı `@` içerse bile `@`lı girdi önce e-postaya bakılır."""
        a = store.create(username="ali", email="ali@ornek.com", password="parola1234").account
        import sqlite3

        with sqlite3.connect(store._path) as baglanti:  # eski veriyi taklit et
            baglanti.execute(
                "UPDATE accounts SET username = ? WHERE id = ?", ("veli@ornek.com", a.account_id)
            )
        b = store.create(username="veli", email="veli@ornek.com", password="digerparola12").account

        sonuc = store.authenticate(identifier="veli@ornek.com", password="digerparola12")
        assert sonuc is not None and sonuc.account_id == b.account_id

    def test_profil_guncellemede_de_dogrulama_yapilir(self, store):
        hesap = store.create(username="ali", email="ali@ornek.com", password="parola1234").account

        with pytest.raises(AccountError, match="boş"):
            store.update_profile(hesap.account_id, username="  ", email="a@b.com", avatar="")
        with pytest.raises(AccountError, match="e-posta"):
            store.update_profile(hesap.account_id, username="ali", email="eposta-degil", avatar="")

    def test_mevcut_avatar_yeniden_secilince_silinmez(self, yerel_kok, tmp_path):
        """kaynak == hedef: kopya döngüsü kaynağı yok etmemeli (C1-11)."""
        kaynak = tmp_path / "profil.png"
        kaynak.write_bytes(b"sahte-png")
        yol = store_avatar_image("hesap-1", str(kaynak))

        yine = store_avatar_image("hesap-1", yol)

        assert yine == yol and Path(yol).read_bytes() == b"sahte-png"

    def test_kopya_basarisizsa_eski_avatar_korunur(self, yerel_kok, tmp_path, monkeypatch):
        kaynak = tmp_path / "profil.png"
        kaynak.write_bytes(b"eski")
        yol = store_avatar_image("hesap-1", str(kaynak))
        yeni = tmp_path / "yeni.jpg"
        yeni.write_bytes(b"yeni")

        def bozuk(*_a, **_k):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr("fusion_cli.accounts.avatars.shutil.copy2", bozuk)
        with pytest.raises(ValueError, match="kopyalanamadı"):
            store_avatar_image("hesap-1", str(yeni))

        assert Path(yol).read_bytes() == b"eski"

    def test_gecersiz_hesap_kimligi_reddedilir(self, yerel_kok):
        """`../x`, boş kimlik dizin dışına çıkaramaz ya da tüm yapılandırmayı silemez (C1-37/38)."""
        for kotu in ("../x", "a/b", "", ".gizli"):
            with pytest.raises(ValueError):
                remember_account(kotu)
            with pytest.raises(ValueError):
                remove_account_files(kotu)
        with pytest.raises(ValueError):
            activate_account("../x")

    def test_bozuk_isaretci_hatirlanmaz(self, yerel_kok):
        from fusion_cli.config.paths import base_config_dir

        base_config_dir().mkdir(parents=True, exist_ok=True)
        (base_config_dir() / "active-account").write_text("../../etc", encoding="utf-8")

        assert remembered_account() == ""

    def test_isaretci_yalniz_sahibine_acik(self, yerel_kok):
        from fusion_cli.config.paths import base_config_dir

        remember_account("hesap-1")

        assert (base_config_dir() / "active-account").stat().st_mode & 0o777 == 0o600

    def test_silinemeyen_dosya_bildirilir(self, yerel_kok, monkeypatch):
        hedef = account_config_dir("hesap-1")
        hedef.mkdir(parents=True, exist_ok=True)
        (hedef / ".env").write_text("SIR=1", encoding="utf-8")
        monkeypatch.setattr("fusion_cli.accounts.session.shutil.rmtree", lambda *a, **k: None)

        kalanlar = remove_account_files("hesap-1")

        assert any(".env" in yol for yol in kalanlar)
