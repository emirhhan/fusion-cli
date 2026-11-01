"""Aynı fiziksel kaynak kimliği ve kayıpsız JSON metadata regresyonları."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.tools.agent_catalog_launch import session_agents_from_json
from fusion_cli.tools.capabilities import Capability, CapabilityRegistry


def _agent(root: Path, body: str = "Talimat") -> Path:
    path = root / ".claude/agents/denetci.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: denetci\ndescription: Denetim\n---\n{body}", encoding="utf-8")
    return path


@pytest.mark.parametrize("same_home", [False, True])
def test_ayni_fiziksel_ek_kok_onceki_kaynak_takma_adini_korur(
    tmp_path: Path, same_home: bool
) -> None:
    root = tmp_path / "proje"
    _agent(root)
    home = root if same_home else tmp_path / "ev"
    expected = "claude+proje+ek-kok" if same_home else "proje+ek-kok"

    agent = CapabilityRegistry(home, root, extra_roots=(root, root)).get_agent("denetci")

    assert agent is not None and agent.source == expected


def test_onceki_nitelikli_kapatma_ayni_fiziksel_ek_koktan_geri_acilmaz(tmp_path: Path) -> None:
    root = tmp_path / "proje"
    path = _agent(root)
    persisted = Capability("denetci", "Denetim", path, "proje+ek-kok").qualified_name
    registry = CapabilityRegistry(
        tmp_path / "ev", root, extra_roots=(root,), disabled_agents=frozenset({persisted})
    )

    assert registry.get_agent("denetci") is None
    assert registry.get_agent(persisted) is None


def test_ayri_dosya_ek_kok_onceligi_ve_ozel_cli_govdesi_alias_sayilmaz(tmp_path: Path) -> None:
    root, extra = tmp_path / "proje", tmp_path / "ek"
    path = _agent(root, "Proje")
    _agent(extra, "Ek proje")
    inline = Capability("denetci", "CLI", path, "cli", inline_prompt="Dosyasız CLI")
    registry = CapabilityRegistry(tmp_path / "ev", root, extra_roots=(extra,))
    session_registry = CapabilityRegistry(tmp_path / "ev", root, session_agents=(inline,))

    project = registry.get_agent("denetci")
    session = session_registry.get_agent("denetci")
    assert project is not None and project.path == path and project.source == "proje"
    assert (
        session is not None and session.source == "cli" and session.inline_prompt == "Dosyasız CLI"
    )


@pytest.mark.parametrize(
    "description",
    [
        "İlk satır\nİkinci satır",
        "Önce 'alıntıyı' denetle: sonra devam et",
        "Son satır\n",
    ],
)
def test_cli_json_aciklamasi_yonlendirme_oncesi_birebir_korunur(
    tmp_path: Path, description: str
) -> None:
    raw = json.dumps({"denetci": {"prompt": "", "description": description}})

    agent = session_agents_from_json(raw, root=tmp_path)[0]

    assert agent.description == description


def test_tum_metinsel_json_metadata_tek_normalizer_uzerinde_kayipsiz_korunur(
    tmp_path: Path,
) -> None:
    text = "Önce 'alıntıyı' denetle: sonra\nİkinci satır\n"
    raw = json.dumps(
        {
            "denetci": {
                "prompt": text,
                "description": text,
                "initialPrompt": text,
                "model": "sağlayıcı/'özel':model",
                "maxTurns": 3,
                "tools": ["Read", "Bash"],
                "disallowedTools": ["Bash(git push *)"],
                "omitClaudeMd": True,
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": text,
                                    "timeout": 5,
                                }
                            ],
                        }
                    ]
                },
                "mcpServers": [{"sunucu": {"command": "python", "args": [text]}}],
            }
        }
    )

    agent = session_agents_from_json(raw, root=tmp_path)[0]

    assert (
        agent.inline_prompt == text and agent.description == text and agent.initial_prompt == text
    )
    assert agent.model == "sağlayıcı/'özel':model"
    assert agent.tools == ("Read", "Bash") and agent.disallowed_tools == ("Bash",)
    assert agent.max_turns == 3 and agent.omit_claude_md
    assert agent.hook_definitions.commands[0].command == text
    assert agent.inline_mcp_servers[0].args == (text,)


def test_generic_katalog_repr_yurutme_metadatasinin_sirlarini_gostermez(tmp_path: Path) -> None:
    raw = json.dumps(
        {
            "denetci": {
                "prompt": "",
                "hooks": {
                    "PreToolUse": [
                        {
                            "hooks": [
                                {
                                    "type": "http",
                                    "url": "https://ornek.invalid/hook",
                                    "headers": {"Authorization": "TEST-HOOK-SECRET"},
                                }
                            ]
                        }
                    ]
                },
                "mcpServers": [
                    {
                        "sunucu": {
                            "command": "python",
                            "args": ["TEST-MCP-ARG-SECRET"],
                            "env": {"KEY": "TEST-MCP-ENV-SECRET"},
                        }
                    }
                ],
            }
        }
    )

    agent = session_agents_from_json(raw, root=tmp_path)[0]

    rendered = repr(agent)
    assert "TEST-HOOK-SECRET" not in rendered
    assert "TEST-MCP-ARG-SECRET" not in rendered
    assert "TEST-MCP-ENV-SECRET" not in rendered
    assert agent.hook_definitions.commands[0].headers == (("Authorization", "TEST-HOOK-SECRET"),)
    assert agent.inline_mcp_servers[0].args == ("TEST-MCP-ARG-SECRET",)
    assert agent.inline_mcp_servers[0].env_literals == (("KEY", "TEST-MCP-ENV-SECRET"),)
