"""Geçici HTTP durumları kalıcı "adres yok" sayılmaz (WP11).

Ölçüldü (29 Ekim): 429 ve 408 `ENDPOINT_NOT_FOUND`'a düşüyordu. O tür kalıcıdır:
havuz bağlantıyı oturum boyunca bir daha denemiyor, kullanıcıya da "bağlantıyı
Kaldır ve doğru adresle yeniden ekle" deniyordu. Oysa sunucu yalnız "biraz bekle"
diyordu.
"""

from __future__ import annotations

import httpx
import pytest

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.failures import McpFailureKind, classify_failure

_CONFIG = McpServerConfig(
    name="uzak", transport=McpTransport.STREAMABLE_HTTP, url="https://mcp.example.com/mcp"
)


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", _CONFIG.url)
    return httpx.HTTPStatusError(
        "hata", request=request, response=httpx.Response(status, request=request)
    )


@pytest.mark.parametrize(
    ("status", "tur"),
    [(429, McpFailureKind.RATE_LIMITED), (408, McpFailureKind.TIMEOUT)],
)
def test_gecici_durum_kalici_sayilmaz(status, tur):
    failure = classify_failure(_status_error(status), _CONFIG)

    assert failure.kind is tur
    assert not failure.is_permanent
    assert "Kaldır" not in failure.message


@pytest.mark.parametrize("status", [404, 405])
def test_adres_yok_durumlari_kalici_kalir(status):
    failure = classify_failure(_status_error(status), _CONFIG)

    assert failure.kind is McpFailureKind.ENDPOINT_NOT_FOUND
    assert failure.is_permanent
