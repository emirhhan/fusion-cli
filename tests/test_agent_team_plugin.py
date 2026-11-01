"""#25: Claude'da olmayan Türkçe ekip rolleri yerleşik değil, isteğe bağlı `fusion-ekip` eklentisi.

Claude Code'un yerleşik ajanları: Explore, Plan, general-purpose, claude, statusline-setup,
claude-code-guide (https://code.claude.com/docs/en/sub-agents). Fusion'ın Türkçe ekibi
(mimar, kodcu, ...) pakete gömülü `fusion` pazarındaki `fusion-ekip` eklentisine taşındı.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from fusion_cli.engines.agent import team
from fusion_cli.tools import bundled_plugins, plugin_install
from fusion_cli.tools.capabilities import CLAUDE_BUILTIN_AGENTS, CapabilityRegistry

TEAM_ROLES = (
    "mimar",
    "kodcu",
    "tasarimci",
    "testci",
    "arastirmaci",
    "tarayici",
    "gorselci",
    "yonetmen",
)
CLAUDE_SIX = {
    "general-purpose",
    "explore",
    "plan",
    "claude",
    "statusline-setup",
    "claude-code-guide",
}


def _yes(_preview: object) -> bool:
    return True


@pytest.mark.parametrize("extra", [True, False])
def test_yerlesik_ajanlar_yalniz_claude_code_altilisidir(tmp_path: Path, extra: bool) -> None:
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path, extra_agent_sources=extra)

    builtins = {agent.name for agent in registry.agents() if agent.source == "fusion"}

    assert builtins == CLAUDE_SIX
    assert set(CLAUDE_BUILTIN_AGENTS) == CLAUDE_SIX
    assert not {agent.name for agent in registry.agents()} & set(TEAM_ROLES)


def test_spawn_agent_aciklamasi_turkce_ekip_adlarini_onermez() -> None:
    description = str(team._SUBTASK_PROPERTIES["uzman"]["description"])  # type: ignore[index]

    assert not any(role in description for role in TEAM_ROLES)
    assert "general-purpose" in description and "Explore" in description


def test_gomulu_pazar_kayitsiz_kesfedilir_ve_fusion_ekip_kurulur(tmp_path: Path) -> None:
    (entry,) = [item for item in plugin_install.browse() if item.entry.name == "fusion-ekip"]
    assert entry.marketplace == bundled_plugins.BUNDLED_MARKETPLACE
    assert plugin_install.browse(bundled_plugins.BUNDLED_MARKETPLACE)

    item = plugin_install.install_plugin("fusion-ekip", approve=_yes)
    assert item.record.marketplace == bundled_plugins.BUNDLED_MARKETPLACE

    registry = CapabilityRegistry(tmp_path / "ev", tmp_path)
    names = {agent.name for agent in registry.agents()}
    assert {f"fusion-ekip:{role}" for role in TEAM_ROLES} <= names
    kodcu = registry.get_agent("fusion-ekip:kodcu")
    assert kodcu is not None and kodcu.source == "eklenti"
    assert kodcu.color and kodcu.avatar == "kodcu" and kodcu.title == "Geliştirici"
    # Claude Code: eklenti ajanı tekse yalın adla da seçilir (`claude --agent kodcu`).
    assert registry.get_agent("kodcu") == kodcu


def test_eklenti_yokken_eski_rol_adi_bir_surum_takma_ad_olarak_uyarip_cozulur(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bundled_plugins.reset_warnings()
    registry = CapabilityRegistry(tmp_path / "ev", tmp_path)

    with caplog.at_level(logging.WARNING):
        first = registry.get_agent("kodcu")
        second = registry.get_agent("kodcu")

    assert first is not None and second is not None and first.name == "kodcu"
    assert "Sen ekibin geliştiricisisin" in first.path.read_text(encoding="utf-8")
    assert "kodcu" not in {agent.name for agent in registry.agents()}
    warnings = [r for r in caplog.records if "fusion-ekip" in r.getMessage()]
    assert len(warnings) == 1
    assert registry.get_agent("yok-boyle-bir-rol") is None


def test_eski_rol_adi_icin_kurulum_ipucu() -> None:
    assert "fusion eklenti kur fusion-ekip" in bundled_plugins.team_role_hint("kodcu")
    assert bundled_plugins.team_role_hint("denetci") == ""
