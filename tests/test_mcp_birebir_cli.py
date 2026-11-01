"""`fusion mcp` Claude Code sözdizimi birebir (#235, #236, #237, #247, #248, #252, #259,
#261, #265, #266, #269, #271, #272)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import mcp_commands, mcp_manage
from fusion_cli.config import loader, trust
from fusion_cli.config.mcp_local import read_local_mcp_servers
from fusion_cli.config.models import McpScope, McpServerConfig, McpTransport
from fusion_cli.mcp_bridge import oauth

runner = CliRunner()


@pytest.fixture
def izole(tmp_path, monkeypatch):
    kok = tmp_path / "proje"
    kok.mkdir()
    monkeypatch.chdir(kok)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    kullanici = tmp_path / "xdg" / "fusion-cli" / "config.yaml"
    monkeypatch.setattr(loader, "user_config_candidates", lambda: (kullanici,))
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "guven.json")

    async def _durum(server):
        return "✔ Bağlandı"

    monkeypatch.setattr(mcp_manage, "_health", _durum)
    temizlenen: list[str] = []

    async def _temizle(server):
        temizlenen.append(server.url)

    monkeypatch.setattr(mcp_manage, "_clear_credentials", _temizle)
    monkeypatch.setattr(mcp_manage, "TEMIZLENEN_TEST", temizlenen, raising=False)
    return kok


def _invoke(*args: str):
    return runner.invoke(app_module.app, ["mcp", *args])


def test_claude_http_sozdizimi_konumsal_url_ve_varsayilan_local(izole):
    result = _invoke("add", "--transport", "http", "notion", "https://mcp.notion.com/mcp")
    assert result.exit_code == 0, result.output
    (server,) = read_local_mcp_servers(izole)
    assert server.transport is McpTransport.STREAMABLE_HTTP
    assert server.url == "https://mcp.notion.com/mcp"
    assert server.scope is McpScope.LOCAL
    assert [s.name for s in loader.load_config().mcp_servers] == ["notion"]


def test_header_tekrarlanabilir_ve_degisken_basvurusu_korunur(izole):
    result = _invoke(
        "add",
        "--transport",
        "sse",
        "asana",
        "https://mcp.asana.com/sse",
        "-H",
        "Authorization: Bearer ${API_KEY}",
        "--header",
        "X-Team: core",
    )
    assert result.exit_code == 0, result.output
    (server,) = read_local_mcp_servers(izole)
    assert server.transport is McpTransport.SSE
    assert server.headers == (("Authorization", "Bearer ${API_KEY}"), ("X-Team", "core"))


def test_ad_kurali_ws_reddi_ve_env_key_value(izole):
    assert _invoke("add", "META ADS", "npx").exit_code != 0
    assert _invoke("add", "--transport", "ws", "x", "wss://a").exit_code != 0
    result = _invoke("add", "air", "-e", "AIRTABLE_API_KEY=k", "--", "npx", "-y", "airtable")
    assert result.exit_code == 0, result.output
    (server,) = read_local_mcp_servers(izole)
    assert server.env_literals == (("AIRTABLE_API_KEY", "k"),)
    assert server.command == "npx" and server.args == ("-y", "airtable")


def test_oauth_bayraklari_ve_client_secret_anahtarlikta(izole, monkeypatch):
    saklanan: list[str] = []

    async def _sakla(server, secret):
        saklanan.append(secret)

    monkeypatch.setattr("fusion_cli.cli.mcp_add.store_client_secret", _sakla)
    monkeypatch.setenv("MCP_CLIENT_SECRET", "gizli")
    result = _invoke(
        "add",
        "--transport",
        "http",
        "--client-id",
        "cid",
        "--client-secret",
        "--callback-port",
        "8080",
        "my-server",
        "https://mcp.example.com/mcp",
    )
    assert result.exit_code == 0, result.output
    (server,) = read_local_mcp_servers(izole)
    assert server.client_id == "cid" and server.oauth_callback_port == 8080
    assert saklanan == ["gizli"]
    assert "gizli" not in json.dumps(read_local_mcp_servers(izole)[0].__repr__())


def test_add_json_oauth_ve_client_secret(izole, monkeypatch):
    monkeypatch.setattr("fusion_cli.cli.mcp_add.store_client_secret", _noop_store)
    monkeypatch.setenv("MCP_CLIENT_SECRET", "s")
    tanim = {"type": "http", "url": "https://a.example/mcp", "oauth": {"clientId": "c"}}
    result = _invoke("add-json", "srv", json.dumps(tanim), "--client-secret", "-s", "user")
    assert result.exit_code == 0, result.output
    (server,) = loader.load_config().mcp_servers
    assert server.scope is McpScope.USER and server.client_id == "c"


async def _noop_store(server, secret):
    return None


def test_remove_scope_belirsizligi_ve_token_temizligi(izole):
    _invoke("add", "--transport", "http", "--scope", "user", "x", "https://a.example/mcp")
    _invoke("add", "--transport", "http", "x", "https://a.example/mcp")
    belirsiz = _invoke("remove", "x")
    assert belirsiz.exit_code != 0 and "--scope" in belirsiz.output
    assert _invoke("remove", "x", "--scope", "local").exit_code == 0
    # Kullanıcı kaydı aynı adresi kullanmaya devam ediyor: token silinmez.
    assert mcp_manage.TEMIZLENEN_TEST == []
    assert _invoke("remove", "x", "-s", "user").exit_code == 0
    assert mcp_manage.TEMIZLENEN_TEST == ["https://a.example/mcp"]


def test_list_durum_bekleyen_proje_ve_eksik_degisken(izole, monkeypatch):
    monkeypatch.delenv("YOK_DEGISKEN", raising=False)
    (izole / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"team": {"command": "npx"}, "bozuk": {"url": "https://a"}}}),
        encoding="utf-8",
    )
    _invoke("add", "--transport", "http", "api", "https://a.example/${YOK_DEGISKEN}")
    result = _invoke("list")
    assert result.exit_code == 0, result.output
    assert "api: https://a.example/${YOK_DEGISKEN} (yerel) - ✔ Bağlandı" in result.output
    assert "YOK_DEGISKEN" in result.output and "eksik" in result.output
    assert "team: npx (proje) - ⏸ Onay bekliyor" in result.output
    assert "Atlandı" in result.output


def test_get_ayrinti_degerleri_basmaz(izole):
    _invoke("add", "--transport", "http", "api", "https://a.example/mcp", "-H", "X-Key: sabit")
    result = _invoke("get", "api")
    assert result.exit_code == 0, result.output
    assert "Kapsam: yerel (local)" in result.output and "Başlıklar: X-Key" in result.output
    assert "sabit" not in result.output


def test_serve_tum_araclari_acar_ciplak_mcp_tty_de_yardim(monkeypatch):
    cagrildi = {}

    async def _sahte(root, *, expose_mutating):
        cagrildi["write"] = expose_mutating

    monkeypatch.setattr("fusion_cli.mcp_bridge.server.run_stdio", _sahte)
    assert _invoke("serve").exit_code == 0 and cagrildi == {"write": True}
    monkeypatch.setattr(mcp_commands.sys.stdin, "isatty", lambda: True, raising=False)
    result = _invoke()
    assert result.exit_code == 0 and "serve" in result.output


def test_fazladan_alt_komutlar_yardimda_gizli():
    result = _invoke("--help")
    for gizli in ("tools", "prompts", "resources", "--token-env"):
        assert gizli not in result.output
    for gorunur in ("add", "add-json", "get", "list", "remove", "login", "logout", "serve"):
        assert gorunur in result.output


def test_oauth_donus_portu_ve_yolu():
    yeni = McpServerConfig(name="a", transport=McpTransport.STREAMABLE_HTTP, url="https://a")
    assert oauth.callback_settings(yeni, {}) == (0, "/callback")
    assert oauth.callback_settings(yeni, {"MCP_OAUTH_CALLBACK_PORT": "9000"}) == (9000, "/callback")
    sabit = McpServerConfig(name="a", url="https://a", oauth_callback_port=8080)
    assert oauth.callback_settings(sabit, {}) == (8080, "/callback")
    eski = McpServerConfig(name="a", url="https://a", client_id="cid")
    assert oauth.callback_settings(eski, {}) == (8765, "/oauth/callback")


def test_no_browser_yapistirilan_donus_adresi_kabul_edilir():
    callback = oauth.LoopbackOAuthCallback(port=0, path="/callback")
    callback._expected_state = "s1"

    async def _calistir():
        import asyncio

        callback._result = asyncio.get_running_loop().create_future()
        callback._accept_pasted("http://localhost:1234/callback?code=abc&state=s1")
        return await callback._result

    import asyncio

    assert asyncio.run(_calistir()) == ("abc", "s1")
    with pytest.raises(Exception, match="code/state"):
        callback._accept_pasted("http://localhost:1/callback?code=x&state=yanlis")


def test_claude_desktop_ice_aktarma_ad_suzgeci_ve_ek(izole, monkeypatch, tmp_path):
    from fusion_cli.cli import mcp_desktop_import

    masaustu = tmp_path / "claude_desktop_config.json"
    masaustu.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {"command": "npx", "args": ["-y", "gh"]},
                    "META ADS": {"command": "x"},
                    "fetch": {"command": "uvx"},
                }
            }
        ),
        encoding="utf-8",
    )
    _invoke("add", "github", "zaten")
    monkeypatch.setattr(mcp_desktop_import, "desktop_config_path", lambda home=None: masaustu)
    result = runner.invoke(app_module.app, ["mcp", "add-from-claude-desktop"], input="\n")
    assert result.exit_code == 0, result.output
    assert "META ADS" in result.output and "Atlandı" in result.output
    assert {s.name for s in read_local_mcp_servers(izole)} == {"github", "github_1", "fetch"}
