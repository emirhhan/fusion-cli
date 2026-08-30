"""Web sağlayıcı bağlantısının sözleşmesi.

Bu sağlayıcılar (ChatGPT, Claude, Gemini, Copilot) API anahtarı KULLANMAZ:
giriş ayrı bir tarayıcı penceresinde yapılır ve çerez izole profilde kalır.
Panelin bu akışı hatasız sürmesi projenin ana taşıdır.
"""

from __future__ import annotations

import sys

import pytest

from fusion_cli.providers.web_control import login_argv, provider_cards


def test_paketlenmis_ikili_modul_bayragiyla_calistirilmaz(monkeypatch: pytest.MonkeyPatch):
    """PyInstaller ikilisinde `-m` YOKTUR; giriş penceresi böyle açılamaz.

    Kaynak kurulumda `python -m fusion_cli.providers.web_login` doğrudur, ama
    paketlenmiş uygulamada `sys.executable` Fusion ikilisidir ve `-m` bayrağını
    tanımaz. Ayrım yapılmazsa panelden "Giriş yap" sessizce hiçbir şey açmaz.
    """
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/Fusion.app/.../fusion")

    argv = login_argv("gemini_web", "main")

    assert "-m" not in argv
    assert argv[0].endswith("fusion")
    assert argv[1] == "web-login"
    assert argv[2:] == ["gemini_web", "main"]


def test_kaynak_kurulumda_modul_girisi_kullanilir(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", "/usr/bin/python3")

    argv = login_argv("chatgpt_web", "main")

    assert argv[:3] == ["/usr/bin/python3", "-m", "fusion_cli.providers.web_login"]
    assert argv[3:] == ["chatgpt_web", "main"]


def test_kartlar_dort_saglayiciyi_anahtar_istemeden_tanitir(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Panel kartları yalnız METADATA taşır; sır ya da çerez değeri taşımaz.

    Profil dizini geçici bir yere yönlendirilir: test makinedeki GERÇEK
    girişlere bağlı olmamalı, yoksa geliştiricinin kendi oturumu testi
    yeşil ya da kırmızı yapar.
    """
    from fusion_cli.providers import web_control

    monkeypatch.setattr(
        web_control, "browser_profile_dir", lambda provider, account: tmp_path / provider
    )
    cards = provider_cards(sessions=(), secret_store=None)

    assert [card["id"] for card in cards] == [
        "chatgpt_web",
        "claude_web",
        "gemini_web",
        "copilot_web",
    ]
    for card in cards:
        assert card["ad"]
        assert card["anahtar_gerekir"] is False
        assert card["bagli"] is False
        assert "cookie" not in str(card).casefold()
        assert "token" not in str(card).casefold()


def test_bilinmeyen_saglayici_cokertmez():
    with pytest.raises(ValueError):
        login_argv("olmayan_saglayici", "main")


async def test_protokol_web_saglayicilarini_anahtar_kutusu_olmadan_dondurur(tmp_path):
    """Masaüstü protokolü kartları verir; panel anahtar kutusu çizmez."""
    import json

    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    root = tmp_path / "proje"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "ev")

    await session.handle(Request(id="1", name="web.saglayicilar", data={}))
    await session.close()

    veri = json.loads(lines[-1])["veri"]
    assert veri["ok"] is True
    assert len(veri["saglayicilar"]) == 4
    assert all(card["anahtar_gerekir"] is False for card in veri["saglayicilar"])


async def test_bilinmeyen_saglayiciya_giris_istegi_sureci_cokertmez(tmp_path):
    import json

    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    root = tmp_path / "proje"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "ev")

    await session.handle(Request(id="2", name="web.giris", data={"saglayici": "yok"}))
    await session.close()

    veri = json.loads(lines[-1])["veri"]
    assert veri["ok"] is False and veri["metin"]


def test_tek_liste_hem_anahtarli_hem_web_saglayicilari_tasir(tmp_path, monkeypatch):
    """Panel TEK bir kısa liste çizer; tür farkı satırın içinde belirtilir.

    Kullanıcı uzun uzun anahtar kutuları istemiyor: "ismi yazsın, tıklayalım,
    dikdörtgen açılsın, API varsa girelim, web sağlayıcısıysa oturum açalım."
    Bu yüzden liste tek ve kısa; ayrıntı tıklayınca açılır.
    """
    from fusion_cli.providers import web_control
    from fusion_cli.providers.web_control import provider_catalog

    monkeypatch.setattr(
        web_control, "browser_profile_dir", lambda provider, account: tmp_path / provider
    )
    satirlar = provider_catalog(sessions=(), secret_store=None)

    kimlikler = {satir["id"] for satir in satirlar}
    assert {"chatgpt_web", "claude_web", "gemini_web", "copilot_web"} <= kimlikler
    assert "openrouter" in kimlikler

    for satir in satirlar:
        assert satir["ad"]
        assert satir["tur"] in ("web", "anahtar")
        assert isinstance(satir["bagli"], bool)
        # Kısa satır: uzun açıklama ve anahtar değeri TAŞIMAZ.
        assert "deger" not in satir
        assert "cookie" not in str(satir).casefold()

    web = next(s for s in satirlar if s["id"] == "gemini_web")
    assert web["tur"] == "web" and web["eylem"] == "oturum"
    anahtar = next(s for s in satirlar if s["id"] == "openrouter")
    assert anahtar["tur"] == "anahtar" and anahtar["eylem"] == "anahtar"
