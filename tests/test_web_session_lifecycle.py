"""Web sağlayıcı oturumunun tam yaşam döngüsü.

Masaüstü uygulaması giriş penceresini açıyor ama pencere kapandıktan sonra
YALNIZCA profil klasörünün varlığına bakıyordu. Kullanıcı panelde "bağlı"
görüyor, Fusion ise o sağlayıcıyı model yönlendirmesinde hiç kullanamıyordu:
oturum yapılandırmaya yazılmıyordu. Bu dosya eksik halkaları korur.
"""

from __future__ import annotations

import pytest

from fusion_cli.providers import web_control
from tests.fakes import make_config


@pytest.fixture(autouse=True)
def _izole_profil(tmp_path, monkeypatch):
    monkeypatch.setattr(
        web_control, "browser_profile_dir", lambda provider, account: tmp_path / provider / account
    )


@pytest.fixture
def config(tmp_path):
    return make_config(source=tmp_path / "config.yaml")


def test_giristen_sonra_oturum_yapilandirmaya_yazilir(config):
    yeni, sonuc = web_control.register_session(config, "chatgpt_web", "main")

    assert sonuc["ok"] is True
    assert yeni is not None
    oturum = yeni.web_sessions[0]
    assert oturum.provider == "chatgpt_web"
    assert oturum.transport == "browser"
    assert oturum.enabled is True
    assert oturum.model == "chatgpt_web/main/auto"


def test_ayni_saglayici_icin_ikinci_kayit_cogaltmaz(config):
    once, _ = web_control.register_session(config, "chatgpt_web", "main")
    assert once is not None

    sonra, _ = web_control.register_session(once, "chatgpt_web", "main")

    assert sonra is not None
    assert len(sonra.web_sessions) == 1


def test_yeniden_kayit_gecilmis_arac_olcumunu_korur(config):
    """Ölçüm modelin yeteneğine dairdir; yeniden bağlanmak onu silmemeli."""
    from dataclasses import replace

    once, _ = web_control.register_session(config, "chatgpt_web", "main")
    assert once is not None
    olculmus = replace(
        once,
        web_sessions=(replace(once.web_sessions[0], tool_eval_passed=True),),
    )

    sonra, _ = web_control.register_session(olculmus, "chatgpt_web", "main")

    assert sonra is not None
    assert sonra.web_sessions[0].tool_eval_passed is True


def test_taninmayan_saglayici_kaydedilmez(config):
    yeni, sonuc = web_control.register_session(config, "olmayan_web", "main")

    assert yeni is None
    assert sonuc["ok"] is False


def test_cikis_oturumu_ve_profili_kaldirir(config, tmp_path):
    kayitli, _ = web_control.register_session(config, "chatgpt_web", "main")
    assert kayitli is not None
    profil = tmp_path / "chatgpt_web" / "main"
    profil.mkdir(parents=True)
    (profil / "Cookies").write_text("x", encoding="utf-8")

    yeni, sonuc = web_control.remove_session(kayitli, "chatgpt_web", "main")

    assert sonuc["ok"] is True
    assert yeni is not None
    assert yeni.web_sessions == ()
    assert not profil.exists()


def test_olmayan_oturum_icin_cikis_hata_verir(config):
    yeni, sonuc = web_control.remove_session(config, "chatgpt_web", "main")

    assert yeni is None
    assert sonuc["ok"] is False


def test_bagli_sayilmak_icin_kayitli_oturum_da_gerekir(tmp_path, config):
    """Boş ya da yarım oluşmuş profil tek başına "bağlı" demek değildir."""
    (tmp_path / "chatgpt_web" / "main").mkdir(parents=True)

    kartlar = web_control.provider_cards(sessions=(), secret_store=None)
    chatgpt = next(kart for kart in kartlar if kart["id"] == "chatgpt_web")

    assert chatgpt["profil_var"] is True
    assert chatgpt["bagli"] is False


def test_kayitli_ve_profilli_saglayici_baglidir(tmp_path, config):
    kayitli, _ = web_control.register_session(config, "chatgpt_web", "main")
    assert kayitli is not None
    (tmp_path / "chatgpt_web" / "main").mkdir(parents=True)

    kartlar = web_control.provider_cards(sessions=kayitli.web_sessions, secret_store=None)
    chatgpt = next(kart for kart in kartlar if kart["id"] == "chatgpt_web")

    assert chatgpt["bagli"] is True
    assert chatgpt["model"] == "chatgpt_web/main/auto"


@pytest.mark.asyncio
async def test_dogrulama_gercek_bir_istek_gonderir(config, monkeypatch):
    """ "Bağlı" demek için gerçekten cevap alınmalı; klasör varlığı yetmez."""
    kayitli, _ = web_control.register_session(config, "chatgpt_web", "main")
    assert kayitli is not None

    class SahteSonuc:
        ok = True
        text = "OK"
        latency_ms = 120
        error = None

    class SahteSaglayici:
        async def complete(self, request):
            return SahteSonuc()

    monkeypatch.setattr(web_control, "_build_web_provider", lambda config, model: SahteSaglayici())

    sonuc = await web_control.validate_session(kayitli, "chatgpt_web", "main")

    assert sonuc["ok"] is True
    assert sonuc["onizleme"] == "OK"


@pytest.mark.asyncio
async def test_dogrulama_basarisizsa_sebebi_soyler(config, monkeypatch):
    kayitli, _ = web_control.register_session(config, "chatgpt_web", "main")
    assert kayitli is not None

    class SahteSonuc:
        ok = False
        text = ""
        latency_ms = 90
        error = "giriş yapılmamış"

    class SahteSaglayici:
        async def complete(self, request):
            return SahteSonuc()

    monkeypatch.setattr(web_control, "_build_web_provider", lambda config, model: SahteSaglayici())

    sonuc = await web_control.validate_session(kayitli, "chatgpt_web", "main")

    assert sonuc["ok"] is False
    assert "giriş yapılmamış" in sonuc["metin"]


@pytest.mark.asyncio
async def test_kayitsiz_saglayici_dogrulanamaz(config):
    sonuc = await web_control.validate_session(config, "chatgpt_web", "main")

    assert sonuc["ok"] is False
