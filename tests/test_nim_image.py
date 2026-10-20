"""NVIDIA NIM görsel üretimi — sahte HTTP taşımasıyla (gerçek ağa çıkılmaz)."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from fusion_cli.providers.nim_image import (
    NIM_IMAGE_MODELS,
    NimImageError,
    generate_nim_image,
    nim_model_from_choice,
)
from tests.image_fixture import image_bytes

_JPEG = image_bytes("JPEG")


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_basarili_uretim_galeriye_yazilir(tmp_path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        payload = {
            "artifacts": [{"base64": base64.b64encode(_JPEG).decode(), "finishReason": "SUCCESS"}]
        }
        return httpx.Response(200, json=payload)

    async with _client(handler) as client:
        images = await generate_nim_image(
            NIM_IMAGE_MODELS[0], "kırmızı kask", tmp_path, api_key="test-anahtari", client=client
        )

    assert seen["url"].endswith("/v1/genai/black-forest-labs/flux.1-dev")
    assert seen["body"]["prompt"] == "kırmızı kask"
    assert seen["auth"] == "Bearer test-anahtari"
    assert images[0].path.suffix == ".jpg"
    assert images[0].path.read_bytes() == _JPEG


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(404, text="Not found for account"), "404"),
        (
            httpx.Response(
                200, json={"artifacts": [{"base64": "", "finishReason": "CONTENT_FILTERED"}]}
            ),
            "CONTENT_FILTERED",
        ),
        (
            httpx.Response(
                200, json={"artifacts": [{"base64": base64.b64encode(b"abc").decode()}]}
            ),
            "geçerli bir görsel",
        ),
    ],
)
async def test_basarisiz_yanit_acik_hata_verir(tmp_path, response, message) -> None:
    async with _client(lambda _request: response) as client:
        with pytest.raises(NimImageError, match=message):
            await generate_nim_image(
                NIM_IMAGE_MODELS[0], "kask", tmp_path, api_key="test-anahtari", client=client
            )
    assert list(tmp_path.iterdir()) == []


def test_yalniz_olculmus_modeller_secilebilir() -> None:
    assert nim_model_from_choice("nvidia_nim/black-forest-labs/flux.1-dev") is not None
    assert nim_model_from_choice("nvidia_nim/black-forest-labs/flux.1-schnell") is None
    assert nim_model_from_choice("gemini_web/main") is None


async def test_png_baslikli_html_uretilmis_gorsel_sayilmaz(tmp_path):
    encoded = base64.b64encode(b"\x89PNG<!doctype html>").decode()
    async with _client(
        lambda request: httpx.Response(200, json={"artifacts": [{"base64": encoded}]})
    ) as client:
        with pytest.raises(NimImageError, match="geçerli bir görsel"):
            await generate_nim_image(
                NIM_IMAGE_MODELS[0], "örnek", tmp_path, api_key="test", client=client
            )
    assert list(tmp_path.iterdir()) == []


async def test_kayit_iscisi_bitmeden_iptal_tamamlandi_sayilmaz(tmp_path, monkeypatch):
    import asyncio
    import threading

    from fusion_cli.providers import nim_image

    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_write = nim_image._write

    def paused_write(path, data):
        started.set()
        release.wait(timeout=5)
        original_write(path, data)
        finished.set()

    monkeypatch.setattr(nim_image, "_write", paused_write)
    async with _client(
        lambda request: httpx.Response(
            200, json={"artifacts": [{"base64": base64.b64encode(_JPEG).decode()}]}
        )
    ) as client:
        task = asyncio.create_task(
            generate_nim_image(
                NIM_IMAGE_MODELS[0], "örnek", tmp_path, api_key="test", client=client
            )
        )
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await asyncio.to_thread(finished.wait, 2)
