"""Kaynak erişim kararı: `authorize(context, resource, action)` (WP02).

Karar yalnız bağlam ile kaynağın sahiplik bilgisinden çıkar. Sıra önemlidir:
önce tenant, sonra workspace, sonra sahip, en son kapsam — kapsamı olan bir cihaz
bile başka bir tenant'ın kaynağını göremez. Karar her zaman bir gerekçe kodu taşır.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .execution_context import ExecutionContext


class Action(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    CANCEL = "cancel"


REASON_ALLOWED = "allowed"
REASON_TENANT = "tenant_mismatch"
REASON_WORKSPACE = "workspace_mismatch"
REASON_OWNER = "not_owner"
REASON_SCOPE = "missing_scope"


@dataclass(frozen=True, slots=True)
class ResourceRef:
    """Erişilen şeyin kimliği ve kime ait olduğu."""

    kind: str
    resource_id: str
    tenant_id: str
    workspace_id: str
    #: Tek sahipli workspace'te boş bırakılabilir; doluysa bağlamın kullanıcısı olmalı.
    owner_user_id: str = ""


@dataclass(frozen=True, slots=True)
class AccessDecision:
    allowed: bool
    reason_code: str


def authorize(
    context: ExecutionContext,
    resource: ResourceRef,
    action: Action,
    *,
    required_scope: str | None = None,
) -> AccessDecision:
    """Bu bağlam bu kaynakta bu işlemi yapabilir mi?"""
    del action  # Eylem kapsam üzerinden ayrışır; karar kaydında tutulur.
    if resource.tenant_id != context.tenant_id:
        return AccessDecision(False, REASON_TENANT)
    if resource.workspace_id != context.workspace_id:
        return AccessDecision(False, REASON_WORKSPACE)
    if resource.owner_user_id and resource.owner_user_id != context.user_id:
        return AccessDecision(False, REASON_OWNER)
    if required_scope is not None and not context.has_scope(required_scope):
        return AccessDecision(False, REASON_SCOPE)
    return AccessDecision(True, REASON_ALLOWED)
