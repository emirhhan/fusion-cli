"""MCP bağlantı davranışı birebir: zaman sınırları, ${VAR}, kimlik bilgisi boşaltma, stdio
ortamı, headersHelper (#233, #239, #243, #244, #245, #249, #273)."""

from __future__ import annotations

import asyncio
import sys

import pytest

from fusion_cli.config.models import McpScope, McpServerConfig, McpTransport
from fusion_cli.core.env_refs import expand_claude_refs
from fusion_cli.mcp_bridge import headers_helper, timeouts
from fusion_cli.mcp_bridge.transport import (
    resolve_remote_url,
    resolve_static_headers,
    stdio_process_env,
)

HTTP = McpServerConfig(name="h", transport=McpTransport.STREAMABLE_HTTP, url="https://a")
STDIO = McpServerConfig(name="s", command="c")


def test_arac_cagrisi_varsayilani_28_saat_ve_oncelik_sirasi():
    assert timeouts.tool_timeout_ms(STDIO, {}) == 100_000_000
    assert timeouts.tool_timeout_ms(STDIO, {"MCP_TOOL_TIMEOUT": "5000"}) == 5000
    server = McpServerConfig(name="s", command="c", timeout_ms=7000)
    assert timeouts.tool_timeout_ms(server, {"MCP_TOOL_TIMEOUT": "5000"}) == 7000
    eski = McpServerConfig(name="s", command="c", call_timeout_s=3)
    assert timeouts.tool_timeout_ms(eski, {}) == 3000


def test_http_istek_siniri_en_az_60_sn_ve_baslatma_30_sn():
    assert timeouts.http_request_timeout_s(HTTP, {}) == 60
    assert timeouts.http_request_timeout_s(HTTP, {"MCP_TOOL_TIMEOUT": "120000"}) == 120
    assert timeouts.http_request_timeout_s(HTTP, {"MCP_TIMEOUT": "90000"}) == 90
    assert timeouts.startup_timeout_s(STDIO, {}) == 30
    assert timeouts.startup_timeout_s(STDIO, {"MCP_TIMEOUT": "10000"}) == 10


def test_bosta_kalma_ag_5_dk_stdio_30_dk_ve_ortam_degiskeni():
    assert timeouts.idle_timeout_s(HTTP, {}) == 300
    assert timeouts.idle_timeout_s(STDIO, {}) == 1800
    assert timeouts.idle_timeout_s(STDIO, {"CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT": "0"}) is None
    assert timeouts.idle_timeout_s(STDIO, {"CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT": "10"}) == 1
    uzun = McpServerConfig(name="s", command="c", timeout_ms=3_600_000)
    assert timeouts.idle_timeout_s(uzun, {}) == 3600


def test_eksik_degisken_metin_kalir_bos_metin_tanimli_sayilir():
    assert expand_claude_refs("${YOK}/x", {}) == ("${YOK}/x", ("YOK",))
    assert expand_claude_refs("${B:-varsayilan}/mcp", {"B": ""}) == ("/mcp", ())
    assert expand_claude_refs("${B:-varsayilan}/mcp", {}) == ("varsayilan/mcp", ())


def test_uzak_url_ve_basliklarda_kimlik_bilgisi_bos_okunur():
    ortam = {"ANTHROPIC_API_KEY": "sk-gizli", "API_KEY": "k", "ANTHROPIC_BASE_URL": "https://g"}
    server = McpServerConfig(
        name="h",
        transport=McpTransport.STREAMABLE_HTTP,
        url="${ANTHROPIC_BASE_URL}/mcp?k=${ANTHROPIC_API_KEY:-x}",
        headers=(("Authorization", "Bearer ${ANTHROPIC_API_KEY}"), ("X-Key", "${API_KEY}")),
    )
    assert resolve_remote_url(server, environ=ortam) == "https://g/mcp?k="
    assert resolve_static_headers(server, environ=ortam) == {
        "Authorization": "Bearer ",
        "X-Key": "k",
    }


