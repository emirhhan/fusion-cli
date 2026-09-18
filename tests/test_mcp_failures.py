"""Bağlantı hataları türüne ayrılır ve her tür kendi çözümünü söyler.

Ölçüldü (17 Eylül denetimi): 401, var olmayan alan adı ve "giriş gerekli" hepsi
"MCP sunucusu başlatılamadı" diyordu. Buradaki hata nesneleri SDK'nın gerçekte
fırlattıklarıyla aynı biçimdedir (18 Eylül'de canlı uç noktalarla ölçüldü):
HTTP hataları `ExceptionGroup` içinde, paket bulunamayınca yalnız "Connection closed".
"""

from __future__ import annotations

import logging
import socket

import httpx
import pytest
from mcp.client.auth.exceptions import OAuthRegistrationError
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge import oauth as oauth_module
from fusion_cli.mcp_bridge.failures import (
    McpFailureKind,
    classify_failure,
    is_permanent_kind,
    missing_command_failure,
)
from fusion_cli.mcp_bridge.oauth import McpLoginRequiredError


def _remote(*, token: bool = False) -> McpServerConfig:
    return McpServerConfig(
        name="meta",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.example.com/mcp",
        token_env="FUSION_MCP_TOKEN_META" if token else "",
    )


def _stdio(command: str = "npx") -> McpServerConfig:
    return McpServerConfig(name="yerel", command=command, args=("-y", "postgresql://gizli@db"))


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://mcp.example.com/mcp")
    return httpx.HTTPStatusError(
        "hata", request=request, response=httpx.Response(status, request=request)
    )


def _group(*errors: Exception) -> ExceptionGroup:
    return ExceptionGroup("unhandled errors in a TaskGroup", list(errors))


def _closed() -> McpError:
    return McpError(ErrorData(code=-32000, message="Connection closed"))


def test_tokenli_baglantida_401_token_yenilemeyi_soyler():
    failure = classify_failure(_group(_http_error(401)), _remote(token=True))

    assert failure.kind is McpFailureKind.UNAUTHORIZED
    assert "token" in failure.message
    assert "Kaldır" in failure.message


def test_oauth_baglantida_401_yeniden_giris_ister():
    failure = classify_failure(_group(_http_error(401)), _remote())

    assert failure.kind is McpFailureKind.UNAUTHORIZED
    assert "'Bağlan'" in failure.message


def test_403_yetki_eksikligini_ayri_soyler():
    failure = classify_failure(_group(_http_error(403)), _remote(token=True))

    assert failure.kind is McpFailureKind.UNAUTHORIZED
    assert "yetkisi yok" in failure.message


def test_sunucu_5xx_gecici_arizadir():
    failure = classify_failure(_group(_http_error(503)), _remote())

    assert failure.kind is McpFailureKind.SERVER_ERROR
    assert not failure.is_permanent


def test_cozulemeyen_alan_adi_adresi_adiyla_soyler():
    """macOS metni: `[Errno 8] nodename nor servname provided, or not known`."""
    error = httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known")

    failure = classify_failure(_group(error), _remote())

    assert failure.kind is McpFailureKind.HOST_NOT_FOUND
    assert "mcp.example.com" in failure.message
    assert "alan adı çözülemedi" in failure.message


def test_dns_hatasi_neden_zincirinden_de_taninir():
    error = httpx.ConnectError("bağlanılamadı")
    error.__cause__ = socket.gaierror(-2, "bilinmeyen")

    assert classify_failure(error, _remote()).kind is McpFailureKind.HOST_NOT_FOUND


def test_dns_disi_baglanti_hatasi_ag_sorunudur_ve_gecicidir():
    failure = classify_failure(httpx.ConnectError("Connection refused"), _remote())

    assert failure.kind is McpFailureKind.NETWORK
    assert not failure.is_permanent


def test_giris_gerekli_hata_degil_ayri_durumdur():
    failure = classify_failure(_group(McpLoginRequiredError("giriş")), _remote())

    assert failure.kind is McpFailureKind.LOGIN_REQUIRED
    assert failure.state == "giris_gerekli"
    assert "'Bağlan'" in failure.message


def test_kayit_reddi_client_id_ister():
    failure = classify_failure(_group(OAuthRegistrationError("400")), _remote())

    assert failure.kind is McpFailureKind.REGISTRATION_REJECTED
    assert "client_id" in failure.message


def test_asil_neden_zaman_asimi_ve_kapanma_hatasindan_once_gelir():
    """SDK asıl hatanın yanında iptal/kapanma sonuçlarını da verir."""
    error = _group(TimeoutError(), _closed(), _http_error(401))

    assert classify_failure(error, _remote()).kind is McpFailureKind.UNAUTHORIZED


