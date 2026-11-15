"""acceptEdits Claude gibi yalnız düzenlemeleri serbest bırakır (#53).

Claude (permission-modes#auto-approve-file-edits-with-acceptedits-mode): dosya düzenlemeleri ve
dosya sistemi komutları dışındaki eylemler Manuel kipteki gibi sorulur. Tarayıcıda tıklama/yazma
(`REMOTE_INTERACT`) düzenleme değildir: acceptEdits'te sorulur, Otomatik kipte sorulmaz.
"""

from __future__ import annotations

from fusion_cli.core.tools import Tool, ToolEffect
from fusion_cli.engines.agent.approval import ApprovalMode, Decision, build_policy, build_request


class _Soran:
    def __init__(self) -> None:
        self.soruldu: list[str] = []

    async def confirm(self, request):
        self.soruldu.append(request.tool.name)
        return False


def _arac(name: str) -> Tool:
    return Tool(name=name, description="", parameters={}, run=lambda a, c: None, mutating=True)


async def _karar(mod: ApprovalMode, name: str, args: dict, effect: ToolEffect, root):
    soran = _Soran()
    istek = build_request(_arac(name), args, effect=effect, root=root)
    return await build_policy(mod, soran).decide(istek), soran.soruldu


async def test_accept_edits_tarayici_tiklamasini_sorar(tmp_path):
    karar, soruldu = await _karar(
        ApprovalMode.ACCEPT_EDITS,
        "browser_click",
        {"ref": "e1"},
        ToolEffect.REMOTE_INTERACT,
        tmp_path,
    )
    assert soruldu == ["browser_click"] and karar is not Decision.ALLOW


async def test_otomatik_kip_tarayici_tiklamasini_sormaz(tmp_path):
    karar, soruldu = await _karar(
        ApprovalMode.AUTO, "browser_click", {"ref": "e1"}, ToolEffect.REMOTE_INTERACT, tmp_path
    )
    assert karar is Decision.ALLOW and soruldu == []


async def test_accept_edits_dosya_yazimini_sormaz(tmp_path):
    karar, soruldu = await _karar(
        ApprovalMode.ACCEPT_EDITS,
        "write_file",
        {"path": "a.txt", "content": "x"},
        ToolEffect.LOCAL,
        tmp_path,
    )
    assert karar is Decision.ALLOW and soruldu == []


async def test_accept_edits_uzak_okumayi_sormaz(tmp_path):
    karar, soruldu = await _karar(
        ApprovalMode.ACCEPT_EDITS, "browser_snapshot", {}, ToolEffect.REMOTE_READ, tmp_path
    )
    assert karar is Decision.ALLOW and soruldu == []
