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

_JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32


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
