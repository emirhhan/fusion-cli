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
from ...tools.sandbox_runtime import asks_unsandboxed

if TYPE_CHECKING:
    from .approval import ApprovalMemory, ApprovalRequest, Decision, Prompter, Verdict


class PlanApproval:
    """Plan kipi: düzenleme yok; okuma ve allow kuralı serbest; öteki çağrı sorulur."""

    def __init__(
        self,
        prompter: Prompter | None = None,
        memory: ApprovalMemory | None = None,
        *,
        use_auto_mode: bool = True,
        bypass_available: bool = False,
    ) -> None:
        from .approval import ApprovalMemory

        self._prompter = prompter
        self._memory = memory if memory is not None else ApprovalMemory()
        #: `useAutoModeDuringPlan` (#318): auto kullanılabilirken denetçi kararı plan kipinde de
        #: geçerli; `false` ise o komut kullanıcıya sorulur.
        self._use_auto_mode = use_auto_mode
        self._bypass_available = bypass_available

    @property
    def prompter(self) -> Prompter | None:
        return self._prompter

    @property
    def bypass_available(self) -> bool:
        """Bypass kullanılabilen oturumda plan kipi sormaz (#52; ağ sorusu da, #323)."""
        return self._bypass_available or self._memory.plan_bypass

    async def decide(self, request: ApprovalRequest) -> Verdict:
        from .approval import BypassApproval, Decision, _ask_and_remember

        if request.pre_denied is not None:
            return Decision.BLOCKED
        must_ask = request.danger is not None or request.pre_ask is not None
        if not must_ask and request.read_only and not request.plan_prompt:
            return Decision.ALLOW
        if request.plan_prompt and self._prompter is not None:
            # Claude Code: plan kipinde bu tarayıcı araçları izin istemi çıkarır (#450).
            return await _ask_and_remember(self._prompter, request, self._memory)
        if _edits_files(request):
            # Bypass kullanılabilen oturumda da plan kipi dosya düzenlemez (#52, #318).
            return Decision.BLOCKED
        if self.bypass_available:
            return await BypassApproval(self._prompter, self._memory).decide(request)
        if self._use_auto_mode and not must_ask and not asks_unsandboxed(request.args):
            # `useAutoModeDuringPlan` (varsayılan açık; Fusion'da auto kullanılabilir): denetçi
            # karar verir (#52, #318). Sandbox dışı yeniden deneme Claude'daki gibi sorulur.
            if request.classifier_allowed:
                return Decision.ALLOW
            verdict = _plan_classifier_verdict(request)
            if verdict is not None:
                return verdict
        if _rule_allowed(request) and request.rule_opens:
            # Allow kuralı yalnız korumalı yol/kritik silmeyi açmaz (#84).
            return Decision.ALLOW
        if self._prompter is None:
            return Decision.BLOCKED
        if not must_ask and self._memory.is_remembered(request):
            return Decision.ALLOW
        return await _ask_and_remember(self._prompter, request, self._memory)


def _plan_classifier_verdict(request: ApprovalRequest) -> Decision | None:
    """Plan kipinde kabuk denetçisi (#318): salt okunur ya da bilinen derleme/test komutu
    çalışır, kaynağı düzenleyen ya da riskli komut engellenir; geri kalanı (`None`) sorulur."""
    from .approval import Decision
    from .plan_shell_guard import PlanVerdict, plan_verdict

    if tool_family(request.tool.name) is not ToolFamily.SHELL:
        return None
    command = request.args.get("command")
    if request.risk is not None or not isinstance(command, str):
        return Decision.BLOCKED
    verdict = plan_verdict(command)
    if verdict is PlanVerdict.ALLOW:
        return Decision.ALLOW
    return Decision.BLOCKED if verdict is PlanVerdict.BLOCK else None


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
