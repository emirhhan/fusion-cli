"""MCP istemleri Claude Code gibi: `/sunucu:istem (MCP)`, boşlukla konumsal argüman (#268).

Belge (code.claude.com/docs/en/mcp, "Use MCP prompts as commands"): menüde
`/servername:promptname (MCP)`; `/mcp__servername__promptname` de çalışır; argümanlar
boşlukla bölünür, her argüman tek token; yalnız sunucu adındaki geçersiz karakterler `_` olur;
`anthropic-skills` adlı sunucunun istemleri görünmez.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.models import McpServerConfig
from fusion_cli.mcp_bridge import pool as pool_module
from fusion_cli.mcp_bridge.references import (
    McpCatalog,
    McpPrompt,
    McpPromptArgument,
    bind_arguments,
    find_prompt,
    prompt_text,
    visible_prompts,
)
from fusion_cli.memory.factory import null_memory

from .fakes import make_config

PR = McpPrompt(
    server="github",
    name="review-pr",
    description="PR'ı incele",
    arguments=(McpPromptArgument("numara", required=True), McpPromptArgument("odak")),
)
GIZLI = McpPrompt(server="anthropic-skills", name="ozet")


def test_yalniz_sunucu_adi_normallesir_istem_adi_bildirildigi_gibi():
    prompt = McpPrompt("my server", "a.b/c")

    assert prompt.slash_name == "mcp__my_server__a.b/c"
    assert prompt.display_name == "my server:a.b/c"


def test_argumanlar_yalniz_bosluktan_konumsal_bolunur():
    assert bind_arguments(PR, "12 güvenlik") == ({"numara": "12", "odak": "güvenlik"}, "")
    # Tırnak gruplamaz, `ad=değer` bağlamaz: her token sırayla bir argüman.
    assert bind_arguments(PR, 'odak=x "a b"') == ({"numara": "odak=x", "odak": '"a'}, "")
    assert bind_arguments(PR, r"C:\Users\x\a.txt") == ({"numara": r"C:\Users\x\a.txt"}, "")
    assert "eksik zorunlu argüman: numara" in bind_arguments(PR, "")[1]


def test_anthropic_skills_istemleri_gizli_ve_cozulmez():
    assert visible_prompts((PR, GIZLI)) == (PR,)
    assert find_prompt((PR, GIZLI), GIZLI.slash_name) is None
    assert find_prompt((PR, GIZLI), "mcp__github__review-pr") is PR


def test_istem_metni_kirpilmaz():
    long_text = "y" * 60_000
    result = SimpleNamespace(
        messages=[SimpleNamespace(role="user", content=SimpleNamespace(text=long_text))]
    )

    assert prompt_text(result) == long_text


def test_menude_sunucu_iki_nokta_istem_mcp_eki(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        pool_module, "mcp_catalogs", lambda: {"github": McpCatalog(prompts=(PR, GIZLI))}
    )
    state = ReplState(
        config=make_config(mcp_servers=(McpServerConfig(name="github", command="npx"),)),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    menu = registry.get("github:review-pr")
    typed = registry.get("mcp__github__review-pr")

    assert menu is not None and menu.summary.endswith("(MCP)")
    assert "/github:review-pr" in registry.completion_words()
    assert "/anthropic-skills:ozet" not in registry.completion_words()
    menu.handler(state, "12")
    assert state.take_pending()[0] == "/mcp__github__review-pr 12"
    assert typed is not None and typed.name == "github:review-pr"
