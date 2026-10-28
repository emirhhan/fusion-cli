"""Doğrulanmış kimliği yürütme bağlamına bağlar (WP02).

Bu modül `ExecutionContext` kurmanın TEK yoludur: istek gövdesindeki tenant ya da
workspace beyanı dikkate alınmaz, yalnız doğrulanmış kimlik ve üyelik kararı.
Pilot (plan §2): hesap = kişisel tenant, tek workspace = `PERSONAL_WORKSPACE`;
başka workspace'e üyelik ve ekip erişimi kapalıdır.
"""

from __future__ import annotations

from ..core.execution_context import FULL_ACCESS, PERSONAL_WORKSPACE, ExecutionContext, Identity

__all__ = [
    "LOCAL_TENANT",
    "PERSONAL_WORKSPACE",
    "WorkspaceAccessError",
    "bind_context",
    "device_identity",
    "local_identity",
]
#: Hesapsız (eski düzen) kurulumun tenant'ı.
LOCAL_TENANT = "local"


class WorkspaceAccessError(PermissionError):
    """Kimlik bu çalışma alanının üyesi değil."""


def local_identity(account_id: str) -> Identity:
    """Masaüstündeki oturum açmış (ya da hesapsız) yerel sahip."""
    tenant = account_id or LOCAL_TENANT
    return Identity(user_id=tenant, tenant_id=tenant, scopes=frozenset({FULL_ACCESS}))


def device_identity(account_id: str, device_id: str, scopes: frozenset[str]) -> Identity:
    """Bir hesaba eşleşmiş cihaz: hesabın tenant'ında, yalnız eşleşme kapsamlarıyla."""
    tenant = account_id or LOCAL_TENANT
    return Identity(user_id=tenant, tenant_id=tenant, scopes=scopes, device_id=device_id)


def bind_context(
    identity: Identity,
    workspace_id: str,
    *,
    device_id: str = "",
    session_id: str = "",
) -> ExecutionContext:
    """Üyeliği doğrula ve bağlamı kur; üyelik yoksa `WorkspaceAccessError`."""
    if workspace_id != PERSONAL_WORKSPACE:
        raise WorkspaceAccessError(f"Bu çalışma alanına erişim yok: {workspace_id}")
    return ExecutionContext(
        tenant_id=identity.tenant_id,
        user_id=identity.user_id,
        workspace_id=workspace_id,
        device_id=device_id or identity.device_id,
        session_id=session_id,
        scopes=identity.scopes,
    )
