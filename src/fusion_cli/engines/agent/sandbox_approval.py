"""Kabuk onay isteğine sandbox kararını işle (P-010).

Claude Code davranışının Fusion karşılığı:
- `dangerouslyDisableSandbox` → `run_shell(unsandboxed=true)`: HER SEFERİNDE açık onay
  (`pre_ask`; oturum/kalıcı izne dönüşmez). Yalnız "İzinleri atla" kipi sormaz.
- `excludedCommands` → `sandbox.excluded_commands`: normal onay akışı, kartta not.
- `failIfUnavailable` → sandbox kurulamıyorsa kimseye sorulmadan kapatılır (`pre_denied`).
- `autoAllowBashIfSandboxed` → `sandbox.auto_allow`: sandbox içinde VE ağ allowlist'teyken
  komut sorulmaz. Yıkıcı komut, `ask`/`deny` kuralı ve plan kipi bunu geçer: ağ açıkken
  (`network: open`) otomatik izin verilmez, çünkü sandbox veri sızdırmayı sınırlamaz.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ...core.sandbox_policy import SandboxPolicy
from ...core.shell_sandbox import SHELL_SANDBOX_WRITE_ROOT
from ...core.tools import ToolContext, ToolFamily, tool_family
from ...tools.sandbox_runtime import OUTSIDE_EXCLUDED, OUTSIDE_REQUESTED, outside_reason, probe_plan

if TYPE_CHECKING:
    from .approval import ApprovalRequest

__all__ = ["SANDBOX_AUTO_ALLOWED", "SANDBOX_EXCLUDED", "SANDBOX_OUTSIDE", "apply_sandbox_policy"]

SANDBOX_OUTSIDE = (
    "sandbox DIŞINDA çalıştırma isteniyor (unsandboxed=true): yazma, okuma ve ağ sınırı "
    "olmadan çalışır; her seferinde sorulur"
)
SANDBOX_EXCLUDED = "sandbox dışı listesinde (sandbox.excluded_commands); sandbox'sız çalışır"
SANDBOX_AUTO_ALLOWED = "sandbox içinde, ağ allowlist'te: sorulmadan çalışır (sandbox.auto_allow)"


def _with_note(request: ApprovalRequest, note: str) -> str:
    return f"{request.note}. {note}" if request.note else note


def apply_sandbox_policy(request: ApprovalRequest, context: ToolContext | None) -> ApprovalRequest:
    """Kabuk isteğini sandbox durumuna göre daralt ya da (auto_allow) serbest bırak."""
    command = request.args.get("command")
    if (
        context is None
        or not isinstance(command, str)
        or tool_family(request.tool.name) is not ToolFamily.SHELL
        or getattr(context, "shell_sandbox", "off") != SHELL_SANDBOX_WRITE_ROOT
    ):
        return request
    outside = outside_reason(command, request.args, context)
    if outside == OUTSIDE_REQUESTED:
        return replace(
            request,
            pre_ask=request.pre_ask or SANDBOX_OUTSIDE,
            note=_with_note(request, SANDBOX_OUTSIDE),
        )
    if outside == OUTSIDE_EXCLUDED:
        return replace(request, note=_with_note(request, SANDBOX_EXCLUDED))
    plan = probe_plan(context)
    if plan.refused:
        return replace(request, pre_denied=request.pre_denied or plan.refused)
    policy = getattr(context, "sandbox_policy", None) or SandboxPolicy()
    if (
        policy.auto_allow
        and policy.restricts_network
        and plan.is_active
        and request.danger is None
        and request.pre_ask is None
        and request.pre_denied is None
    ):
        return replace(request, pre_allowed=True, note=_with_note(request, SANDBOX_AUTO_ALLOWED))
    return request
