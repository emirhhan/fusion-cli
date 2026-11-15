"""Kit tarayıcısına Fusion profili: `tarayici.profil_tarif` / `tarayici.profil_disa_aktar` (P-023).

Kapsam yalnız istenen ve profilin onayladığı alan adlarıdır; tarif yanıtı ve loglar çerez
değeri taşımaz; kapatma `runtime.disabled_tools` ve `browser.profiles_enabled` ile.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace

import pytest

from fusion_cli.appserver.kits_profile_routes import (
    KIT_PROFILE_TOOL,
    KITS_PROFILE_DESCRIBE_ROUTE,
    KITS_PROFILE_EXPORT_ROUTE,
    MAX_DOMAINS,
)
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.config.browser_profiles import BrowserProfileStore
from fusion_cli.core.cookie_files import Cookie

GIZLI = "kit-cerezi-GIZLI-47"


def _sonuc(satirlar, kimlik):
    for satir in reversed(satirlar):
        veri = json.loads(satir)
        if veri.get("tip") == "sonuc" and veri.get("id") == kimlik:
            return veri["veri"]
    raise AssertionError(f"kimlik için sonuç bulunamadı: {kimlik}")


@pytest.fixture
def oturum(tmp_path):
    satirlar: list[str] = []
    session = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    store = BrowserProfileStore(tmp_path / "bp", secret_key="anahtar", clock=lambda: 2.0)
    store.save(
        "is",
        (
            Cookie("sid", GIZLI, ".example.com"),
            Cookie("cart", "c", "shop.example.com"),
            Cookie("o", "1", "other.net"),
        ),
        source="dosya",
        allowed_domains=("example.com", "other.net"),
        origins=(
            {"origin": "https://example.com", "localStorage": [{"name": "t", "value": GIZLI}]},
        ),
    )
    session._browser_profiles = store
    return session, satirlar


async def _istek(session, satirlar, ad, veri, kimlik="1"):
    await session.handle(Request(id=kimlik, name=ad, data=veri))
    return _sonuc(satirlar, kimlik)


async def test_tarif_kapsami_ve_profil_alanlarini_degersiz_verir(oturum, caplog):
    session, satirlar = oturum
    caplog.set_level(logging.DEBUG)

    veri = await _istek(
        session, satirlar, KITS_PROFILE_DESCRIBE_ROUTE, {"ad": "is", "alanlar": ["example.com"]}
    )

    assert veri["status"] == "ok"
    assert veri["alan_adlari"] == ["example.com"]
    assert veri["profil_alanlari"] == ["example.com", "shop.example.com"]
    assert all(GIZLI not in satir for satir in satirlar)
    assert GIZLI not in caplog.text


async def test_disa_aktarma_yalniz_istenen_alan_adlarini_verir(oturum, caplog):
    session, satirlar = oturum
    caplog.set_level(logging.DEBUG)

    veri = await _istek(
        session, satirlar, KITS_PROFILE_EXPORT_ROUTE, {"ad": "is", "alanlar": ["example.com"]}
    )

    assert veri["status"] == "ok" and veri["cerez_sayisi"] == 2
    alanlar = {c["domain"] for c in veri["storage_state"]["cookies"]}
    assert alanlar == {".example.com", "shop.example.com"}
    assert [o["origin"] for o in veri["storage_state"]["origins"]] == ["https://example.com"]
    # Değer yalnız storage_state içinde; özet alanlarında ve loglarda yok.
    ozet = {k: v for k, v in veri.items() if k != "storage_state"}
    assert GIZLI not in json.dumps(ozet) and GIZLI not in caplog.text


async def test_profilin_onayi_disindaki_alan_adi_ve_ic_ag_reddedilir(oturum):
    session, satirlar = oturum

    disari = await _istek(
        session, satirlar, KITS_PROFILE_EXPORT_ROUTE, {"ad": "is", "alanlar": ["bank.com"]}, "1"
    )
    ic_ag = await _istek(
        session, satirlar, KITS_PROFILE_EXPORT_ROUTE, {"ad": "is", "alanlar": ["localhost"]}, "2"
    )
    bos = await _istek(session, satirlar, KITS_PROFILE_EXPORT_ROUTE, {"ad": "is"}, "3")
    fazla = await _istek(
        session,
        satirlar,
        KITS_PROFILE_EXPORT_ROUTE,
        {"ad": "is", "alanlar": [f"s{i}.example.com" for i in range(MAX_DOMAINS + 1)]},
        "4",
    )
    yok = await _istek(
        session, satirlar, KITS_PROFILE_EXPORT_ROUTE, {"ad": "yok", "alanlar": ["a.com"]}, "5"
    )

    assert disari["status"] == "denied" and "bank.com" in disari["text"]
    assert ic_ag["ok"] is False and "iç ağ" in ic_ag["text"]
    assert bos["ok"] is False and fazla["ok"] is False and yok["ok"] is False
    assert all("storage_state" not in json.loads(satir).get("veri", {}) for satir in satirlar)


async def test_kapatma_ayarlari_kullaniciya_sorulmadan_reddeder(oturum):
    session, satirlar = oturum
    config = session._state.config
    session._state.config = replace(
        config, runtime=replace(config.runtime, disabled_tools=(KIT_PROFILE_TOOL,))
    )
    kapali = await _istek(
        session, satirlar, KITS_PROFILE_DESCRIBE_ROUTE, {"ad": "is", "alanlar": ["example.com"]}
    )
    session._state.config = replace(config, browser=replace(config.browser, profiles_enabled=False))
    profilsiz = await _istek(
        session,
        satirlar,
        KITS_PROFILE_EXPORT_ROUTE,
        {"ad": "is", "alanlar": ["example.com"]},
        "2",
    )

    assert kapali["status"] == "denied" and KIT_PROFILE_TOOL in kapali["text"]
    assert profilsiz["status"] == "denied" and "profiles_enabled" in profilsiz["text"]
