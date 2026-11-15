"""Hesap başına veri kökü (bayraklı) ve eski ortak verinin tek sahibe taşınması (WP02).

Ölçüldü (28 Ekim): iki hesap kimliğiyle `user_data_dir` aynı kökü döndürüyordu;
bellek, sır deposu (`secrets.enc` + yerel ana anahtar), tarayıcı profilleri ve
gönderim kayıtları bütün hesaplarda ortaktı. Plan §5: yeni bağlam özellik
bayrağıyla açılır; sahipliği belirsiz eski veri otomatik olarak bütün hesaplara
kopyalanmaz, kullanıcı tek bir sahip seçer; taşıma kesilirse eski veri okunur
kalır ve tekrar çalıştırma çoğaltmaz.
"""

from __future__ import annotations

import pytest

from fusion_cli.accounts import data_migration
from fusion_cli.accounts.data_migration import (
    MigrationError,
    migrate_legacy_data,
    migration_inventory,
)
from fusion_cli.accounts.workspaces import PERSONAL_WORKSPACE, bind_context, local_identity
from fusion_cli.config import paths


@pytest.fixture
def veri(tmp_path, monkeypatch):
    kok = tmp_path / "veri"
    monkeypatch.setenv("XDG_DATA_HOME", str(kok))
    monkeypatch.setenv("LOCALAPPDATA", str(kok))
    monkeypatch.delenv("FUSION_MEMORY_DIR", raising=False)
    monkeypatch.delenv(paths.ENV_ACCOUNT, raising=False)
    monkeypatch.delenv(paths.ENV_WORKSPACE_ISOLATION, raising=False)
    eski = paths.base_data_dir()
    (eski / "memory").mkdir(parents=True)
    (eski / "memory" / "dersler.json").write_text('{"ders": 1}', encoding="utf-8")
    (eski / "secrets.enc").write_bytes(b"sifreli")
    (eski / "web_profiles" / "chatgpt" / "main").mkdir(parents=True)
    (eski / "web_profiles" / "chatgpt" / "main" / "Cookies").write_bytes(b"oturum")
    return eski


def _hedef(hesap):
    """Hesabın kişisel çalışma alanının veri kökü (taşımanın hedefi)."""
    return paths.tenant_data_dir(hesap) / PERSONAL_WORKSPACE


def _hesap(monkeypatch, hesap):
    monkeypatch.setenv(paths.ENV_ACCOUNT, hesap)


def test_bayrak_kapaliyken_eski_ortak_duzen_korunur(veri, monkeypatch):
    _hesap(monkeypatch, "hesap-a")
    a = paths.user_data_dir()
    _hesap(monkeypatch, "hesap-b")

    assert a == paths.user_data_dir() == veri


def test_bayrak_acikken_her_hesabin_ayri_koku_ve_siri_var(veri, monkeypatch):
    monkeypatch.setenv(paths.ENV_WORKSPACE_ISOLATION, "1")
    _hesap(monkeypatch, "hesap-a")
    a = (paths.user_data_dir(), paths.memory_dir(), paths.credentials_file())
    _hesap(monkeypatch, "hesap-b")
    b = (paths.user_data_dir(), paths.memory_dir(), paths.credentials_file())

    assert all(x != y for x, y in zip(a, b, strict=True))
    assert a[0] == paths.workspace_data_dir(
        bind_context(local_identity("hesap-a"), PERSONAL_WORKSPACE)
    )
    assert not a[0].is_relative_to(b[0]) and not b[0].is_relative_to(a[0])


def test_hesapsiz_kurulum_bayrakla_da_eski_koku_kullanir(veri, monkeypatch):
    monkeypatch.setenv(paths.ENV_WORKSPACE_ISOLATION, "1")

    assert paths.user_data_dir() == veri


def test_eski_veri_yalniz_secilen_sahibe_kopyalanir(veri, monkeypatch):
    sonuc = migrate_legacy_data("hesap-a")

    hedef_a = _hedef("hesap-a")
    assert (hedef_a / "memory" / "dersler.json").read_text(encoding="utf-8") == '{"ders": 1}'
    assert (hedef_a / "secrets.enc").read_bytes() == b"sifreli"
    assert not _hedef("hesap-b").exists()
    # Kopyalanır, taşınmaz: eski kurulum çalışır kalır.
    assert (veri / "memory" / "dersler.json").exists()
    assert set(sonuc.copied) >= {"memory", "secrets.enc", "web_profiles"}


