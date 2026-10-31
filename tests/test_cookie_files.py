"""Çerez dışa aktarma dosyalarının ayrıştırılması (Netscape cookies.txt, JSON) — P-023.

Ölçüldü (31 Ekim): `tools/browser.py` her turda boş `new_context()` açıyordu; kullanıcının
dışa aktardığı çerez dosyasını okuyan hiçbir yol yoktu (yalnız `Cookie` başlığı metni
ayrıştırılıyordu, `providers/web_browser.py::parse_cookie_header`).
"""

from __future__ import annotations

import pytest

from fusion_cli.core.cookie_files import (
    Cookie,
    CookieFileError,
    cookie_domains,
    filter_by_domains,
    filter_origins_by_domains,
    origins_from_storage_state,
    parse_cookie_file,
    parse_json_cookies,
    parse_netscape_cookies,
    to_storage_state,
    validate_profile_name,
)

NETSCAPE = """# Netscape HTTP Cookie File
# https://curl.se/docs/http-cookies.html
.example.com\tTRUE\t/\tTRUE\t1893456000\tsid\tabc123
#HttpOnly_.example.com\tTRUE\t/\tTRUE\t1893456000\tgizli\txyz
shop.example.org\tFALSE\t/sepet\tFALSE\t0\toturum\tq=1=2

bozuk satır
"""


def test_netscape_dosyasi_ayristirilir_httponly_oneki_taninir():
    cerezler = parse_netscape_cookies(NETSCAPE)

    assert [cerez.name for cerez in cerezler] == ["sid", "gizli", "oturum"]
    assert cerezler[0] == Cookie(
        name="sid",
        value="abc123",
        domain=".example.com",
        path="/",
        expires=1893456000.0,
        secure=True,
        http_only=False,
    )
    assert cerezler[1].http_only is True
    assert cerezler[1].domain == ".example.com"
    # Değer içindeki '=' bozulmaz; süresi 0 olan oturum çerezidir (-1).
    assert cerezler[2].value == "q=1=2"
    assert cerezler[2].expires == -1


def test_json_listesi_cookie_editor_alanlariyla_ayristirilir():
    metin = """[
      {"name": "a", "value": "1", "domain": ".example.com", "path": "/",
       "expirationDate": 1893456000.5, "secure": true, "httpOnly": true, "sameSite": "lax"},
      {"name": "b", "value": "2", "domain": "example.org", "session": true,
       "sameSite": "no_restriction"}
    ]"""

    cerezler = parse_json_cookies(metin)

    assert cerezler[0].same_site == "Lax"
    assert cerezler[0].http_only is True
    assert cerezler[0].expires == 1893456000.5
    assert cerezler[1].expires == -1
    assert cerezler[1].same_site == "None"
    assert cerezler[1].path == "/"


def test_playwright_storage_state_json_da_okunur():
    metin = (
        '{"cookies": [{"name": "a", "value": "1", "domain": "x.io", "path": "/", '
        '"expires": -1}], "origins": []}'
    )

    cerezler = parse_json_cookies(metin)

    assert cerezler == (Cookie(name="a", value="1", domain="x.io", path="/", expires=-1),)


@pytest.mark.parametrize(
    "metin",
    ["", "   ", "{}", "[]", '{"cookies": "x"}', "[1, 2]", '[{"value": "v"}]'],
)
def test_bos_ya_da_cerezsiz_icerik_anlasilir_hata_verir(metin):
    with pytest.raises(CookieFileError):
        parse_cookie_file(metin, filename="cookies.json")


def test_bicim_dosya_adina_degil_icerige_gore_secilir():
    assert parse_cookie_file(NETSCAPE, filename="indirilen.json")[0].name == "sid"
    json_metin = '[{"name": "a", "value": "1", "domain": "x.io"}]'
    assert parse_cookie_file(json_metin, filename="cookies.txt")[0].name == "a"


def test_storage_state_playwright_bicimindedir_ve_degerler_korunur():
    cerezler = parse_netscape_cookies(NETSCAPE)

    durum = to_storage_state(cerezler)

    assert durum["origins"] == []
    ilk = durum["cookies"][0]
    assert ilk == {
        "name": "sid",
        "value": "abc123",
        "domain": ".example.com",
        "path": "/",
        "expires": 1893456000.0,
        "httpOnly": False,
        "secure": True,
        "sameSite": "Lax",
    }


def test_alan_adlari_normalize_ve_tekil():
    cerezler = parse_netscape_cookies(NETSCAPE)

    assert cookie_domains(cerezler) == ("example.com", "shop.example.org")


def test_alan_adi_suzgeci_alt_alan_adlarini_kapsar():
    cerezler = parse_netscape_cookies(NETSCAPE)

    kalan = filter_by_domains(cerezler, ("example.org",))

    assert [cerez.name for cerez in kalan] == ["oturum"]
    assert filter_by_domains(cerezler, ()) == ()
    assert filter_by_domains(cerezler, None) == cerezler


@pytest.mark.parametrize("ad", ["", "a/b", "../x", "çok uzun" * 20, ".gizli", "a b"])
def test_gecersiz_profil_adi_reddedilir(ad):
    with pytest.raises(CookieFileError):
        validate_profile_name(ad)


def test_gecerli_profil_adi_oldugu_gibi_doner():
    assert validate_profile_name(" is-hesabi_1 ") == "is-hesabi_1"


def test_storage_state_origins_tasir_ve_bozuk_kayitlari_atar():
    """Ölçüldü (31 Ekim): origins hep boş yazılıyordu; localStorage oturumları kayboluyordu."""
    origins = (
        {"origin": "https://app.example.com", "localStorage": [{"name": "jwt", "value": "J"}]},
    )
    durum = to_storage_state((), origins=origins)
    assert durum["origins"] == list(origins)

    okunan = origins_from_storage_state(
        {
            "cookies": [],
            "origins": [
                origins[0],
                {"origin": "", "localStorage": []},
                {
                    "origin": "https://x.com",
                    "localStorage": [{"name": "a"}, "bozuk", {"name": "b", "value": 1}],
                },
                "bozuk",
            ],
        }
    )
    assert okunan == (
        origins[0],
        {"origin": "https://x.com", "localStorage": [{"name": "b", "value": "1"}]},
    )
    assert origins_from_storage_state(None) == ()


def test_origins_alan_adi_suzgeci_koku_ve_alt_alan_adini_kapsar():
    origins = (
        {"origin": "https://app.example.com", "localStorage": []},
        {"origin": "https://example.com:8443", "localStorage": []},
        {"origin": "https://notexample.com", "localStorage": []},
        {"origin": "bozuk", "localStorage": []},
    )
    assert filter_origins_by_domains(origins, None) == origins
    assert filter_origins_by_domains(origins, ("example.com",)) == origins[:2]
    assert filter_origins_by_domains(origins, ()) == ()
