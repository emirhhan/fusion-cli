"""Plan kipinde Chrome GIF kaydı, yeni sekme ve kısayol sorulur; onaylanırsa çalışır (#450)."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, Decision, build_policy, resolve_request
from fusion_cli.tools.builtin import build_registry


class _Sor:
    def __init__(self, answer: object) -> None:
        self.answer = answer
        self.asked: list[object] = []

    async def confirm(self, request):
        self.asked.append(request)
        return self.answer


async def _karar(tmp_path, args, mode, answer=True):
    tool = build_registry().get("chrome_action")
    request = await resolve_request(tool, args, root=tmp_path, context=ToolContext(root=tmp_path))
    prompter = _Sor(answer)
    return await build_policy(mode, prompter).decide(request), prompter


@pytest.mark.parametrize(
    "args",
    [{"action": "record", "value": "start"}, {"action": "open", "value": "example.com"},
     {"action": "window", "value": "example.com"}, {"action": "shortcut", "value": "ozet"}],
)  # fmt: skip
async def test_plan_kipinde_sorulur_onaylanirsa_calisir(tmp_path, args):
    decision, prompter = await _karar(tmp_path, args, ApprovalMode.PLAN)
    assert decision is Decision.ALLOW and len(prompter.asked) == 1
    decision, _ = await _karar(tmp_path, args, ApprovalMode.PLAN, answer=False)
    assert decision is not Decision.ALLOW


async def test_plan_kipinde_okuma_sorulmaz_otomatikte_yeni_sekme_sorulmaz(tmp_path):
    decision, prompter = await _karar(tmp_path, {"action": "tabs"}, ApprovalMode.PLAN)
    assert decision is Decision.ALLOW and prompter.asked == []
    decision, prompter = await _karar(
        tmp_path, {"action": "open", "value": "example.com"}, ApprovalMode.AUTO
    )
    assert decision is Decision.ALLOW and prompter.asked == []


@pytest.mark.parametrize(
    "item",
    [{"name": "chrome_action", "input": {"action": "new_tab", "value": "example.com"}},
     {"name": "chrome_action", "input": {"action": "shortcut", "value": "ozet"}}],
)  # fmt: skip
async def test_plan_kipinde_toplu_cagri_icindeki_istemli_eylem_de_sorulur(tmp_path, item):
    """Belge: "including batch calls that contain them" (#450)."""
    tool = build_registry().get("chrome_batch")
    args = {"actions": [{"name": "chrome_page", "input": {}}, item]}
    request = await resolve_request(tool, args, root=tmp_path, context=ToolContext(root=tmp_path))
    assert request.plan_prompt
    prompter = _Sor(True)
    assert await build_policy(ApprovalMode.PLAN, prompter).decide(request) is Decision.ALLOW
    assert len(prompter.asked) == 1
    prompter = _Sor(False)
    assert await build_policy(ApprovalMode.PLAN, prompter).decide(request) is not Decision.ALLOW
