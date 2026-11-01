"""WebFetch / WebSearch onayı Claude Code ile birebir (#55).

Kaynak: https://code.claude.com/docs/en/permissions#permission-system ;
https://code.claude.com/docs/en/tools-reference#webfetch-tool-behavior
"""

from __future__ import annotations

import pytest

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.engines.agent.approval import (
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    resolve_request,
)
from fusion_cli.engines.agent.permission_persist import rule_for_request
from fusion_cli.tools import build_registry

from .fakes import AlwaysReject

_REG = build_registry()


async def _karar(mod, arac, args, kok, rules=None):
    istek = await resolve_request(_REG.get(arac), args, root=kok, rules=rules)
    return await build_policy(mod, AlwaysReject(), ApprovalMemory()).decide(istek)


def test_web_araclari_onay_kapisina_girer():
    assert _REG.get("web_fetch").effect_resolver is not None
    assert _REG.get("web_search").effect_resolver is not None


@pytest.mark.parametrize(
    ("mod", "beklenen"),
    [
        (ApprovalMode.SECURITY, Decision.DENIED),
        (ApprovalMode.ACCEPT_EDITS, Decision.DENIED),
        (ApprovalMode.PLAN, Decision.DENIED),
        (ApprovalMode.AUTO, Decision.ALLOW),
        (ApprovalMode.BYPASS, Decision.ALLOW),
        (ApprovalMode.DONT_ASK, Decision.BLOCKED),
    ],
)
async def test_web_fetch_ve_search_kiplere_gore(tmp_path, mod, beklenen):
    url = {"url": "https://example.com/a"}
    assert await _karar(mod, "web_fetch", url, tmp_path) is beklenen
    assert await _karar(mod, "web_search", {"query": "x"}, tmp_path) is beklenen


@pytest.mark.parametrize("mod", [ApprovalMode.SECURITY, ApprovalMode.DONT_ASK])
async def test_onceden_onayli_belge_alani_sorulmaz(tmp_path, mod):
    url = {"url": "https://docs.python.org/3/library/re.html"}
    assert await _karar(mod, "web_fetch", url, tmp_path) is Decision.ALLOW


async def test_acik_kural_onceden_onayli_kumenin_onune_gecer(tmp_path):
    kural = parse_rule("WebFetch(domain:docs.python.org)", PermissionDecision.ASK, source="t")
    kume = PermissionRuleSet(rules=(kural,))
    url = {"url": "https://docs.python.org/3/"}
    sonuc = await _karar(ApprovalMode.SECURITY, "web_fetch", url, tmp_path, rules=kume)
    assert sonuc is Decision.DENIED


async def test_allow_kurali_alani_sormadan_acar(tmp_path):
    kural = parse_rule("WebFetch(domain:example.com)", PermissionDecision.ALLOW, source="t")
    kume = PermissionRuleSet(rules=(kural,))
    url = {"url": "https://example.com/a"}
    assert await _karar(ApprovalMode.SECURITY, "web_fetch", url, tmp_path, rules=kume) is (
        Decision.ALLOW
    )


async def test_kalici_kural_alan_ve_arama_bicimi(tmp_path):
    istek = await resolve_request(
        _REG.get("web_fetch"), {"url": "https://a.b.com/x"}, root=tmp_path
    )
    assert rule_for_request(istek, tmp_path).pattern == "WebFetch(domain:a.b.com)"
    istek = await resolve_request(_REG.get("web_search"), {"query": "q"}, root=tmp_path)
    assert rule_for_request(istek, tmp_path).pattern == "WebSearch"
