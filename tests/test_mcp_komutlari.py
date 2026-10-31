"""MCP komut paritesi (P-049): `fusion mcp add/remove/list/reconnect`, `.mcp.json` proje
kapsamı, `${VAR:-varsayılan}` başvuruları, havuz yeniden bağlanma isteği.

Ölçüldü (31 Ekim): `fusion mcp-add` yalnız stdio ve kapsamsızdı; `.mcp.json` okunmuyor,
`${VAR}` çözülmüyor, `reconnect`/`login` komutu yoktu; `fusion mcp` yalnız sunucu açıyordu.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import mcp_commands
from fusion_cli.config import loader, trust
from fusion_cli.config.mcp_json import (
    PROJECT_MCP_FILE,
    merge_mcp_servers,
    parse_project_mcp,
    read_project_mcp_servers,
    write_project_mcp_servers,
)
from fusion_cli.config.models import McpScope, McpServerConfig, McpTransport
from fusion_cli.config.writer import write_mcp_servers
from fusion_cli.core.env_refs import EnvRefError, expand_env_refs, referenced_names
from fusion_cli.core.errors import ConfigError
from fusion_cli.mcp_bridge.transport import (
    resolve_remote_url,
    resolve_stdio_args,
    resolve_stdio_command,
    resolve_stdio_env,
)

runner = CliRunner()


@pytest.fixture
def izole(tmp_path, monkeypatch):
    """Kullanıcı config'i ve güven kaydı geçici dizinde; çalışma dizini proje kökü."""
    kok = tmp_path / "proje"
    kok.mkdir()
    monkeypatch.chdir(kok)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    # conftest kullanıcı config adaylarını boşaltır; bu testler yazılanı geri okur.
    kullanici_config = tmp_path / "xdg" / "fusion-cli" / "config.yaml"
    monkeypatch.setattr(loader, "user_config_candidates", lambda: (kullanici_config,))
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "guven.json")
    return kok


# --- ${VAR:-varsayılan} ------------------------------------------------------------------ #


def test_env_basvurusu_ortamdan_ve_varsayilandan_cozulur():
    ortam = {"TOKEN": "gizli"}
    assert expand_env_refs("Bearer ${TOKEN}", ortam) == "Bearer gizli"
    assert expand_env_refs("${YOK:-varsayilan}/mcp", ortam) == "varsayilan/mcp"
    assert expand_env_refs("duz metin", ortam) == "duz metin"
    assert referenced_names("${A} ${B:-x} ${A}") == ("A", "B")


def test_varsayilani_olmayan_eksik_basvuru_hata():
    with pytest.raises(EnvRefError, match="YOK"):
        expand_env_refs("${YOK}", {})


def test_tasima_komut_arguman_adres_ve_ortam_degerlerini_baglanti_aninda_cozer():
    config = McpServerConfig(
        name="pg",
        command="${NPX:-npx}",
        args=("-y", "server-postgres", "${DB_URL}"),
        url="https://${HOST:-mcp.example}/mcp",
        env_literals=(("NODE_ENV", "${NODE_ENV:-production}"),),
    )
    ortam = {"DB_URL": "postgres://u:p@h/db"}

    assert resolve_stdio_command(config, environ=ortam) == "npx"
    assert resolve_stdio_args(config, environ=ortam) == [
        "-y",
        "server-postgres",
        "postgres://u:p@h/db",
    ]
    assert resolve_remote_url(config, environ=ortam) == "https://mcp.example/mcp"
    assert resolve_stdio_env(config, environ=ortam) == {"NODE_ENV": "production"}
    # Yapılandırma nesnesi başvuruyu taşımaya devam eder: diske çözülmüş sır yazılmaz.
    assert config.args[-1] == "${DB_URL}"


def test_eksik_basvuru_tasimada_yapilandirma_hatasi():
    config = McpServerConfig(name="x", command="c", args=("${YOK}",))
    with pytest.raises(ValueError, match="YOK"):
        resolve_stdio_args(config, environ={})


# --- .mcp.json --------------------------------------------------------------------------- #

_MCP_JSON = {
    "mcpServers": {
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
        },
        "linear": {"type": "http", "url": "https://mcp.linear.app/mcp"},
    }
}


def test_mcp_json_claude_code_bicimini_proje_kapsamli_kayitlara_cevirir():
    github, linear = parse_project_mcp(_MCP_JSON)

    assert github.scope is McpScope.PROJECT
    assert github.command == "npx"
    assert github.env_literals == (("GITHUB_TOKEN", "${GITHUB_TOKEN}"),)
    assert linear.transport is McpTransport.STREAMABLE_HTTP
    assert linear.url == "https://mcp.linear.app/mcp"


