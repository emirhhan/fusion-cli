import httpx
import pytest

from fusion_cli.providers.api_validation import validate_api_key


@pytest.mark.parametrize(
    "status,expected", [(200, True), (401, False), (403, False), (429, False), (500, False)]
)
async def test_anahtar_sinamasi_saglayici_yanitini_ayirt_eder(status, expected):
    def handle(request):
        assert request.url.host == "openrouter.ai"
        assert request.headers["authorization"] == "Bearer test-value"
        return httpx.Response(status, json={"data": {}})

    result = await validate_api_key(
        "openrouter", "test-value", transport=httpx.MockTransport(handle)
    )
    assert result.ok is expected
    assert "test-value" not in result.message


async def test_yonlendirme_takip_edilip_anahtar_baska_sunucuya_gonderilmez():
    result = await validate_api_key(
        "openai",
        "test-value",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"location": "https://example.com"})
        ),
    )
    assert not result.ok
