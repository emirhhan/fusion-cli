"""Allow kuralı Claude gibi deny → ask → allow sırasında çalışır (#84).

Kaynak: https://code.claude.com/docs/en/permissions#manage-permissions ;
https://code.claude.com/docs/en/permission-modes#protected-paths
Allow kuralı yalnız korumalı yolları ve kritik yol silmelerini açmaz; Fusion'ın sezgisel
yıkıcı komut sınıflandırması allow'un önüne geçmez. Kuralsız çağrıda sezgisel denetim sürer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRule, PermissionRuleSet
from fusion_cli.engines.agent.approval import (
    ApprovalMode,
    ApprovalRequest,
    Decision,
    build_policy,
    build_request,
)
from fusion_cli.tools.critical_paths import SKIP_CRITICAL_PROMPT_ENV


class _Soran:
    def __init__(self) -> None:
        self.sorulan: list[ApprovalRequest] = []

    async def confirm(self, request: ApprovalRequest) -> bool:
        self.sorulan.append(request)
        return False


class _Arac:
    name = "run_shell"
    effect = None
    effect_resolver = None
    scope_resolver = None
    mutating = True


@pytest.fixture
def kok(tmp_path, monkeypatch) -> Path:
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.delenv(SKIP_CRITICAL_PROMPT_ENV, raising=False)
    kok = tmp_path / "proje"
    kok.mkdir()
    return kok


def _kurallar(*allow: str) -> PermissionRuleSet:
    rules = []
    for item in allow:
        tool, _, rest = item.partition("(")
        rules.append(
            PermissionRule(tool, rest.rstrip(")") or None, PermissionDecision.ALLOW, "kullanici")
        )
    return PermissionRuleSet(tuple(rules))


def _istek(komut: str, kok: Path, rules: PermissionRuleSet) -> ApprovalRequest:
    from fusion_cli.core.tools import ToolEffect

    return build_request(
        _Arac(), {"command": komut}, effect=ToolEffect.LOCAL, root=kok, rules=rules
    )


@pytest.mark.parametrize(
    "kip",
    [ApprovalMode.SECURITY, ApprovalMode.ACCEPT_EDITS, ApprovalMode.AUTO, ApprovalMode.DONT_ASK],
)
@pytest.mark.parametrize(
    ("kural", "komut"),
    [
        ("Bash(git push *)", "git push --force origin main"),
        ("Bash(git reset *)", "git reset --hard"),
        ("Bash(chmod *)", "chmod -R 777 ."),
    ],
)
def test_allow_kurali_sezgisel_yikiciyi_acar(kok, kip, kural, komut):
    istek = _istek(komut, kok, _kurallar(kural))
    assert istek.danger is not None
    soran = _Soran()
    assert asyncio.run(build_policy(kip, soran).decide(istek)) is Decision.ALLOW
    assert soran.sorulan == []


@pytest.mark.parametrize(
    "kip", [ApprovalMode.SECURITY, ApprovalMode.ACCEPT_EDITS, ApprovalMode.AUTO]
)
def test_kuralsiz_yikici_komut_hala_sorulur(kok, kip):
    istek = _istek("git push --force origin main", kok, _kurallar())
    soran = _Soran()
    assert asyncio.run(build_policy(kip, soran).decide(istek)) is not Decision.ALLOW
    assert len(soran.sorulan) == 1


def test_allow_kurali_kritik_yol_silmesini_acmaz(kok):
    istek = _istek("rm -rf ~", kok, _kurallar("Bash(rm *)"))
    soran = _Soran()
    assert (
        asyncio.run(build_policy(ApprovalMode.ACCEPT_EDITS, soran).decide(istek))
        is not Decision.ALLOW
    )
    assert asyncio.run(build_policy(ApprovalMode.DONT_ASK, soran).decide(istek)) is Decision.BLOCKED


def test_allow_kurali_korumali_yolu_acmaz(kok):
    istek = _istek("rm .git/config", kok, _kurallar("Bash(rm *)"))
    assert istek.protected is not None
    soran = _Soran()
    assert (
        asyncio.run(build_policy(ApprovalMode.SECURITY, soran).decide(istek)) is not Decision.ALLOW
    )
    assert len(soran.sorulan) == 1
