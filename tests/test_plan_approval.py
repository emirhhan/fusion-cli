"""Plan kipinin onay politikası Claude Code ile birebir (#52).

Kaynak: https://code.claude.com/docs/en/permission-modes (Analyze before you edit with plan
mode; Protected paths).
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.config import trust
from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.core.tools import Tool
from fusion_cli.engines.agent.approval import (
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)

from .fakes import AlwaysApprove, AlwaysReject


def _arac(ad: str = "run_shell") -> Tool:
    return Tool(name=ad, description="", parameters={}, run=lambda a, c: None, mutating=True)


def _hafiza(*, bypass: bool = False) -> ApprovalMemory:
    hafiza = ApprovalMemory()
    hafiza.plan_bypass = bypass
    return hafiza


async def _karar(komut, kok, *, prompter=None, rules=None, **kw):
    politika = build_policy(ApprovalMode.PLAN, prompter or AlwaysReject(), _hafiza(**kw))
    return await politika.decide(build_request(_arac(), {"command": komut}, root=kok, rules=rules))


async def test_okuma_disi_komut_sorulur(tmp_path):
    assert await _karar("pytest -q", tmp_path) is Decision.DENIED
    sonuc = await _karar("pytest -q", tmp_path, prompter=AlwaysApprove())
    assert sonuc is Decision.ALLOW
    assert await _karar("git log", tmp_path) is Decision.ALLOW


async def test_ask_kurali_plan_kipinde_sorulur(tmp_path):
    kural = parse_rule("Bash(git log *)", PermissionDecision.ASK, source="test")
    kume = PermissionRuleSet(rules=(kural,))
    sonuc = await _karar("git log -1", tmp_path, prompter=AlwaysApprove(), rules=kume)
    assert sonuc is Decision.ALLOW
    assert await _karar("git log -1", tmp_path, rules=kume) is Decision.DENIED


async def test_dosya_duzenlemesi_engellenir(tmp_path):
    politika = build_policy(ApprovalMode.PLAN, AlwaysApprove(), _hafiza())
    istek = build_request(_arac("write_file"), {"path": "a.txt"}, root=tmp_path)
    assert await politika.decide(istek) is Decision.BLOCKED


async def test_bypass_kullanilabilir_oturumda_plan_sormaz(tmp_path):
    assert await _karar("git push", tmp_path, bypass=True) is Decision.ALLOW
    politika = build_policy(ApprovalMode.PLAN, AlwaysReject(), _hafiza(bypass=True))
    istek = build_request(_arac("write_file"), {"path": "a.txt"}, root=tmp_path)
    assert await politika.decide(istek) is Decision.ALLOW


def test_repl_durumu_plan_bayraklarini_kurar(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from fusion_cli.cli.repl.state import _apply_plan_policy

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(trust, "trust_store_file", lambda: tmp_path / "guven.json")
    durum = SimpleNamespace(root=tmp_path, approval_memory=ApprovalMemory(), bypass_available=True)
    _apply_plan_policy(durum)
    assert durum.approval_memory.plan_bypass is True
