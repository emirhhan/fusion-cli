"""Düğümlü görsel akışının çekirdek tarafı: NIM yolu, işlem istemleri, referans kuralları."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.appserver import image_create
from fusion_cli.config.models import WebSessionConfig
from fusion_cli.providers import web_image
from fusion_cli.providers.web_browser import WebBrowserError
from fusion_cli.providers.web_image import GeneratedImage

_NIM = "nvidia_nim/black-forest-labs/flux.1-dev"
_ENV = {"NVIDIA_NIM_API_KEY": "test-anahtari"}


def _config(*models: str):
    from fusion_cli.config.loader import load_config

    oturumlar = tuple(
        WebSessionConfig(model=m, transport="browser", provider=m.split("/")[0]) for m in models
    )
    return replace(load_config(), web_sessions=oturumlar)


@pytest.fixture
def galeri(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(image_create, "image_output_dir", lambda: tmp_path)
    return tmp_path


def test_nim_anahtari_varsa_olculmus_modeller_listelenir() -> None:
    secenekler = image_create.image_providers(_config(), environ=_ENV)

    assert [s["deger"] for s in secenekler] == [
        _NIM,
        "nvidia_nim/black-forest-labs/flux.2-klein-4b",
    ]
    assert all(s["referans"] is False for s in secenekler)
    assert image_create.image_providers(_config(), environ={}) == []


async def test_nim_ile_uretim_galeriye_yazar_ve_istemi_saklar(galeri, monkeypatch) -> None:
    alinan: dict[str, object] = {}

    async def uret(model, istem, klasor, *, api_key):
        alinan.update(model=model.model, istem=istem, anahtar=api_key)
        yol = klasor / "a.jpg"
        yol.write_bytes(b"\xff\xd8")
        return [GeneratedImage(yol, 1024, 1024)]

    monkeypatch.setattr(image_create, "generate_nim_image", uret)

    sonuc = await image_create.create_image(
        _config(), {"istem": "kırmızı kask", "saglayici": _NIM}, environ=_ENV
    )

    assert sonuc["ok"] is True
    assert alinan == {
        "model": "black-forest-labs/flux.1-dev",
        "istem": "kırmızı kask",
        "anahtar": "test-anahtari",
    }
    assert (galeri / "a.jpg.json").is_file()


async def test_referans_gereken_islem_referanssiz_calismaz(galeri) -> None:
    sonuc = await image_create.create_image(
        _config("gemini_web/main/auto"), {"istem": "", "islem": "buyut"}, environ={}
    )
    assert sonuc == {"ok": False, "metin": "Bu işlem için bir görsel girdisi bağla."}


async def test_galeri_disindaki_dosya_referans_olamaz(galeri, tmp_path_factory) -> None:
    disari = tmp_path_factory.mktemp("disari") / "gizli.png"
    disari.write_bytes(b"\x89PNG")

    sonuc = await image_create.create_image(
        _config("gemini_web/main/auto"),
        {"istem": "x", "islem": "duzenle", "referans": str(disari)},
        environ={},
    )

    assert sonuc == {"ok": False, "metin": "Referans görsel galeride bulunamadı."}


async def test_nim_referans_almaz(galeri) -> None:
    referans = galeri / "r.png"
    referans.write_bytes(b"\x89PNG")

    sonuc = await image_create.create_image(
        _config(),
        {"istem": "x", "islem": "varyasyon", "saglayici": _NIM, "referans": str(referans)},
        environ=_ENV,
    )

    assert sonuc["ok"] is False and "referans görsel almaz" in sonuc["metin"]


async def test_duzenleme_istemi_referansla_web_saglayiciya_gider(galeri, monkeypatch) -> None:
    referans = galeri / "r.png"
    referans.write_bytes(b"\x89PNG")
    alinan: dict[str, object] = {}

    async def uret(_oturum, _kimlik, istem, klasor, *, reference=None):
        alinan.update(istem=istem, reference=reference)
        yol = klasor / "b.png"
        yol.write_bytes(b"\x89PNG")
        return [GeneratedImage(yol, 1024, 1024)]

    monkeypatch.setattr(image_create, "generate_images", uret)

    sonuc = await image_create.create_image(
        _config("gemini_web/main/auto"),
        {"istem": "kaskı mat siyah yap", "islem": "duzenle", "referans": str(referans)},
        environ={},
    )

    assert sonuc["ok"] is True
    assert alinan["reference"] == referans.resolve()
    assert str(alinan["istem"]).startswith("Ekteki görseli şu şekilde düzenle")
    assert "kaskı mat siyah yap" in str(alinan["istem"])


class _SahteSayfa:
    async def close(self) -> None:
        return None


class _SahteHavuz:
    def __init__(self) -> None:
        self.sayfa = _SahteSayfa()

    @asynccontextmanager
    async def lock_for(self, _provider, _account):
        yield

    async def context_for(self, _session, _credential):
        havuz = self

        class _Baglam:
            async def new_page(self):
                return havuz.sayfa

        return _Baglam()

    def schedule_idle_release(self, _provider, _account) -> None:
        return None


async def test_referans_yuklenemezse_istem_gonderilmez(tmp_path, monkeypatch) -> None:
    """Yükleme başarısızsa referanssız görsel 'düzenlendi' diye sunulmamalı."""
    gonderildi: list[str] = []

    async def acik(_page, _definition) -> None:
        return None

    async def yuklenemedi(_page, _path) -> bool:
        return False

    async def doldur(_girdi, metin) -> None:
        gonderildi.append(metin)

    monkeypatch.setattr(web_image, "_open_ready_conversation", acik)
    monkeypatch.setattr(web_image, "gemini_attach_file", yuklenemedi)
    monkeypatch.setattr(web_image, "_fill_editor", doldur)
    oturum = WebSessionConfig(
        model="gemini_web/main/auto", transport="browser", provider="gemini_web"
    )

    with pytest.raises(WebBrowserError, match="yüklenemedi"):
        await web_image.generate_images(
            oturum, None, "düzenle", tmp_path, pool=_SahteHavuz(), reference=tmp_path / "r.png"
        )
    assert gonderildi == []


async def test_chatgpt_referans_gorsel_yuklemeyi_denemez(tmp_path) -> None:
    oturum = WebSessionConfig(
        model="chatgpt_web/main/auto", transport="browser", provider="chatgpt_web"
    )

    with pytest.raises(WebBrowserError, match="referans görsel yükleyemiyor"):
        await web_image.generate_images(oturum, None, "x", tmp_path, reference=tmp_path / "r.png")
