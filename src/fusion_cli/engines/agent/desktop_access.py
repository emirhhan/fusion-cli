"""Toplu uygulama onayını onay isteğine işle (#426; Claude `request_access`).

Tek kart, tek "Bu oturumda … için izin ver / Reddet": onay istenen her uygulamayı oturum
iznine yazar (`consent_key` + `extra_consent_keys`). Engelli uygulama (ret listesi, Fusion'ın
kendi penceresi) karta girmez; hepsi engelliyse çağrı sorulmadan kapanır. İzinleri atla dahil
her kipte sorulur (#446) ve istenen uygulamaların hepsi zaten izinliyse sorulmaz.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ...core.desktop_settings import DesktopTarget
from ...core.tools import ToolArgs, ToolContext, ToolEffect
from ...tools.desktop_access import (
    ACCESS_TOOL,
    OwnerReader,
    describe,
    plan_access,
    requested_apps,
)
from .desktop_approval import consent_key

if TYPE_CHECKING:
    from .approval import ApprovalRequest

__all__ = ["ACCESS_TOOL", "apply_access"]

#: Hiç uygulama istenmediğinde modele dönen gerekçe.
EMPTY_REASON = "desktop_request_access: apps boş; kullanılacak uygulamaları liste olarak ver"


def apply_access(
    request: ApprovalRequest,
    args: ToolArgs,
    context: ToolContext,
    owners: OwnerReader | None = None,
) -> ApprovalRequest:
    """İsteği toplu uygulama onayına çevir; engelliler dışarıda kalır."""
    apps = requested_apps(args)
    if not apps:
        return replace(request, pre_denied=EMPTY_REASON)
    plan = plan_access(context.desktop_settings, apps, owners)
    if not plan.allowed:
        reasons = "; ".join(reason for _, reason in plan.blocked)
        first = plan.blocked[0][0]
        return replace(
            request,
            pre_denied=request.pre_denied or reasons,
            desktop_target=DesktopTarget(first),
            desktop_blocked=request.pre_denied is None,
        )
    first, *rest = plan.allowed
    names = ", ".join(target.app for target in plan.allowed)
    warnings = " ".join(target.warning for target in plan.allowed if target.warning)
    combined = DesktopTarget(names, first.bundle if not rest else "", 0, first.level, warnings)
    note = describe(plan)
    return replace(
        request,
        effect=ToolEffect.REMOTE_INTERACT,
        risk=note,
        unattended_safe=False,
        read_only=False,
        note=note,
        consent_key=consent_key(first.key),
        extra_consent_keys=tuple(consent_key(target.key) for target in rest),
        desktop_target=combined,
    )