def test_mcp_json_sse_ve_bilinmeyen_alan_acik_hata():
    with pytest.raises(ConfigError, match="sse"):
        parse_project_mcp({"mcpServers": {"x": {"type": "sse", "url": "https://a/b"}}})
    with pytest.raises(ConfigError, match="bilinmeyen"):
        parse_project_mcp({"mcpServers": {"x": {"command": "c", "foo": 1}}})


def test_mcp_json_yazilir_okunur_ve_guven_kaydina_islenir(izole):
    sunucu = McpServerConfig(
        name="fetch", command="uvx", args=("mcp-server-fetch",), scope=McpScope.PROJECT
    )

    yol = write_project_mcp_servers(izole, (sunucu,))

    assert yol == izole / PROJECT_MCP_FILE
    assert read_project_mcp_servers(izole) == (sunucu,)
    assert trust.is_file_trusted(izole, yol)


def test_guvenilmeyen_mcp_json_yuklenmez_guvenilen_yuklenir(izole):
    (izole / PROJECT_MCP_FILE).write_text(json.dumps(_MCP_JSON), encoding="utf-8")

    assert {s.name for s in loader.load_config().mcp_servers} == set()

    trust.trust_project(izole)
    yuklenen = {s.name: s for s in loader.load_config().mcp_servers}
    assert set(yuklenen) == {"github", "linear"}
    assert yuklenen["github"].scope is McpScope.PROJECT


def test_proje_kaydi_ayni_adli_kullanici_kaydini_gecer():
    kullanici = McpServerConfig(name="github", command="eski")
    proje = McpServerConfig(name="github", command="yeni", scope=McpScope.PROJECT)
    diger = McpServerConfig(name="diger", command="d")

    birlesik = merge_mcp_servers((kullanici, diger), (proje,))

    assert [s.name for s in birlesik] == ["diger", "github"]
    assert birlesik[-1].command == "yeni"


def test_config_yaml_yazici_proje_kaydini_kopyalamaz(tmp_path):
    hedef = tmp_path / "config.yaml"
    kullanici = McpServerConfig(name="u", command="c", env_literals=(("A", "1"),))
    proje = McpServerConfig(name="p", command="c", scope=McpScope.PROJECT)
    config = replace(loader.load_config(), mcp_servers=(kullanici, proje))

    write_mcp_servers(config, hedef)
    geri = loader.load_config(hedef)

    assert geri.mcp_servers == (kullanici,)


# --- fusion mcp alt grubu ----------------------------------------------------------------- #


def test_mcp_add_kullanici_kapsamina_yazar(izole, tmp_path):
    result = runner.invoke(
        app_module.app, ["mcp", "add", "github", "npx", "--", "-y", "server-github"]
    )

    assert result.exit_code == 0, result.output
    yazilan = (tmp_path / "xdg" / "fusion-cli" / "config.yaml").read_text(encoding="utf-8")
    assert "name: github" in yazilan and "server-github" in yazilan


def test_mcp_add_proje_kapsami_mcp_json_yazar_ve_remove_oradan_siler(izole):
    result = runner.invoke(
        app_module.app,
        [
            "mcp",
            "add",
            "pg",
            "--scope",
            "project",
            "npx",
            "-e",
            "DATABASE_URL",
            "-e",
            "NODE_ENV=prod",
            "--",
            "-y",
            "server-postgres",
        ],
    )

    assert result.exit_code == 0, result.output
    veri = json.loads((izole / PROJECT_MCP_FILE).read_text(encoding="utf-8"))
    giris = veri["mcpServers"]["pg"]
    assert giris["command"] == "npx" and giris["args"] == ["-y", "server-postgres"]
    assert giris["env"] == {"NODE_ENV": "prod", "DATABASE_URL": "${DATABASE_URL}"}
    assert [s.name for s in loader.load_config().mcp_servers] == ["pg"]

    result = runner.invoke(app_module.app, ["mcp", "remove", "pg"])
    assert result.exit_code == 0, result.output
    assert json.loads((izole / PROJECT_MCP_FILE).read_text(encoding="utf-8"))["mcpServers"] == {}