@pytest.mark.parametrize(
    ("command", "expected"),
    [("uvx", "brew install uv"), ("npx", "brew install node"), ("/opt/bin/uvx", "brew install uv")],
)
def test_eksik_calistirici_kurulum_komutuyla_bildirilir(command, expected):
    failure = classify_failure(FileNotFoundError(2, "yok"), _stdio(command))

    assert failure.kind is McpFailureKind.COMMAND_MISSING
    assert expected in failure.message


def test_bilinmeyen_komut_adiyla_bildirilir_argumanlari_gostermez():
    failure = classify_failure(FileNotFoundError(2, "yok"), _stdio("godot-mcp"))

    assert "`godot-mcp`" in failure.message
    assert "postgresql://gizli@db" not in failure.message


def test_npm_404_paket_bulunamadi_olarak_taninir():
    tail = "npm error code E404\nnpm error 404  '@x/y@*' is not in this registry.\n"

    failure = classify_failure(_closed(), _stdio("npx"), stderr_tail=tail)

    assert failure.kind is McpFailureKind.PACKAGE_MISSING
    assert "npm" in failure.message
    # Sunucunun ham çıktısı mesaja kopyalanmaz.
    assert "E404" not in failure.message


def test_uv_paketi_bulunamadi_pypi_ile_bildirilir():
    tail = "  × No solution found when resolving tool dependencies:\n"

    failure = classify_failure(_closed(), _stdio("uvx"), stderr_tail=tail)

    assert failure.kind is McpFailureKind.PACKAGE_MISSING
    assert "PyPI" in failure.message


def test_iz_birakmadan_kapanan_surec_kurulum_alanlarini_isaret_eder():
    failure = classify_failure(_closed(), _stdio("npx"), stderr_tail="Error: API key yok")

    assert failure.kind is McpFailureKind.SERVER_EXITED
    assert "API key" not in failure.message


def test_http_404_mcp_adresinin_yanlis_oldugunu_soyler():
    """SDK `initialize`'a gelen 404'ü "Session terminated" olarak bildirir."""
    error = McpError(ErrorData(code=32600, message="Session terminated"))

    failure = classify_failure(error, _remote())

    assert failure.kind is McpFailureKind.ENDPOINT_NOT_FOUND
    assert "HTTP 404" in failure.message


def test_eksik_sir_yapilandirma_hatasidir():
    error = ValueError("MCP ortam değişkeni bulunamadı: BRAVE_API_KEY")

    failure = classify_failure(error, _stdio())

    assert failure.kind is McpFailureKind.CONFIGURATION
    assert "BRAVE_API_KEY" in failure.message


def test_zaman_asimi_ayri_durumdur_ve_gecicidir():
    failure = classify_failure(TimeoutError(), _stdio())

    assert failure.state == "zaman_asimi"
    assert not failure.is_permanent


def test_taninmayan_hata_turunu_adiyla_soyler():
    failure = classify_failure(RuntimeError("iç ayrıntı"), _stdio())

    assert failure.kind is McpFailureKind.UNKNOWN
    assert "RuntimeError" in failure.message
    assert "iç ayrıntı" not in failure.message


def test_kalici_turler_protokol_degerinden_taninir():
    assert is_permanent_kind("giris_gerekli")
    assert is_permanent_kind("komut_yok")
    assert not is_permanent_kind("zaman_asimi")
    assert not is_permanent_kind(None)


def test_eksik_komut_mesaji_yeniden_eklemeyi_soyler():
    assert "yeniden ekle" in missing_command_failure("uvx").message


def test_beklenen_giris_gereksinimi_sdk_logunda_yigin_dokumu_basmaz(caplog):
    """Notion için her turda "OAuth flow error" yığın dökümü basılıyordu."""
    oauth_module._silence_expected_login_errors()
    oauth_module._silence_expected_login_errors()  # ikinci çağrı filtre çoğaltmaz
    logger = logging.getLogger(oauth_module._SDK_OAUTH_LOGGER)

    with caplog.at_level(logging.ERROR, logger=oauth_module._SDK_OAUTH_LOGGER):
        try:
            raise McpLoginRequiredError("giriş")
        except McpLoginRequiredError:
            logger.exception("OAuth flow error")
        try:
            raise RuntimeError("gerçek hata")
        except RuntimeError:
            logger.exception("OAuth flow error")

    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info[0] is RuntimeError
    assert sum(isinstance(item, oauth_module._ExpectedLoginFilter) for item in logger.filters) == 1
