"""Plan kipinde auto sınıflandırıcısı — Claude Code `useAutoModeDuringPlan` (#52).

Kaynak: code.claude.com/docs/en/settings-reference (`useAutoModeDuringPlan`, varsayılan
`true`) ve permission-modes (Analyze before you edit with plan mode). Auto kipi
kullanılabiliyorsa planlama sırasında yerleşik salt okunur küme dışındaki kabuk komutunu
sınıflandırıcı inceler ve kullanıcı sorulmaz; kritik yol silmesi yine sorulur. Ayar `false`
ise ya da auto kullanılamıyorsa komut sorulur (`PlanApproval`).

Fusion karşılığı: denetçi modeli (`runtime.auto_classifier`) "güvenli" derse istek
`classifier_allowed` ile işaretlenir ve `PlanApproval` sormadan geçirir; "riskli" derse kart
gerekçeyle sorulur (Claude'da engellenen eylemin Fusion'daki karşılığı soru). Model yok,
erişilemedi ya da cevap bozuksa istek aynen döner: belgedeki "auto kullanılamıyor" dalı.

Auto kullanılabilirliği: `disableAutoMode` yok, denetçi kapalı değil (`off`), oturum Manuel'e
düşmemiş. Bypass kullanılabilir oturumda plan kipi bypass kurallarıyla çalışır, model
çağrılmaz. Plan kipindeki riskli kararlar auto kipinin engel sayacına yazılmaz: sayaç auto
kipini Manuel'e düşürür, plan kipini değil.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ...config.permission_settings import auto_mode_disabled, use_auto_mode_during_plan
from ...core.auto_review import ReviewSource, ReviewVerdict
from ...core.events import AutoReviewDecided
from ...core.tools import ToolFamily, tool_family

if TYPE_CHECKING:
    from .approval import ApprovalRequest
    from .auto_guard import AutoReviewState
    from .risk_classifier import ReviewDeps

#: Denetçi istemindeki "kuralın notu": plan kipinde neden incelendiği.
PLAN_REVIEW_NOTE = "plan kipinde salt okunur olmayan kabuk komutu"
#: Önbellek anahtarının auto kip kararlarından ayrılması için öneki.
_CACHE_PREFIX = "plan:"


async def review_plan_request(
    request: ApprovalRequest, deps: ReviewDeps, state: AutoReviewState
) -> ApprovalRequest:
    """Plan kipindeki kabuk komutunu denetçiye sor; güvenliyse `classifier_allowed` işaretle."""
    from .risk_classifier import (
        CARD_NOTE,
        ReviewKind,
        cache_key,
        classify,
        has_fixed_shell_risk,
        user_intent,
    )

    root = deps.tool_context.root
    touched = tuple(deps.tool_context.touched)
    if root is None or not _eligible(request) or _plan_bypass(state):
        return request
    if has_fixed_shell_risk(str(request.args.get("command")), root, touched):
        return request
    if not use_auto_mode_during_plan(root) or auto_mode_disabled(root):
        return request
    if state.remembered is not None and state.remembered(request):
        return request
    intent = user_intent(getattr(deps, "live_history", None))
    reviewed = replace(request, risk=PLAN_REVIEW_NOTE)
    key = _CACHE_PREFIX + cache_key(reviewed, intent)
    cached = state.cached(key)
    if cached is not None:
        outcome = replace(cached, source=ReviewSource.CACHE)
    else:
        outcome = await classify(
            reviewed,
            intent,
            deps.config,
            deps.publisher,
            root=root,
            kind=ReviewKind.RELAX,
            state=state,
        )
        state.remember(key, outcome)
    if outcome.source is ReviewSource.RULE:
        return request
    deps.publisher.publish(
        AutoReviewDecided(
            tool=outcome.tool,
            verdict=outcome.verdict,
            reason=outcome.reason,
            source=outcome.source,
            summary=outcome.summary,
            consecutive=state.consecutive,
            total=state.total,
        )
    )
    note = CARD_NOTE.format(reason=outcome.reason)
    if outcome.verdict is ReviewVerdict.SAFE:
        return replace(request, note=note, classifier_allowed=True)
    return replace(request, note=f"{request.note}. {note}" if request.note else note)


def _eligible(request: ApprovalRequest) -> bool:
    """Salt okunur olmayan, kuralca karara bağlanmamış, kritik/korumalı olmayan kabuk komutu."""
    if (
        request.pre_denied is not None
        or request.pre_ask is not None
        or request.pre_allowed
        or request.danger is not None
        or request.critical is not None
        or request.protected is not None
        or request.read_only
    ):
        return False
    command = request.args.get("command")
    return tool_family(request.tool.name) is ToolFamily.SHELL and isinstance(command, str)


def _plan_bypass(state: AutoReviewState) -> bool:
    probe = getattr(state, "plan_bypass", None)
    return bool(probe()) if probe is not None else False
