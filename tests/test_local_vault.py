"""Yerel kasa geçişi kullanıcı sırlarını korur ve izin diyaloğu açmaz."""

import pytest

pytest.importorskip("fcntl")

from fusion_cli.config import local_vault
from fusion_cli.config.credentials import FernetSecretStore


def test_yeni_kasa_anahtari_kalici_ve_ozeldir(tmp_path, monkeypatch):
    monkeypatch.setattr(local_vault, "_legacy_key", lambda: pytest.fail("Keychain çağrılmamalı"))
    key = local_vault.local_master_key(tmp_path)
    assert key == local_vault.local_master_key(tmp_path)
    assert (tmp_path / "vault/master.key").stat().st_mode & 0o777 == 0o600


def test_eski_kasa_ayni_anahtarla_tasinir_eski_dosya_korunur(tmp_path, monkeypatch):
    old = FernetSecretStore(tmp_path / "secrets.enc", secret_key="test-only")
    old.set("TEST_KEY", "test-value")
    original = (tmp_path / "secrets.enc").read_bytes()
    monkeypatch.setattr(local_vault, "_legacy_key", lambda: "test-only")
    key = local_vault.local_master_key(tmp_path)
    new = FernetSecretStore(tmp_path / "vault/secrets.enc", secret_key=key)
    assert new.get("TEST_KEY") == "test-value"
    assert (tmp_path / "secrets.enc").read_bytes() == original


def test_izin_yoksa_eski_kasa_uzerine_yazilmaz(tmp_path, monkeypatch):
    old = FernetSecretStore(tmp_path / "secrets.enc", secret_key="old-test-key")
    old.set("TEST_KEY", "test-value")
    original = (tmp_path / "secrets.enc").read_bytes()
    monkeypatch.setattr(local_vault, "_legacy_key", lambda: None)
    new = FernetSecretStore(
        tmp_path / "vault/secrets.enc", secret_key=local_vault.local_master_key(tmp_path)
    )
    new.set("NEW_TEST_KEY", "new-test-value")
    assert new.list_names() == ("NEW_TEST_KEY",)
    assert (tmp_path / "secrets.enc").read_bytes() == original
