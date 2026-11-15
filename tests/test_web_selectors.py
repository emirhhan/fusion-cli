"""Web arayüz seçicileri koddan ayrı, gömülü JSON'dadır (P1-43).

Ölçüldü (30 Ekim): seçiciler `web_browser.py` içine kodlanmıştı; ön yüz dağıtımı her
kırdığında (22 Eylül, 18 Ekim) düzeltme kod değişikliği istiyor, kullanıcıya "zaman aşımı"
olarak yansıyordu. Uzaktan güncelleme YOKTUR: yalnız pakete gömülü dosya okunur.
"""

from __future__ import annotations

import copy
import json
from importlib import resources

import pytest

from fusion_cli.providers import web_browser, web_image
from fusion_cli.providers.web_selectors import (
    WebSelectorsError,
    parse_web_selectors,
    web_selectors,
)


def _raw() -> dict:
    resource = resources.files("fusion_cli.providers").joinpath("data", "web-selectors.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def test_gomulu_dosya_gecerli_ve_dort_saglayiciyi_kapsar():
    secici = web_selectors()

    assert set(secici.providers) == {"chatgpt_web", "claude_web", "gemini_web", "copilot_web"}
    for tanim in secici.providers.values():
        assert tanim.input and tanim.send and tanim.response and tanim.stop and tanim.history


def test_sağlayici_tanimlari_seciciyi_dosyadan_alir():
    for kimlik, tanim in web_browser.WEB_BROWSER_PROVIDERS.items():
        secici = web_selectors().providers[kimlik]
        assert tanim.input_selectors == secici.input
        assert tanim.response_selectors == secici.response
        assert tanim.stop_selectors == secici.stop
        assert tanim.history_selectors == secici.history


def test_ozel_secici_tablolari_dosyadan_turetilir():
    assert web_browser.MODEL_MENU_BUTTONS["gemini_web"] == (
        'button[data-test-id="bard-mode-menu-button"]',
    )
    assert set(web_browser.MODEL_MENU_BUTTONS) == {"gemini_web", "chatgpt_web", "claude_web"}
    assert set(web_image.IMAGE_SELECTORS) == {"gemini_web", "chatgpt_web"}
    assert web_browser._GEMINI_UPLOAD_MENU_TRIGGER == "button[jslog^='300142']"
    assert 'iframe[src*="challenges.cloudflare.com"]' in web_browser._CHALLENGE_DOM


def test_dosya_kod_icinde_secici_kopyasi_birakmaz():
    paket = resources.files("fusion_cli.providers")
    kaynaklar = [
        (paket / ad).read_text(encoding="utf-8") for ad in ("web_browser.py", "web_image.py")
    ]
    secililer = {
        secici
        for tanim in web_selectors().providers.values()
        for secici in (
            *tanim.input,
            *tanim.response,
            *tanim.history,
            *tanim.image,
            *tanim.model_menu,
        )
        if len(secici) > 15
    }

    assert secililer
    for secici in secililer:
        for kaynak in kaynaklar:
            assert f'"{secici}"' not in kaynak and f"'{secici}'" not in kaynak, secici


def test_bilinmeyen_anahtar_sessizce_yutulmaz():
    ham = _raw()
    ham["providers"]["chatgpt_web"]["girdi"] = ["textarea"]  # yazım hatası

    with pytest.raises(WebSelectorsError, match="bilinmeyen"):
        parse_web_selectors(ham)


def test_zorunlu_liste_bos_olamaz():
    ham = _raw()
    ham["providers"]["claude_web"]["input"] = []

    with pytest.raises(WebSelectorsError, match="boş olamaz"):
        parse_web_selectors(ham)


def test_secici_metin_olmali():
    ham = copy.deepcopy(_raw())
    ham["providers"]["gemini_web"]["send"] = ["button", 3]

    with pytest.raises(WebSelectorsError, match="metin"):
        parse_web_selectors(ham)


def test_desteklenmeyen_surum_reddedilir():
    ham = _raw()
    ham["version"] = 99

    with pytest.raises(WebSelectorsError, match="sürümü"):
        parse_web_selectors(ham)


def test_ihtiyari_alanlar_eksik_olabilir():
    ham = _raw()
    del ham["providers"]["copilot_web"]["tier"]
    del ham["providers"]["copilot_web"]["image"]

    assert parse_web_selectors(ham).providers["copilot_web"].tier == ()


def test_aciklama_anahtarlari_yok_sayilir():
    ham = _raw()
    ham["providers"]["chatgpt_web"]["_notes"] = ["serbest metin"]

    assert parse_web_selectors(ham).providers["chatgpt_web"].input


def test_paket_verisi_olarak_dagitilir():
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())
    veri = pyproject["tool"]["setuptools"]["package-data"]["fusion_cli.providers"]

    assert "data/*.json" in veri
