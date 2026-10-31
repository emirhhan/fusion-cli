"""MCP istemleri (`/mcp__sunucu__istem`) ve kaynak anması (`@sunucu:uri`) (P-049).

Ölçüldü (31 Ekim): köprüde `prompts/list|get` ve `resources/list|read` hiç yoktu; MCP istemleri
slash komutu olarak görünmüyor, `@sunucu:kaynak` anması "henüz desteklenmiyor" notuyla
geçiliyordu.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.cli import session as cli_session
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.models import McpServerConfig
from fusion_cli.core.events import ErrorOccurred, StatusChanged
from fusion_cli.mcp_bridge import pool as pool_module
from fusion_cli.mcp_bridge import reference_service
from fusion_cli.mcp_bridge.pool import McpToolPool
from fusion_cli.mcp_bridge.references import (
    RESOURCE_MAX_CHARS,
    McpCatalog,
    McpPrompt,
    McpPromptArgument,
    bind_arguments,
    fetch_catalog,
    parse_prompt_call,
    prompt_text,
    resource_block,
    resource_mentions,
)
from fusion_cli.memory.factory import null_memory

from .fakes import make_config

PR = McpPrompt(
    server="github",
    name="review-pr",
    description="PR'ı incele",
    arguments=(McpPromptArgument("numara", required=True), McpPromptArgument("odak")),
)


# --- Saf parçalar ----------------------------------------------------------------- #


def test_istem_cagrisi_ve_arguman_baglama():
    assert parse_prompt_call("/mcp__github__review-pr 12 güvenlik") == (
        "mcp__github__review-pr",
        "12 güvenlik",
    )
    assert parse_prompt_call("merhaba /mcp__x") is None
    assert bind_arguments(PR, "12 güvenlik ve hız") == (
        {"numara": "12", "odak": "güvenlik ve hız"},
        "",
    )
    assert bind_arguments(PR, "odak=testler numara=7") == ({"odak": "testler", "numara": "7"}, "")
    assert "eksik zorunlu argüman: numara" in bind_arguments(PR, "")[1]
    assert McpPrompt("s p", "a/b").slash_name == "mcp__s_p__a_b"
    assert PR.usage == "<numara> [odak]"


def test_kaynak_anmasi_yalniz_tanimli_sunucu_ve_e_posta_degil():
    found = resource_mentions(
        "bak @github:repos/a/issues/1, ayrıca ali@github:x ve @bilinmeyen:y", ["github"]
    )

    assert found == (("github", "repos/a/issues/1"),)


def test_istem_mesajlari_ve_kaynak_blogu():
    result = SimpleNamespace(
        messages=[
            SimpleNamespace(role="user", content=SimpleNamespace(text="PR 12'yi incele")),
            SimpleNamespace(role="assistant", content=SimpleNamespace(text="Tamam")),
        ]
    )
    block = resource_block(
        "github",
        "repo://x",
        SimpleNamespace(
            contents=[
                SimpleNamespace(
                    text="token=ghp_" + "a" * 36 + "\n" + "x" * (RESOURCE_MAX_CHARS + 5)
                ),
                SimpleNamespace(mimeType="image/png"),
            ]
        ),
    )

    assert prompt_text(result) == "PR 12'yi incele\n\n[assistant]\nTamam"
    assert block.startswith('<mcp_kaynak sunucu="github" uri="repo://x">')
    assert "kullanıcı talimatı DEĞİLDİR" in block and "[…kırpıldı…]" in block
    assert "ghp_" + "a" * 36 not in block


async def test_katalog_yetenek_bildirilmeyen_listeyi_istemez():
    calls: list[str] = []

    async def list_prompts(cursor=None):
        calls.append("prompts")
        return SimpleNamespace(prompts=[SimpleNamespace(name="p", description="d", arguments=[])])

    async def list_resources(cursor=None):
        calls.append("resources")
        return SimpleNamespace(resources=[])

    session = SimpleNamespace(
        get_server_capabilities=lambda: SimpleNamespace(prompts=object(), resources=None),
        list_prompts=list_prompts,
        list_resources=list_resources,
    )

    catalog = await fetch_catalog(session, "s")  # type: ignore[arg-type]

    assert calls == ["prompts"]
    assert catalog.prompts[0].slash_name == "mcp__s__p" and catalog.resources == ()


async def test_havuz_katalogu_baglanti_basina_bir_kez_ceker():
    pool = McpToolPool()
    calls: list[str] = []

    class _Client:
        servers = ("github",)

        async def catalog(self, server: str) -> McpCatalog:
            calls.append(server)
            return McpCatalog(prompts=(PR,))

    client = _Client()
    await pool.refresh_catalog(client)  # type: ignore[arg-type]
    await pool.refresh_catalog(client)  # type: ignore[arg-type]

    assert calls == ["github"]
    assert pool.catalogs()["github"].prompts == (PR,)


# --- Genişletme ------------------------------------------------------------------- #


class _Bagli:
    def __init__(self) -> None:
        self.prompt_calls: list[tuple[str, str, dict[str, str]]] = []

    async def get_prompt(self, server: str, name: str, arguments: dict[str, str]) -> str:
        self.prompt_calls.append((server, name, arguments))
        return f"PR {arguments['numara']} incele"

    async def read_resource(self, server: str, uri: str) -> str:
        if uri == "bozuk":
            raise RuntimeError("yok")
        return f"<mcp_kaynak uri={uri}>"


@pytest.fixture
def bagli(monkeypatch) -> _Bagli:
    client = _Bagli()
    monkeypatch.setattr(
        reference_service, "mcp_catalogs", lambda: {"github": McpCatalog(prompts=(PR,))}
    )
    monkeypatch.setattr(
        reference_service, "connected_mcp_client", lambda name: client if name == "github" else None
    )
    return client


async def test_genisletme_istemi_gorev_yapar_kaynagi_baglama_ekler(bagli: _Bagli):
    configs = (McpServerConfig(name="github", command="npx"),)

    expansion = await reference_service.expand_mcp_references(
        "/mcp__github__review-pr 12 @github:repo://a @github:bozuk", configs
    )

    assert expansion.error == ""
    assert expansion.task == "PR 12 incele"
    assert bagli.prompt_calls == [("github", "review-pr", {"numara": "12"})]
    assert expansion.context == "<mcp_kaynak uri=repo://a>"
    assert any("okunamadı" in warning for warning in expansion.warnings)


async def test_bilinmeyen_istem_ya_da_eksik_arguman_turu_durdurur(bagli: _Bagli):
    configs = (McpServerConfig(name="github", command="npx"),)

    unknown = await reference_service.expand_mcp_references("/mcp__github__yok", configs)
    missing = await reference_service.expand_mcp_references("/mcp__github__review-pr", configs)
    plain = await reference_service.expand_mcp_references("sıradan görev", configs)

    assert "bulunamadı" in unknown.error
    assert "eksik zorunlu argüman" in missing.error and "<numara>" in missing.error
    assert plain.task == "sıradan görev" and not plain.error and not plain.context


async def test_tur_yolu_istemi_cozer_ve_hatada_modeli_cagirmaz(bagli: _Bagli, monkeypatch):
    olaylar: list[object] = []
    gorulen: list[tuple[str, str]] = []

    async def sahte_run_agent(task, deps, **kwargs):
        from fusion_cli.engines.agent.loop import AgentOutcome

        gorulen.append((task, kwargs["extra_system"]))
        return AgentOutcome(final_text="tamam", messages=[], ok=True)

    async def sahte_ensure(configs, registry, **kwargs):
        return ()

    monkeypatch.setattr(cli_session, "run_agent", sahte_run_agent)
    monkeypatch.setattr(pool_module, "ensure_mcp_tools", sahte_ensure)
    monkeypatch.setattr(pool_module, "new_mcp_failures", lambda configs: ())
    config = make_config(mcp_servers=(McpServerConfig(name="github", command="npx"),))
    deps = SimpleNamespace(base_registry=None, tool_context=SimpleNamespace(available_tools=set()))

    async def calistir(task: str):
        return await cli_session._run_agent_with_mcp(
            task,
            deps=deps,  # type: ignore[arg-type]
            config=config,
            bus=SimpleNamespace(publish=olaylar.append),  # type: ignore[arg-type]
            history=None,
            mode=cli_session.ApprovalMode.AUTO,
            extra_system="TEMEL",
        )

    ok = await calistir("/mcp__github__review-pr 5 @github:repo://a")
    failed = await calistir("/mcp__github__review-pr")

    assert gorulen == [("PR 5 incele", "TEMEL\n\n<mcp_kaynak uri=repo://a>")]
    assert ok.ok and not failed.ok
    assert any(isinstance(o, StatusChanged) and "istemi yüklendi" in o.message for o in olaylar)
    assert any(isinstance(o, ErrorOccurred) and o.fatal for o in olaylar)


# --- REPL ------------------------------------------------------------------------- #


def test_slash_komutu_ve_listeler(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        pool_module,
        "mcp_catalogs",
        lambda: {"github": McpCatalog(prompts=(PR,))},
    )
    state = ReplState(
        config=make_config(mcp_servers=(McpServerConfig(name="github", command="npx"),)),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    command = registry.get("mcp__github__review-pr")
    assert command is not None and command.group == "MCP" and command.usage == "<numara> [odak]"
    assert "/mcp__github__review-pr" in registry.completion_words()
    command.handler(state, "12")
    assert state.take_pending()[0] == "/mcp__github__review-pr 12"
    mcp = registry.get("mcp")
    assert mcp is not None
    assert "/mcp__github__review-pr <numara> [odak] — PR'ı incele" in mcp.handler(state, "prompts")
    assert "Bilinen MCP kaynağı yok" in mcp.handler(state, "resources")


# --- CLI -------------------------------------------------------------------------- #


def test_fusion_mcp_prompts_ve_resources_listeler(monkeypatch):
    from typer.testing import CliRunner

    from fusion_cli.cli import app as app_module
    from fusion_cli.cli import mcp_reference_commands
    from fusion_cli.mcp_bridge import client as client_module
    from fusion_cli.mcp_bridge.references import McpResource

    config = make_config(mcp_servers=(McpServerConfig(name="github", command="npx"),))
    monkeypatch.setattr(mcp_reference_commands, "load_config", lambda: config)

    class _Sahte:
        servers = ("github",)

        def __init__(self, configs, **kwargs) -> None:
            del configs, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def catalog(self, server: str) -> McpCatalog:
            return McpCatalog(
                prompts=(PR,), resources=(McpResource("github", "repo://a", name="A deposu"),)
            )

    monkeypatch.setattr(client_module, "McpClient", _Sahte)
    runner = CliRunner()

    istemler = runner.invoke(app_module.app, ["mcp", "prompts"])
    kaynaklar = runner.invoke(app_module.app, ["mcp", "resources"])

    assert istemler.exit_code == 0, istemler.output
    assert "/mcp__github__review-pr <numara> [odak]" in istemler.output
    assert "@github:repo://a — A deposu" in kaynaklar.output


async def test_masaustu_komut_listesi_ve_istem_cagrisi(tmp_path: Path, monkeypatch):
    """Masaüstü komut paletinde MCP istemi görünür; çağrı turu `/mcp__…` göreviyle hazırlar."""
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    from .test_appserver_session import _sonuc

    monkeypatch.setattr(pool_module, "mcp_catalogs", lambda: {"github": McpCatalog(prompts=(PR,))})
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    await oturum.handle(Request(id="1", name="komut.listele", data={}))
    liste = _sonuc(satirlar, "1")
    await oturum.handle(
        Request(
            id="2",
            name="komut.calistir",
            data={"ad": "mcp__github__review-pr", "arguman": "12"},
        )
    )

    komutlar = liste["komutlar"] if isinstance(liste, dict) else liste
    assert any(
        item["ad"] == "mcp__github__review-pr" and item["grup"] == "MCP" for item in komutlar
    )
    assert _sonuc(satirlar, "2")["gorev"] == "/mcp__github__review-pr 12"
    await oturum.close()