def test_tekrar_calistirma_cogaltmaz_ve_ikinci_sahip_reddedilir(veri):
    migrate_legacy_data("hesap-a")
    (_hedef("hesap-a") / "memory" / "yeni.json").write_text("{}", encoding="utf-8")

    ikinci = migrate_legacy_data("hesap-a")

    assert ikinci.copied == () and ikinci.already_done
    assert (_hedef("hesap-a") / "memory" / "yeni.json").exists()
    with pytest.raises(MigrationError):
        migrate_legacy_data("hesap-b")


def test_kesilen_tasima_eski_veriyi_bozmaz_ve_kaldigi_yerden_tamamlanir(veri, monkeypatch):
    gercek = data_migration._copy_entry
    sayac = {"n": 0}

    def yarida_kes(source, target):
        sayac["n"] += 1
        if sayac["n"] == 2:
            raise OSError("disk doldu")
        gercek(source, target)

    monkeypatch.setattr(data_migration, "_copy_entry", yarida_kes)
    with pytest.raises(OSError):
        migrate_legacy_data("hesap-a")
    assert (veri / "memory" / "dersler.json").exists()
    assert not list(_hedef("hesap-a").glob("*.tasiniyor-*"))

    monkeypatch.setattr(data_migration, "_copy_entry", gercek)
    sonuc = migrate_legacy_data("hesap-a")

    assert sonuc.already_done is False
    assert (_hedef("hesap-a") / "memory" / "dersler.json").exists()
    assert (_hedef("hesap-a") / "secrets.enc").exists()


def test_acik_tarayici_profili_varken_tasima_yapilmaz(veri):
    (veri / "web_profiles" / "chatgpt" / "main" / "SingletonLock").write_text("x")

    with pytest.raises(MigrationError, match="tarayıcı"):
        migrate_legacy_data("hesap-a")
    assert not _hedef("hesap-a").exists()


def test_envanter_sahipligi_belirsiz_veriyi_listeler(veri):
    envanter = migration_inventory()

    assert envanter.owner == ""
    assert {item.name for item in envanter.entries} >= {"memory", "secrets.enc", "web_profiles"}
    assert all(item.size_bytes >= 0 for item in envanter.entries)


def test_adopt_data_komutu_secilen_hesaba_baglar(veri, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from fusion_cli.accounts import SqliteAccountStore
    from fusion_cli.cli.app import app

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "ayar"))
    hesap = SqliteAccountStore().create(username="ayse", email="a@x.test", password="parola-123456")

    envanter = CliRunner().invoke(app, ["adopt-data"])
    sonuc = CliRunner().invoke(app, ["adopt-data", "ayse"])

    assert envanter.exit_code == 0 and "memory" in envanter.output
    assert sonuc.exit_code == 0, sonuc.output
    assert (_hedef(hesap.account.account_id) / "memory" / "dersler.json").exists()


def test_hedefte_veri_varsa_sessizce_atlamaz_reddeder(veri):
    (_hedef("hesap-a") / "memory").mkdir(parents=True)
    (_hedef("hesap-a") / "memory" / "hesabin-kendi.json").write_text("{}", encoding="utf-8")

    with pytest.raises(MigrationError, match="memory"):
        migrate_legacy_data("hesap-a")

    assert migration_inventory().owner == ""
    assert (_hedef("hesap-a") / "memory" / "hesabin-kendi.json").exists()


def test_chromeun_kirik_sembolik_bag_kilidi_algilanir(veri):
    profil = veri / "web_profiles" / "chatgpt" / "main"
    (profil / "SingletonLock").symlink_to("makine-12345")

    with pytest.raises(MigrationError, match="tarayıcı"):
        migrate_legacy_data("hesap-a")


def test_acik_sqlite_gunlugu_varken_tasima_yapilmaz(veri):
    (veri / "submission.sqlite3").write_bytes(b"db")
    (veri / "submission.sqlite3-wal").write_bytes(b"bekleyen yazim")

    with pytest.raises(MigrationError, match="Fusion"):
        migrate_legacy_data("hesap-a")
