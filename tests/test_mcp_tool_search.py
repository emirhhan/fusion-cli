"""MCP araç araması (#258): Claude Code `ENABLE_TOOL_SEARCH`, `ToolSearch`, `alwaysLoad`.

Belge: code.claude.com/docs/en/mcp "Scale with MCP tool search", "Configure tool search".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.config.models import McpServerConfig
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.tool_search_bridge import McpToolSearch, is_deferrable
from fusion_cli.mcp_bridge.types import RemoteTool
from fusion_cli.tools import ToolRegistry
from fusion_cli.tools.tool_search import (
    TOOL_SEARCH,
    ToolSearchMode,
    tool_search_mode,
    visible_tool_names,
)


@pytest.mark.parametrize(
    ("env", "beklenen"),
    [
        ({}, ToolSearchMode(True)),
        ({"ENABLE_TOOL_SEARCH": "true"}, ToolSearchMode(True)),
        ({"ENABLE_TOOL_SEARCH": "false"}, ToolSearchMode(False)),
        ({"ENABLE_TOOL_SEARCH": "auto"}, ToolSearchMode(True, 10)),
        ({"ENABLE_TOOL_SEARCH": "auto:5"}, ToolSearchMode(True, 5)),
        (
            {"CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1", "ENABLE_TOOL_SEARCH": "true"},
            ToolSearchMode(False),
        ),
    ],
)
def test_enable_tool_search_degerleri(env, beklenen):
    assert tool_search_mode(env) == beklenen


def test_always_load_sunucu_ayari_arac_isaretini_ezer():
    isaretli = RemoteTool(server="s", name="a", description="", always_load=True)
    duz = RemoteTool(server="s", name="b", description="")

    assert not is_deferrable(McpServerConfig("s"), isaretli)
    assert is_deferrable(McpServerConfig("s"), duz)
    assert not is_deferrable(McpServerConfig("s", always_load=True), duz)
    assert is_deferrable(McpServerConfig("s", always_load=False), isaretli)


class _Arac:
    def __init__(self, name: str, description: str = "", meta: dict | None = None) -> None:
        self.name = name
        self.description = description
        self.inputSchema: dict[str, object] = {"type": "object", "properties": {}}
        self.annotations = None
        self.meta = meta


class _Oturum:
    def __init__(self, *tools: _Arac) -> None:
        self._tools = tools

    async def list_tools(self, cursor=None):
        return SimpleNamespace(tools=list(self._tools), nextCursor=None)


async def _defter(mode: ToolSearchMode, *tools: _Arac, config: McpServerConfig | None = None):
    config = config or McpServerConfig("gh")
    client = McpClient((config,))
    client._tool_search = McpToolSearch(mode)
    client._sessions[config.name] = _Oturum(*tools)
    registry = ToolRegistry()
    await client.register_into(registry)
    return registry


def _pencere() -> int:
    return 200_000


async def _ara(registry: ToolRegistry, args: dict):
    return await registry.get(TOOL_SEARCH).run(args, None)


def _gorunen(registry: ToolRegistry, pencere=_pencere) -> set[str]:
    names = visible_tool_names(None, registry, pencere)
    return set(registry.names()) if names is None else names


async def test_varsayilan_kipte_mcp_semasi_ertelenir_toolsearch_ile_yuklenir():
    registry = await _defter(
        ToolSearchMode(True),
        _Arac("create_issue", "Opens a GitHub issue"),
        _Arac("list_prs", "Lists pull requests"),
    )

    gorunen = visible_tool_names(None, registry, _pencere)
    assert gorunen is not None
    assert TOOL_SEARCH in gorunen and "mcp__gh__create_issue" not in gorunen
    assert "mcp__gh__create_issue" in registry.get(TOOL_SEARCH).description

    sonuc = await _ara(registry, {"query": "select:mcp__gh__create_issue"})
    assert sonuc.ok and "<functions>" in sonuc.output and "Opens a GitHub issue" in sonuc.output

    gorunen = visible_tool_names(None, registry, _pencere)
    assert "mcp__gh__create_issue" in gorunen and "mcp__gh__list_prs" not in gorunen


async def test_anahtar_sozcuk_ve_arti_sarti():
    registry = await _defter(
        ToolSearchMode(True),
        _Arac("create_issue", "Opens a GitHub issue"),
        _Arac("list_prs", "Lists pull requests"),
    )

    sonuc = await _ara(registry, {"query": "pull requests"})
    assert "mcp__gh__list_prs" in sonuc.output and "create_issue" not in sonuc.output
    sonuc = await _ara(registry, {"query": "+issue"})
    assert "mcp__gh__create_issue" in sonuc.output and "list_prs" not in sonuc.output


async def test_false_kipinde_toolsearch_yok_hepsi_bastan():
    registry = await _defter(ToolSearchMode(False), _Arac("create_issue"))

    assert registry.get(TOOL_SEARCH) is None
    assert visible_tool_names(None, registry, _pencere) is None


async def test_arac_isareti_alwaysload_bastan_yuklenir():
    registry = await _defter(
        ToolSearchMode(True),
        _Arac("search", meta={"anthropic/alwaysLoad": True}),
        _Arac("other"),
    )

    gorunen = visible_tool_names(None, registry, _pencere)
    assert "mcp__gh__search" in gorunen and "mcp__gh__other" not in gorunen


async def test_sunucu_alwaysload_true_ise_toolsearch_kurulmaz():
    registry = await _defter(
        ToolSearchMode(True), _Arac("a"), config=McpServerConfig("gh", always_load=True)
    )

    assert registry.get(TOOL_SEARCH) is None


async def test_toolsearch_reddedilmisse_araclar_bastan_gider():
    registry = await _defter(ToolSearchMode(True), _Arac("a"))
    izinli = set(registry.names()) - {TOOL_SEARCH}

    assert visible_tool_names(izinli, registry, _pencere) == izinli


async def test_auto_esik_altinda_bastan_ustunde_ertelenir():
    registry = await _defter(ToolSearchMode(True, 10), _Arac("a"), _Arac("b"))

    assert "mcp__gh__a" in _gorunen(registry)
    assert "mcp__gh__a" not in _gorunen(registry, lambda: 100)
    # Eşik bir kez aşıldı: pencere büyüse de arama açık kalır.
    assert "mcp__gh__a" not in _gorunen(registry)


async def test_ertelenen_aciklama_16384_bastan_yuklenen_4096(monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH", raising=False)
    uzun = "x" * 20_000
    registry = await _defter(
        ToolSearchMode(True),
        _Arac("ertelenen", uzun),
        _Arac("bastan", uzun, meta={"anthropic/alwaysLoad": True}),
    )

    assert len(registry.get("mcp__gh__ertelenen").description) == 16_384
    assert len(registry.get("mcp__gh__bastan").description) == 4_096


async def test_motor_ertelenen_semayi_toolsearch_sonrasi_ayni_turda_sunar(monkeypatch, tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent

    from .fakes import (
        AlwaysApprove,
        RecordingSink,
        ScriptedProvider,
        make_config,
        model_result,
        tool_call,
    )

    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call(TOOL_SEARCH, query="select:mcp__gh__create_issue")]),
            model_result("Araç yüklendi; işi bitirdim ve sonucu doğruladım, ayrıntı yukarıda."),
        ]
    )
    monkeypatch.setattr(agent_loop, "build_provider", lambda *a, **k: provider)
    sink = RecordingSink()

    class _Pub:
        def publish(self, event):
            sink.handle(event)

    deps = AgentDeps(
        config=make_config(),
        publisher=_Pub(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    # Sahte sağlayıcının modeli Claude değil: erteleme açıkça açılır (ENABLE_TOOL_SEARCH=true).
    kaynak = await _defter(
        ToolSearchMode(True, explicit=True), _Arac("create_issue", "Opens a GitHub issue")
    )
    for tool in kaynak:
        deps.base_registry.register_or_replace(tool)

    await run_agent("bir issue aç", deps, verify=False, self_review=False)

    def _adlar(istek):
        return {schema["function"]["name"] for schema in istek}

    assert TOOL_SEARCH in _adlar(provider.seen_requests[0])
    assert "mcp__gh__create_issue" not in _adlar(provider.seen_requests[0])
    assert "mcp__gh__create_issue" in _adlar(provider.seen_requests[1])


def _model_gorunen(registry: ToolRegistry, model: str) -> set[str]:
    names = visible_tool_names(None, registry, _pencere, model=model)
    return set(registry.names()) if names is None else names


async def test_varsayilan_kipte_claude_disi_modelde_erteleme_yok():
    """Claude: araç araması desteklemeyen model araçları baştan yükler (Fusion: Claude dışı)."""
    registry = await _defter(tool_search_mode({}), _Arac("create_issue", "Opens"))

    gorunen = _model_gorunen(registry, "gemini/gemini-2.5-flash")

    assert "mcp__gh__create_issue" in gorunen and TOOL_SEARCH not in gorunen


async def test_varsayilan_kipte_claude_4_modelinde_ertelenir():
    registry = await _defter(tool_search_mode({}), _Arac("create_issue", "Opens"))

    gorunen = _model_gorunen(registry, "anthropic/claude-sonnet-4-5")

    assert "mcp__gh__create_issue" not in gorunen and TOOL_SEARCH in gorunen


async def test_eski_claude_modelinde_true_bile_ertelemez():
    """Claude: eski modeller araçları baştan yükler; `ENABLE_TOOL_SEARCH=true` bunu ezmez."""
    mode = tool_search_mode({"ENABLE_TOOL_SEARCH": "true"})
    registry = await _defter(mode, _Arac("create_issue", "Opens"))

    gorunen = _model_gorunen(registry, "anthropic/claude-3-5-haiku-20241022")

    assert "mcp__gh__create_issue" in gorunen and TOOL_SEARCH not in gorunen


async def test_acikca_acilan_aramada_claude_disi_model_de_erteler():
    mode = tool_search_mode({"ENABLE_TOOL_SEARCH": "true"})
    registry = await _defter(mode, _Arac("create_issue", "Opens"))

    gorunen = _model_gorunen(registry, "gemini/gemini-2.5-flash")

    assert "mcp__gh__create_issue" not in gorunen and TOOL_SEARCH in gorunen
