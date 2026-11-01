"""Plan kipinin onay politikası — Claude Code ile birebir (#52).

Kaynak: code.claude.com/docs/en/permission-modes (Analyze before you edit with plan mode;
Protected paths). Plan kipinde Claude okur, keşif için kabuk komutu çalıştırır ve plan yazar;
kaynağı düzenlemez. Kabuk komutu için ilk uyan durum geçerlidir:

    bypass kullanılabilir oturum   ne sınıflandırıcı ne soru: bypass kipinin kuralları
                                   (açık `ask` kuralı ve kritik yol silmesi yine sorulur)
    auto kullanılabilir ve         sınıflandırıcı (denetçi modeli) inceler: güvenli → sorulmaz,
    `useAutoModeDuringPlan` açık   riskli → sorulur; kritik yol silmesi hep sorulur
                                   (`plan_review.review_plan_request`)
    öteki durumlar                 yerleşik salt okunur küme dışındaki komut sorulur (sandbox
                                   auto-allow açık olsa da); denetçi modeli yoksa da bu dal

Dosya düzenlemeleri (yerel yazma araçları) plan onaylanana dek engellenir. Açık `ask`
kuralı ve Fusion'ın yıkıcı/korumalı yol gerekçesi her durumda sorar. Uzak sistemde değişiklik
yapan MCP araçları Manuel kipteki gibi sorulur; masaüstü ve tarayıcı eylemi engellenir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.tools import ToolEffect, ToolFamily, tool_family
from ...tools.outside_reads import is_read_tool

if TYPE_CHECKING:
    from .approval import ApprovalMemory, ApprovalRequest, Prompter, Verdict


class PlanApproval:
    """Plan kipi: düzenleme yok; okuma ve allow kuralı serbest; öteki çağrı sorulur."""

    def __init__(
        self, prompter: Prompter | None = None, memory: ApprovalMemory | None = None
    ) -> None:
        from .approval import ApprovalMemory

        self._prompter = prompter
        self._memory = memory if memory is not None else ApprovalMemory()

    async def decide(self, request: ApprovalRequest) -> Verdict:
        from .approval import BypassApproval, Decision, _ask_and_remember

        if request.pre_denied is not None:
            return Decision.BLOCKED
        if self._memory.plan_bypass:
            return await BypassApproval(self._prompter, self._memory).decide(request)
        if request.plan_prompt and self._prompter is not None:
            # Claude Code: plan kipinde bu tarayıcı araçları izin istemi çıkarır (#450).
            return await _ask_and_remember(self._prompter, request, self._memory)
        must_ask = request.danger is not None or request.pre_ask is not None
        if not must_ask and request.read_only and not request.plan_prompt:
            return Decision.ALLOW
        if _edits_files(request):
            return Decision.BLOCKED
        if request.classifier_allowed and not must_ask:
            # Auto sınıflandırıcısı planlama komutunu güvenli buldu (#52).
            return Decision.ALLOW
        if _rule_allowed(request) and request.rule_opens:
            # Allow kuralı yalnız korumalı yol/kritik silmeyi açmaz (#84).
            return Decision.ALLOW
        if self._prompter is None:
            return Decision.BLOCKED
        if not must_ask and self._memory.is_remembered(request):
            return Decision.ALLOW
        return await _ask_and_remember(self._prompter, request, self._memory)


def _edits_files(request: ApprovalRequest) -> bool:
    """Plan kipinde sorulmadan engellenen değişiklik mi?

    Yalnız kabuk, web (#55), çalışma dizini dışı okuma (#56) ve MCP (uzak araç ailesi)
    çağrısı soruya gider; yerel dosya yazımı, masaüstü ve tarayıcı eylemi plan onaylanana
    dek engellenir.
    """
    family = tool_family(request.tool.name)
    if family in {ToolFamily.SHELL, ToolFamily.WEB} or is_read_tool(request.tool.name):
        return False
    return not (family is ToolFamily.EXTERNAL and request.effect is not ToolEffect.LOCAL)


def _rule_allowed(request: ApprovalRequest) -> bool:
    """Kullanıcının allow kuralı (sandbox auto-allow'u değil) çağrıyı onaylıyor mu?"""
    return request.pre_allowed and request.rule is not None