def test_mcp_add_http_adres_ister_ve_add_json_calisir(izole):
    result = runner.invoke(app_module.app, ["mcp", "add", "linear", "--transport", "http"])
    assert result.exit_code != 0

    result = runner.invoke(
        app_module.app,
        ["mcp", "add-json", "fetch", json.dumps({"command": "uvx", "args": ["mcp-server-fetch"]})],
    )
    assert result.exit_code == 0, result.output
    assert [s.command for s in loader.load_config().mcp_servers] == ["uvx"]


def test_mcp_list_kapsam_ve_tasima_gosterir(izole):
    runner.invoke(app_module.app, ["mcp", "add", "a", "npx"])
    result = runner.invoke(app_module.app, ["mcp", "list"])

    assert result.exit_code == 0
    assert "kullanıcı" in result.output and "stdio" in result.output


def test_eski_mcp_add_takma_adi_calisir(izole, tmp_path):
    result = runner.invoke(app_module.app, ["mcp-add", "github", "npx", "--", "-y", "x"])

    assert result.exit_code == 0, result.output
    assert "name: github" in (tmp_path / "xdg" / "fusion-cli" / "config.yaml").read_text()


def test_alt_komutsuz_mcp_sunucuyu_acar(monkeypatch):
    cagrildi = {}

    async def _sahte(root, *, expose_mutating):
        cagrildi["write"] = expose_mutating

    monkeypatch.setattr("fusion_cli.mcp_bridge.server.run_stdio", _sahte)
    result = runner.invoke(app_module.app, ["mcp", "--write"])

    assert result.exit_code == 0, result.output
    assert cagrildi == {"write": True}


def test_mcp_reconnect_servisi_cagirir(izole, monkeypatch):
    runner.invoke(app_module.app, ["mcp", "add", "a", "npx"])
    cagrilar = []

    class _Servis:
        async def reconnect(self, config):
            cagrilar.append(config.name)
            return SimpleNamespace(server=config.name, state="bagli", message="", tool_count=3)

    monkeypatch.setattr("fusion_cli.mcp_bridge.service.McpConnectionService", _Servis)
    result = runner.invoke(app_module.app, ["mcp", "reconnect", "all"])

    assert result.exit_code == 0, result.output
    assert cagrilar == ["a"] and "bagli" in result.output


def test_env_secenegi_sir_adi_ve_duz_degeri_ayirir():
    assert mcp_commands.split_env_options(["TOKEN", "NODE_ENV=prod", " "]) == (
        ("TOKEN",),
        (("NODE_ENV", "prod"),),
    )


# --- havuz: ertelenmiş yeniden bağlanma ---------------------------------------------------- #


def test_havuz_reconnect_istegi_canli_girdiyi_bir_sonraki_turda_dusurur():
    from fusion_cli.mcp_bridge import pool as pool_module

    havuz = pool_module.McpToolPool()
    config = McpServerConfig(name="a", command="c")
    atilan = []

    async def _senaryo():
        loop = asyncio.get_running_loop()
        girdi = pool_module._Entry(config=config, loop=loop)
        girdi.client = SimpleNamespace(is_stalled=False)  # type: ignore[assignment]
        girdi.task = loop.create_task(asyncio.Event().wait())
        girdi.ready.set()
        havuz._entries["a"] = girdi

        async def _discard(entry, _loop):
            atilan.append(entry.config.name)

        havuz._discard = _discard  # type: ignore[method-assign]
        await havuz._discard_stale((config,), loop)
        assert atilan == []  # canlı ve istenen: kalır
        havuz.request_reconnect("a")
        await havuz._discard_stale((config,), loop)
        girdi.task.cancel()

    asyncio.run(_senaryo())
    assert atilan == ["a"]


def test_repl_mcp_reconnect_ve_liste(monkeypatch, tmp_path):
    from fusion_cli.cli.repl import commands as repl_commands
    from fusion_cli.mcp_bridge import pool as pool_module

    istenen = []
    monkeypatch.setattr(pool_module, "request_mcp_reconnect", lambda name: istenen.append(name))
    config = replace(
        loader.load_config(),
        mcp_servers=(
            McpServerConfig(name="a", command="npx"),
            McpServerConfig(name="p", command="c", scope=McpScope.PROJECT),
        ),
    )
    state = SimpleNamespace(config=config)

    assert "a" in repl_commands._mcp(state, "reconnect a")
    assert istenen == ["a"]
    assert "yok" in repl_commands._mcp(state, "reconnect olmayan")
    assert "2" in repl_commands._mcp(state, "reconnect all")
    liste = repl_commands._mcp(state, "")
    assert "proje" in liste and "kullanıcı" in liste
