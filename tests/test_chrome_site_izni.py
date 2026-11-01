"""#435: Chrome'da site izni katmanı — Allow this action / Always allow / Decline."""

from __future__ import annotations

import pytest

from fusion_cli.appserver.bridges import _approval_options
from fusion_cli.cli.repl import chrome_command
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMemory,
    BypassApproval,
    Decision,
    SecurityApproval,
    resolve_request,
)
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.chrome_site_policy import SiteCategory, classify
from fusion_cli.ui.chrome_site_labels import relabel_choices
from fusion_cli.ui.picker import Choice

pytestmark = pytest.mark.asyncio
_REGISTRY = build_registry()


class _Chrome:
    def __init__(self, url: str) -> None:
        self.url = url
        self.calls: list[str] = []

    async def invoke(self, name, data):
        self.calls.append(name)
        if name == "tabs":
            return {"ok": True, "veri": {"tabs": [{"id": 1, "url": self.url, "bound": True}]}}
        if name.startswith("describe"):
            return {"ok": True, "veri": {"name": "Devam", "tag": "button"}}
        return {"ok": True, "veri": {"changed": True}}


class _Prompter:
    def __init__(self, answer=ApprovalAnswer.SESSION) -> None:
        self.answer = answer
        self.asked: list[str | None] = []

    async def confirm(self, request):
        self.asked.append(request.note)
        return self.answer


async def _request(tmp_path, url: str, tool: str = "chrome_click", args=None):
    context = ToolContext(root=tmp_path, chrome=_Chrome(url))  # type: ignore[arg-type]
    found = _REGISTRY.get(tool)
    assert found is not None
    return await resolve_request(found, args or {"ref": "e1"}, root=tmp_path, context=context)


async def test_siniflandirma_engelli_finansal_ve_siradan() -> None:
    assert classify("pornhub.com") is SiteCategory.ADULT
    assert classify("cdn.xvideos.com") is SiteCategory.ADULT
    assert classify("essex.ac.uk") is SiteCategory.NORMAL
    assert classify("thepiratebay.org") is SiteCategory.PIRACY
    assert classify("garantibbva.com.tr") is SiteCategory.FINANCIAL
    assert classify("online-bank.example") is SiteCategory.FINANCIAL
    assert classify("github.com") is SiteCategory.NORMAL


async def test_ilk_eylem_site_izni_ister_hep_izin_verilince_sitede_sorulmaz(tmp_path) -> None:
    request = await _request(tmp_path, "https://www.example.com/sepet")
    assert request.consent_key == "chrome-site:example.com"
    assert "Chrome'da Fusion example.com sitesinde tıklamak istiyor" in str(request.note)
    assert request.can_remember and "example.com" in str(request.remembered_scope_description)
    memory = ApprovalMemory()
    prompter = _Prompter()
    policy = SecurityApproval(prompter, memory)
    assert await policy.decide(request) is Decision.ALLOW
    again = await _request(tmp_path, "https://example.com/baska", "chrome_type", {"ref": "e2", "text": "a"})
    assert await policy.decide(again) is Decision.ALLOW
    assert len(prompter.asked) == 1  # aynı sitede ikinci eylem sorulmadı
    other = await _request(tmp_path, "https://other.org/")
    assert await policy.decide(other) is Decision.ALLOW
    assert len(prompter.asked) == 2  # başka site ayrıca soruldu


async def test_allow_this_action_hatirlanmaz(tmp_path) -> None:
    memory = ApprovalMemory()
    prompter = _Prompter(ApprovalAnswer.ONCE)
    policy = SecurityApproval(prompter, memory)
    for _ in range(2):
        assert await policy.decide(await _request(tmp_path, "https://example.com")) is Decision.ALLOW
    assert len(prompter.asked) == 2


async def test_yetiskin_sitede_eylem_ve_gezinme_engellenir(tmp_path) -> None:
    request = await _request(tmp_path, "https://pornhub.com/x")
    assert request.pre_denied is not None and "yetişkin" in request.pre_denied
    chrome = _Chrome("https://example.com")
    context = ToolContext(root=tmp_path, chrome=chrome)  # type: ignore[arg-type]
    result = await _REGISTRY.execute("chrome_navigate", {"url": "thepiratebay.org"}, context)
    assert not result.ok and "korsan" in result.output
    assert "navigate" not in chrome.calls


async def test_finansal_site_izinleri_atla_kipinde_de_sorulur_sonra_hatirlanir(tmp_path) -> None:
    memory = ApprovalMemory()
    prompter = _Prompter()
    policy = BypassApproval(prompter, memory)
    finans = await _request(tmp_path, "https://www.isbank.com.tr/giris")
    assert "Finansal site" in str(finans.note)
    assert await policy.decide(finans) is Decision.ALLOW
    assert await policy.decide(await _request(tmp_path, "https://isbank.com.tr/")) is Decision.ALLOW
    assert len(prompter.asked) == 1
    siradan = await _request(tmp_path, "https://example.com")
    assert await policy.decide(siradan) is Decision.ALLOW
    assert len(prompter.asked) == 1  # bypass sıradan sitede sormaz


async def test_hedef_okunamazsa_katman_uygulanmaz(tmp_path) -> None:
    request = await _request(tmp_path, "chrome://settings")
    assert request.consent_key is None and request.chrome_site is None


async def test_kart_secenekleri_claude_adlariyla(tmp_path) -> None:
    request = await _request(tmp_path, "https://example.com")
    options = _approval_options(request)
    assert [o["etiket"] for o in options] == [
        "Allow this action",
        "Always allow actions on this site",
        "Decline",
    ]
    choices = relabel_choices(
        request, [Choice("once", "Evet"), Choice("session", "Oturum"), Choice("deny", "Hayır")]
    )
    assert [c.label for c in choices] == [o["etiket"] for o in options]


async def test_chrome_permissions_izinli_siteleri_listeler_ve_geri_alir(tmp_path) -> None:
    memory = ApprovalMemory()
    await SecurityApproval(_Prompter(), memory).decide(
        await _request(tmp_path, "https://example.com")
    )
    listing = chrome_command.permissions(memory, "")
    assert "Your approved sites" in listing and "example.com" in listing
    assert "geri alındı" in chrome_command.permissions(memory, "revoke example.com")
    assert "yok" in chrome_command.permissions(memory, "revoke example.com")
    assert "verilmiş site yok" in chrome_command.permissions(memory, "")
