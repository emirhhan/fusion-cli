"""Chrome 'Cookies' SQLite'ından çerez okuma ve çözme (P-023).

Gerçek Chrome dizinine ve macOS Keychain'e DOKUNULMAZ: sahte bir `Cookies` veritabanı
Chrome'un kendi şemasıyla `tmp_path` altında kurulur, değerler Chrome'un kullandığı
türetme (PBKDF2-SHA1 "saltysalt" + AES-128-CBC) ile şifrelenir ve parola sağlayıcı
sahte verilir.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from fusion_cli.core.errors import BrowserProfileError
from fusion_cli.providers import chrome_cookies

PAROLA = "sahte-keychain-parolasi"
#: Chrome zaman damgası: 1601'den mikrosaniye. 2030-01-01 00:00:00 UTC.
CHROME_2030 = (1893456000 + 11644473600) * 1_000_000


def _sifrele(plain: bytes, *, iterations: int) -> bytes:
    key = chrome_cookies.derive_key(PAROLA, iterations=iterations)
    return chrome_cookies.encrypt_for_test(plain, key)


def _veritabani(path: Path, rows: list[tuple[str, str, bytes, str, int, int, int, int]]) -> None:
    baglanti = sqlite3.connect(path)
    baglanti.execute(
        "CREATE TABLE cookies (creation_utc INTEGER, host_key TEXT, name TEXT, value TEXT, "
        "encrypted_value BLOB, path TEXT, expires_utc INTEGER, is_secure INTEGER, "
        "is_httponly INTEGER, samesite INTEGER, last_access_utc INTEGER)"
    )
    for host, name, enc, path_, expires, secure, httponly, samesite in rows:
        baglanti.execute(
            "INSERT INTO cookies (creation_utc, host_key, name, value, encrypted_value, path, "
            "expires_utc, is_secure, is_httponly, samesite, last_access_utc) "
            "VALUES (0,?,?,'',?,?,?,?,?,?,0)",
            (host, name, enc, path_, expires, secure, httponly, samesite),
        )
    baglanti.commit()
    baglanti.close()


@pytest.fixture
def chrome_dizini(tmp_path, monkeypatch):
    """`Local State` + iki profil; biri eski `Cookies`, biri yeni `Network/Cookies` yerinde."""
    kok = tmp_path / "Chrome"
    (kok / "Default" / "Network").mkdir(parents=True)
    (kok / "Profile 1").mkdir()
    (kok / "Local State").write_text(
        json.dumps(
            {
                "profile": {
                    "info_cache": {
                        "Default": {"name": "Kişisel"},
                        "Profile 1": {"name": "İş"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    iterations = chrome_cookies.KEY_ITERATIONS
    sid = _sifrele(b"GIZLI-sid-degeri", iterations=iterations)
    # Chrome ≥ 130: düz metnin başına SHA-256(host_key) eklenir; çözücü bunu atmalı.
    onekli = _sifrele(
        hashlib.sha256(b"shop.example.org").digest() + b"yeni-bicim", iterations=iterations
    )
    _veritabani(
        kok / "Default" / "Network" / "Cookies",
        [
            (".example.com", "sid", sid, "/", CHROME_2030, 1, 1, 1),
            ("shop.example.org", "pref", onekli, "/sepet", 0, 0, 0, 2),
            (
                "login.other.net",
                "tok",
                _sifrele(b"baska", iterations=iterations),
                "/",
                CHROME_2030,
                1,
                0,
                0,
            ),
        ],
    )
    _veritabani(
        kok / "Profile 1" / "Cookies",
        [(".is.example", "a", _sifrele(b"1", iterations=iterations), "/", 0, 0, 0, -1)],
    )
    monkeypatch.setattr(chrome_cookies, "safe_storage_password", lambda: PAROLA)
    return kok


def test_profiller_local_state_adlariyla_listelenir(chrome_dizini):
    profiller = chrome_cookies.list_chrome_profiles(chrome_dizini)

    assert [(p.directory.name, p.label) for p in profiller] == [
        ("Default", "Kişisel"),
        ("Profile 1", "İş"),
    ]
    assert profiller[0].cookies_path.name == "Cookies"
    assert profiller[0].cookies_path.parent.name == "Network"


def test_alan_adlari_cozmeden_okunur(chrome_dizini, monkeypatch):
    """Onay ekranı için alan adı listesi: Keychain'e hiç gidilmez."""
    monkeypatch.setattr(
        chrome_cookies, "safe_storage_password", lambda: pytest.fail("Keychain çağrıldı")
    )
    profil = chrome_cookies.list_chrome_profiles(chrome_dizini)[0]

    assert chrome_cookies.chrome_cookie_domains(profil) == (
        "example.com",
        "login.other.net",
        "shop.example.org",
    )


def test_cerezler_cozulur_ve_alanlar_donusturulur(chrome_dizini):
    profil = chrome_cookies.list_chrome_profiles(chrome_dizini)[0]

    cerezler = chrome_cookies.read_chrome_cookies(profil)

    sid, pref, tok = cerezler
    assert sid.value == "GIZLI-sid-degeri"
    assert sid.domain == ".example.com"
    assert sid.expires == 1893456000.0
    assert sid.secure is True and sid.http_only is True and sid.same_site == "Lax"
    assert pref.value == "yeni-bicim"
    assert pref.expires == -1 and pref.path == "/sepet" and pref.same_site == "Strict"
    assert tok.same_site == "None"


def test_alan_adi_suzgeci_yalniz_secilenleri_okur(chrome_dizini):
    profil = chrome_cookies.list_chrome_profiles(chrome_dizini)[0]

    cerezler = chrome_cookies.read_chrome_cookies(profil, domains=("example.com",))

    assert [cerez.name for cerez in cerezler] == ["sid"]


def test_yanlis_parola_anlasilir_hata_verir(chrome_dizini, monkeypatch):
    monkeypatch.setattr(chrome_cookies, "safe_storage_password", lambda: "yanlis")
    profil = chrome_cookies.list_chrome_profiles(chrome_dizini)[0]

    with pytest.raises(BrowserProfileError, match="çözülemedi"):
        chrome_cookies.read_chrome_cookies(profil)


def test_olmayan_chrome_dizini_bos_liste_doner(tmp_path):
    assert chrome_cookies.list_chrome_profiles(tmp_path / "yok") == ()


def test_okuma_veritabanini_kopyalar_asil_dosyaya_dokunmaz(chrome_dizini):
    """Chrome açıkken DB kilitlidir; kopya üzerinden okunur ve kopya silinir."""
    profil = chrome_cookies.list_chrome_profiles(chrome_dizini)[1]
    once = profil.cookies_path.stat().st_mtime_ns

    chrome_cookies.read_chrome_cookies(profil)

    assert profil.cookies_path.stat().st_mtime_ns == once
    assert not list(profil.cookies_path.parent.glob("*.tmp"))
