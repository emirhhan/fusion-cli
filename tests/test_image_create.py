from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.appserver import image_create
from fusion_cli.config.models import WebSessionConfig
from fusion_cli.providers.web_browser import WebBrowserError
from fusion_cli.providers.web_image import GeneratedImage


def _config(tmp_path: Path, *models: str):
    from fusion_cli.config.loader import load_config

    base = load_config()
    oturumlar = tuple(
        WebSessionConfig(model=m, transport="browser", provider=m.split("/")[0]) for m in models
    )
    return replace(base, web_sessions=oturumlar)


def test_saglayicilar_gemini_once_siralanir(tmp_path):
    config = _config(tmp_path, "chatgpt_web/main/auto", "gemini_web/main/auto")

    secenekler = image_create.image_providers(config)

    assert [s["etiket"] for s in secenekler] == ["Gemini", "ChatGPT"]


async def test_bos_istem_reddedilir(tmp_path):
    sonuc = await image_create.create_image(_config(tmp_path, "gemini_web/main/auto"), {})
    assert sonuc["ok"] is False


async def test_uretilen_dosyalar_doner_ve_hata_okunur_kalir(tmp_path, monkeypatch):
    config = _config(tmp_path, "gemini_web/main/auto")
    monkeypatch.setattr(image_create, "image_output_dir", lambda: tmp_path)

    async def uret(_oturum, _kimlik, istem, klasor):
        return [GeneratedImage(klasor / "a.png", 1024, 559)]

    monkeypatch.setattr(image_create, "generate_images", uret)
    sonuc = await image_create.create_image(config, {"istem": "kırmızı kask"})
    assert sonuc["ok"] is True
    assert sonuc["dosyalar"][0]["genislik"] == 1024

    async def engel(*_a, **_k):
        raise WebBrowserError("authentication: Gemini insan doğrulaması (captcha) istiyor.")

    monkeypatch.setattr(image_create, "generate_images", engel)
    sonuc = await image_create.create_image(config, {"istem": "x"})
    assert sonuc == {"ok": False, "metin": "Gemini insan doğrulaması (captcha) istiyor."}


@pytest.mark.parametrize("secim", ["claude_web/main"])
async def test_bilinmeyen_saglayici(tmp_path, secim):
    sonuc = await image_create.create_image(
        _config(tmp_path, "gemini_web/main/auto"), {"istem": "x", "saglayici": secim}
    )
    assert sonuc["ok"] is False
