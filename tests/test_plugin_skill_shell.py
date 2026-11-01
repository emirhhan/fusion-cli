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
