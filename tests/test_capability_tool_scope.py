"""Ajanın araç kısıtı sessizce "tam yetki"ye dönüşemez (T1-13).

Ölçüldü (29 Ekim): `tools:` + blok liste (`  - Read`) satırı boş değer üretip `()` →
`map_tools(()) is None` (tam set) oluyordu; TOML ajanında araç alanı hiç okunmuyordu.
"""

from __future__ import annotations

from fusion_cli.tools.capabilities import (
    CapabilityRegistry,
    map_tools,
    parse_frontmatter,
)

BLOK_LISTE = """---
name: salt-okur
description: yalnız okur
tools:
  - Read
  - Grep
---
govde
"""


def test_blok_liste_biciminde_tools_ayristirilir():
    assert parse_frontmatter(BLOK_LISTE)["tools"] == ("Read", "Grep")


def test_blok_liste_kisitli_arac_setine_cevrilir():
    allowed = map_tools(parse_frontmatter(BLOK_LISTE)["tools"])  # type: ignore[arg-type]

    assert allowed is not None
    assert "read_file" in allowed
    assert "run_shell" not in allowed and "write_file" not in allowed


def test_blok_listede_tirnak_ve_yorum_soyulur():
    metin = "---\nname: a\ntools:\n  - 'Read'   # okuma\n  - \"Bash\"\n---\nx"

    assert parse_frontmatter(metin)["tools"] == ("Read", "Bash")


def test_tools_anahtari_var_ama_bos_ise_hic_arac_yok_sayilir():
    for metin in ("---\nname: a\ntools:\n---\nx", "---\nname: a\ntools: []\n---\nx"):
        araclar = parse_frontmatter(metin)["tools"]
        assert map_tools(araclar) == set(), metin  # type: ignore[arg-type]


def test_tools_anahtari_yoksa_tam_yetki_korunur():
    assert "tools" not in parse_frontmatter("---\nname: a\n---\nx")
    assert map_tools(()) is None
    assert map_tools(("*",)) is None


def test_ajan_kaydinda_blok_liste_kisitli_gelir(tmp_path):
    klasor = tmp_path / ".claude" / "agents"
    klasor.mkdir(parents=True)
    (klasor / "salt-okur.md").write_text(BLOK_LISTE, encoding="utf-8")

    ajan = CapabilityRegistry(tmp_path, tmp_path).get_agent("salt-okur")

    assert ajan is not None
    allowed = map_tools(ajan.tools)
    assert allowed is not None and "run_shell" not in allowed


def _toml(tmp_path, govde: str):
    klasor = tmp_path / ".codex" / "agents"
    klasor.mkdir(parents=True, exist_ok=True)
    (klasor / "ajan.toml").write_text(govde, encoding="utf-8")
    return CapabilityRegistry(tmp_path, tmp_path).get_agent("ajan")


def test_toml_ajaninda_read_only_sandbox_arac_kisitina_donusur(tmp_path):
    ajan = _toml(tmp_path, 'name = "ajan"\nsandbox_mode = "read-only"\n')

    assert ajan is not None
    allowed = map_tools(ajan.tools)
    assert allowed is not None
    assert "read_file" in allowed and "run_shell" not in allowed and "write_file" not in allowed


def test_toml_ajaninda_tools_listesi_okunur(tmp_path):
    ajan = _toml(tmp_path, 'name = "ajan"\ntools = ["Read", "Grep"]\n')

    assert ajan is not None
    assert ajan.tools == ("Read", "Grep")


def test_toml_ajani_kisit_bildirmezse_tam_yetki_kalir(tmp_path):
    ajan = _toml(tmp_path, 'name = "ajan"\nsandbox_mode = "workspace-write"\n')

    assert ajan is not None
    assert map_tools(ajan.tools) is None


def test_capability_genislemesi_ilgi_seciminde_izin_kapsamini_asmaz():
    from fusion_cli.core.tools import Tool, ToolResult
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _permitted
    from fusion_cli.engines.agent.tool_surface import narrow_to_compact_surface
    from fusion_cli.tools import build_registry
    from fusion_cli.tools.capabilities import expand_tool_patterns

    registry = build_registry()
    for name in ("jira__read", "jira__write", "other__read"):
        registry.register_or_replace(
            Tool(
                name=name,
                description="jira issue read write",
                parameters={},
                run=lambda args, context: ToolResult("ok"),
            )
        )
    expanded = expand_tool_patterns({"jira__*", "read_file"}, registry.names())
    policy = ExecutionPolicy(
        is_web=False, allowed_tool_names=frozenset({"jira__read", "read_file"})
    )
    permitted = _permitted(expanded, registry, policy)
    selected = narrow_to_compact_surface(
        permitted,
        registry,
        max_external_tools=1,
        task_kinds=(),
        explicit=expanded,
        external_tool_selection="relevance",
        task="jira issue write",
    )
    assert selected == {"jira__read", "read_file"}


def test_profil_genislemesi_ilgi_seciminde_korunur():
    from fusion_cli.engines.agent.tool_profiles import WIDENED_KIND
    from fusion_cli.engines.agent.tool_surface import narrow_to_compact_surface
    from fusion_cli.tools import build_registry

    registry = build_registry()
    arguments = {
        "max_external_tools": 1,
        "explicit": (),
        "profiles": ("kod",),
        "external_tool_selection": "relevance",
        "task": "browser tabs",
    }
    initial = narrow_to_compact_surface(set(registry.names()), registry, task_kinds=(), **arguments)
    widened = narrow_to_compact_surface(
        set(registry.names()), registry, task_kinds=(WIDENED_KIND,), **arguments
    )
    assert "browser_tabs_list" not in initial
    assert "browser_tabs_list" in widened
