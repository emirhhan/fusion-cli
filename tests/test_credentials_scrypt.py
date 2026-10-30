"""Sır deposu anahtar türetmesi scrypt'tir; eski SHA-256 dosyaları okunur ve göç edilir (L2-27).

Gerçek kullanıcı dizinine dokunulmaz: her şey tmp_path altında.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest

from fusion_cli.config.credentials import FernetSecretStore
from fusion_cli.core.errors import ConfigError

_KEY = "test-ana-anahtari"


def _eski_dosya_yaz(yol, anahtar, veri):
    """Eski sürümün yazdığı biçim: SHA-256 ile türetilmiş çıplak Fernet belirteci."""
    from cryptography.fernet import Fernet

    turetilmis = base64.urlsafe_b64encode(hashlib.sha256(anahtar.encode()).digest())
    yol.write_bytes(Fernet(turetilmis).encrypt(json.dumps(veri).encode()))


def test_yeni_dosya_surum_basligi_ve_tuz_tasir(tmp_path):
    store = FernetSecretStore(tmp_path / "s.enc", secret_key=_KEY)
    store.set("A", "1")
    ham = (tmp_path / "s.enc").read_bytes()
    assert ham.startswith(b"FSV2")
    assert store.get("A") == "1"


def test_ayni_anahtar_iki_dosyada_farkli_sifreleme_anahtari_uretir(tmp_path):
    """Tuz dosyaya özeldir: aynı parola iki depoda aynı türetilmiş anahtarı vermez."""
    for ad in ("a.enc", "b.enc"):
        FernetSecretStore(tmp_path / ad, secret_key=_KEY).set("A", "1")
    a = (tmp_path / "a.enc").read_bytes()
    b = (tmp_path / "b.enc").read_bytes()
    assert a[4:20] != b[4:20]


def test_eski_sha256_dosyasi_okunur(tmp_path):
    _eski_dosya_yaz(tmp_path / "s.enc", _KEY, {"A": "1"})
    store = FernetSecretStore(tmp_path / "s.enc", secret_key=_KEY)
    assert store.get("A") == "1"


def test_eski_dosya_yazimda_yeni_bicime_yukselir(tmp_path):
    _eski_dosya_yaz(tmp_path / "s.enc", _KEY, {"A": "1"})
    store = FernetSecretStore(tmp_path / "s.enc", secret_key=_KEY)
    store.set("B", "2")
    assert (tmp_path / "s.enc").read_bytes().startswith(b"FSV2")
    assert store.list_names() == ("A", "B")


def test_gocu_yedeklidir_idempotenttir_ve_degerleri_korur(tmp_path):
    _eski_dosya_yaz(tmp_path / "s.enc", _KEY, {"A": "1"})
    eski_bayt = (tmp_path / "s.enc").read_bytes()
    store = FernetSecretStore(tmp_path / "s.enc", secret_key=_KEY)

    assert store.upgrade_format() is True
    assert (tmp_path / "s.enc").read_bytes().startswith(b"FSV2")
    assert (tmp_path / "s.enc.v1").read_bytes() == eski_bayt
    assert store.get("A") == "1"

    yeni_bayt = (tmp_path / "s.enc").read_bytes()
    assert store.upgrade_format() is False  # ikinci çağrı hiçbir şey yapmaz
    assert (tmp_path / "s.enc").read_bytes() == yeni_bayt
    assert (tmp_path / "s.enc.v1").read_bytes() == eski_bayt


def test_gocte_yanlis_anahtar_dosyayi_degistirmez(tmp_path):
    _eski_dosya_yaz(tmp_path / "s.enc", "dogru", {"A": "1"})
    onceki = (tmp_path / "s.enc").read_bytes()
    store = FernetSecretStore(tmp_path / "s.enc", secret_key="yanlis")
    assert store.upgrade_format() is False
    assert (tmp_path / "s.enc").read_bytes() == onceki
    assert not (tmp_path / "s.enc.v1").exists()


def test_gocte_dosya_yoksa_veya_anahtarsizsa_hicbir_sey_olmaz(tmp_path):
    assert FernetSecretStore(tmp_path / "yok.enc", secret_key=_KEY).upgrade_format() is False
    assert FernetSecretStore(tmp_path / "yok.enc", secret_key=None).upgrade_format() is False


def test_yanlis_anahtar_yeni_bicimde_de_cozemez(tmp_path):
    FernetSecretStore(tmp_path / "s.enc", secret_key="dogru").set("K", "v")
    with pytest.raises(ConfigError, match="çözülemedi"):
        FernetSecretStore(tmp_path / "s.enc", secret_key="yanlis").get("K")


def test_scrypt_yoksa_eski_bicimle_yazilir(tmp_path, monkeypatch):
    """Derlemede `hashlib.scrypt` olmayabilir: depo çökmez, eski biçime düşer."""
    monkeypatch.delattr("fusion_cli.config.credentials.hashlib.scrypt", raising=False)
    store = FernetSecretStore(tmp_path / "s.enc", secret_key=_KEY)
    store.set("A", "1")
    assert not (tmp_path / "s.enc").read_bytes().startswith(b"FSV2")
    assert store.get("A") == "1"


def test_yukleyici_eski_dosyayi_acilista_tasir(tmp_path, monkeypatch):
    from fusion_cli.config import keys, loader, paths

    yol = tmp_path / "secrets.enc"
    _eski_dosya_yaz(yol, _KEY, {"FUSION_TEST_SIR": "gizli"})
    monkeypatch.setattr(paths, "credentials_file", lambda: yol)
    monkeypatch.setattr(loader, "credentials_file", lambda: yol)
    monkeypatch.setattr(keys, "secret_key", lambda: _KEY)
    monkeypatch.delenv("FUSION_TEST_SIR", raising=False)

    loader._apply_stored_secrets()

    import os

    assert os.environ.pop("FUSION_TEST_SIR") == "gizli"
    assert yol.read_bytes().startswith(b"FSV2")
    assert (tmp_path / "secrets.enc.v1").exists()
