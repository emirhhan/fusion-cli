"""Eklenti becerilerinde `!`komut`` dinamik bağlamı (Claude Code skills, #386).

Claude: eklenti becerileri beceri olarak yüklenir ve dinamik bağlam çalışır. Fusion'da eklenti
becerisi kullanıcının kendi becerisiyle aynı kipte (auto/acceptEdits/bypass) ve aynı riskli komut
denetimiyle koşar; plan/security kipinde koşmaz.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fusion_cli.cli.repl.skill_commands import shell_context_policy
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.tools.capabilities import Capability


def _skill(source: str) -> Capability:
    return Capability(name="rapor:ozet", description="", path=Path("/yok/SKILL.md"), source=source)


@pytest.mark.parametrize("source", ["eklenti", "claude-plugin"])
def test_eklenti_becerisi_izinli_kipte_tam_yetkili_kosar(tmp_path, source):
    state = SimpleNamespace(approval=ApprovalMode.AUTO, root=tmp_path)
    assert shell_context_policy(state, _skill(source)) == (True, False)


@pytest.mark.parametrize("source", ["eklenti", "claude-plugin"])
def test_eklenti_becerisi_sorulan_kipte_kosmaz(tmp_path, source):
    state = SimpleNamespace(approval=ApprovalMode.SECURITY, root=tmp_path)
    assert shell_context_policy(state, _skill(source)) == (False, False)


def _repo_plugin(tmp_path: Path) -> tuple[Path, Path]:
    """Deponun kendi pazarı (extraKnownMarketplaces benzeri) ve projede açılan eklenti."""
    import json

    from fusion_cli.tools import plugin_install

    project = tmp_path / "proje"
    market = project / "tools" / "mk"
    plugin = market / "plugins" / "p"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "p"}), "utf-8")
    skill = plugin / "skills" / "ozet" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: ozet\ndescription: Ö\n---\n!`date`\n", "utf-8")
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {"name": "mk", "owner": {"name": "R"}, "plugins": [{"name": "p", "source": "./plugins/p"}]}
        ),
        "utf-8",
    )
    plugin_install.add_marketplace(str(market))
    (project / ".claude" / "settings.json").parent.mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"p@mk": True}}), "utf-8"
    )
    return project, skill


def test_projeden_acilan_eklenti_becerisi_proje_becerisi_gibi_salt_okur(tmp_path):
    from fusion_cli.config import trust

    project, skill = _repo_plugin(tmp_path)
    trust.trust_project(project)
    state = SimpleNamespace(approval=ApprovalMode.BYPASS, root=project)
    capability = Capability(name="p:ozet", description="", path=skill, source="eklenti")

    assert shell_context_policy(state, capability) == (True, True)