def test_stdio_kabuk_ortamini_miras_alir_allowlist_ile_daralir(tmp_path):
    ortam = {"PATH": "/usr/bin", "KABUK_DEGISKENI": "1", "HOME": "/h"}
    server = McpServerConfig(name="s", command="c", env_literals=(("A", "b"),))
    tam = stdio_process_env(server, environ=ortam, project_dir=tmp_path)
    assert tam["KABUK_DEGISKENI"] == "1" and tam["A"] == "b"
    assert tam["CLAUDE_PROJECT_DIR"] == str(tmp_path)
    dar = stdio_process_env(
        server, environ={**ortam, "CLAUDE_CODE_MCP_ALLOWLIST_ENV": "1"}, project_dir=tmp_path
    )
    assert "KABUK_DEGISKENI" not in dar and dar["A"] == "b"


def _helper(scope: McpScope, command: str) -> McpServerConfig:
    return McpServerConfig(
        name="iç",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://mcp.internal.example",
        headers_helper=command,
        scope=scope,
    )


def test_headers_helper_json_basliklari_ve_ortam_degiskenleri(tmp_path):
    komut = (
        f"{sys.executable} -c \"import json,os;print(json.dumps({{'Authorization': 'Bearer t',"
        f" 'X-Ad': os.environ['CLAUDE_CODE_MCP_SERVER_NAME']}}))\""
    )
    sonuc = asyncio.run(
        headers_helper.run_headers_helper(_helper(McpScope.USER, komut), root=tmp_path)
    )
    assert sonuc == {"Authorization": "Bearer t", "X-Ad": "iç"}
    assert headers_helper.has_authorization(sonuc)


def test_proje_kaynakli_yardimci_kimlik_degiskenlerini_gormez():
    ortam = {"MY_REGISTRY_TOKEN": "x", "ANTHROPIC_API_KEY": "y", "GIT_CONFIG_KEY_0": "z", "A": "1"}
    proje = headers_helper.helper_environment(_helper(McpScope.PROJECT, "x"), ortam)
    assert "MY_REGISTRY_TOKEN" not in proje and "ANTHROPIC_API_KEY" not in proje
    assert proje["GIT_CONFIG_KEY_0"] == "z" and proje["A"] == "1"
    kullanici = headers_helper.helper_environment(_helper(McpScope.USER, "x"), ortam)
    assert kullanici["MY_REGISTRY_TOKEN"] == "x"


def test_headers_helper_hatali_cikti_acik_hata():
    with pytest.raises(ValueError, match="JSON"):
        headers_helper.parse_helper_output("a", "değil")
    with pytest.raises(ValueError, match="dizgi"):
        headers_helper.parse_helper_output("a", '{"a": 1}')


def test_sse_tasimasi_basliklarla_acilir_ws_adresi_dogrulanir(monkeypatch):
    from contextlib import asynccontextmanager

    from fusion_cli.mcp_bridge import transport
    from fusion_cli.mcp_bridge.ws_transport import validate_ws_url

    yakalanan = {}

    @asynccontextmanager
    async def _sahte_sse(url, **kwargs):
        yakalanan.update(url=url, **kwargs)
        yield ("okuma", "yazma")

    monkeypatch.setattr(transport, "sse_client", _sahte_sse)
    monkeypatch.setenv("TAKIM_TOKEN", "t")
    server = McpServerConfig(
        name="asana",
        transport=McpTransport.SSE,
        url="https://mcp.asana.com/sse",
        headers=(("Authorization", "Bearer ${TAKIM_TOKEN}"),),
    )

    async def _ac():
        async with transport.open_mcp_stream(server, extra_headers={"X-D": "1"}) as akis:
            return akis

    assert asyncio.run(_ac()) == ("okuma", "yazma")
    assert yakalanan["headers"] == {"Authorization": "Bearer t", "X-D": "1"}
    assert yakalanan["timeout"] == 60
    validate_ws_url("wss://mcp.example.com/socket")
    with pytest.raises(ValueError, match="wss"):
        validate_ws_url("ws://uzak.example.com/socket")
