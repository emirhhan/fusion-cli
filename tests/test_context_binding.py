"""Yürütme bağlamı kimlik/üyelik çözümleyicisinden gelir; istek gövdesi yetki taşımaz (WP02).

Plan §2: ExecutionContext tenant/user/workspace/device/session/run ve kapsamları
taşır; ağdan gelen kimlikler doğrudan bu tipe çevrilmez. Pilot varsayımı: her
hesap kendi kişisel tenant'ı ve tek sahipli workspace'idir; ekip erişimi kapalı.
"""

from __future__ import annotations

import pytest

from fusion_cli.accounts.workspaces import (
    PERSONAL_WORKSPACE,
    WorkspaceAccessError,
    bind_context,
    local_identity,
)
from fusion_cli.core.access_policy import Action, ResourceRef, authorize
from fusion_cli.core.execution_context import FULL_ACCESS, ExecutionContext


def _ctx(tenant="t-a", user="u-a", workspace="w-a", scopes=frozenset({"project.read"})):
    return ExecutionContext(tenant_id=tenant, user_id=user, workspace_id=workspace, scopes=scopes)


def test_baglam_degistirilemez_ve_kimlik_alanlari_dogrulanir():
    ctx = _ctx()
    with pytest.raises(AttributeError):
        ctx.tenant_id = "t-b"  # type: ignore[misc]
    with pytest.raises(ValueError):
        ExecutionContext(tenant_id="", user_id="u", workspace_id="w")
    with pytest.raises(ValueError):
        ExecutionContext(tenant_id="../b", user_id="u", workspace_id="w")


@pytest.mark.parametrize(
    ("resource", "action", "scope", "allowed", "reason"),
    [
        (ResourceRef("run", "r1", "t-a", "w-a"), Action.READ, "project.read", True, "allowed"),
        (ResourceRef("run", "r1", "t-b", "w-a"), Action.READ, "project.read", False, "tenant"),
        (ResourceRef("run", "r1", "t-a", "w-b"), Action.READ, "project.read", False, "workspace"),
        (ResourceRef("run", "r1", "t-a", "w-a"), Action.CANCEL, "agent.cancel", False, "scope"),
        (
            ResourceRef("run", "r1", "t-a", "w-a", owner_user_id="u-x"),
            Action.READ,
            "project.read",
            False,
            "owner",
        ),
    ],
)
def test_yetki_karari_matrisi(resource, action, scope, allowed, reason):
    decision = authorize(_ctx(), resource, action, required_scope=scope)

    assert decision.allowed is allowed
    assert reason in decision.reason_code


def test_tam_yetkili_yerel_sahip_bile_baska_tenanta_erisemez():
    owner = _ctx(scopes=frozenset({FULL_ACCESS}))

    assert authorize(owner, ResourceRef("run", "r", "t-a", "w-a"), Action.CANCEL).allowed
    assert not authorize(owner, ResourceRef("run", "r", "t-b", "w-a"), Action.READ).allowed


def test_hesap_kendi_kisisel_workspaceine_baglanir():
    ctx = bind_context(local_identity("hesap-a"), PERSONAL_WORKSPACE, device_id="masaustu")

    assert ctx.tenant_id == ctx.user_id == "hesap-a"
    assert ctx.workspace_id == PERSONAL_WORKSPACE
    assert ctx.device_id == "masaustu"


def test_baska_hesabin_workspaceine_baglanilamaz():
    with pytest.raises(WorkspaceAccessError):
        bind_context(local_identity("hesap-a"), "hesap-b:kisisel")


def test_hesapsiz_kurulum_yerel_sahip_tenantina_baglanir():
    ctx = bind_context(local_identity(""), PERSONAL_WORKSPACE)

    assert ctx.tenant_id == "local"
    assert FULL_ACCESS in ctx.scopes
