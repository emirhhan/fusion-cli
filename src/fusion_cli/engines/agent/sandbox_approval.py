"""Kabuk onay isteğine sandbox kararını işle (P-010).

Claude Code davranışının Fusion karşılığı:
- `dangerouslyDisableSandbox=true` (eski ad `unsandboxed`): Claude sandboxing › "Escape hatch"
  matrisi (#351). İstek riskli sayılır (`risk`, salt okunur değil): bypass sormaz, Manuel ve
  acceptEdits "Bash command (unsandboxed)" diye sorar, auto'da denetçi (sınıflandırıcı) karar
  verir, dontAsk reddeder. Komuta uyan `allow` kuralı yeniden denemeyi sormadan onaylar;
  `Bash(dangerouslyDisableSandbox:true)` `ask` kuralı her kipte soruyu zorunlu kılar
  (`deny` kuralı reddeder). `allowUnsandboxedCommands: false` parametreyi tümüyle yok sayar.
- `excludedCommands` → `sandbox.excluded_commands`: normal onay akışı, kartta not.
- `failIfUnavailable` → sandbox kurulamıyorsa kimseye sorulmadan kapatılır (`pre_denied`).
- `autoAllowBashIfSandboxed` → `sandbox.auto_allow` (Claude'da varsayılan açık, #347):
  sandbox içinde çalışan komut ağ kipinden bağımsız sorulmaz. Yıkıcı komut, `ask`/`deny`
  kuralı ve plan kipi bunu geçer; `FOO=bar npm test`, `make CC=clang`, `eval "ls"` gibi
  çalışacak programı değiştirebilen biçimler olağan izin akışından geçer (Claude).
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from ...config.permission_rules import PermissionDecision, PermissionRule, PermissionRuleSet
from ...core.sandbox_policy import SandboxPolicy
from ...core.shell_sandbox import SHELL_SANDBOX_WRITE_ROOT
from ...core.tools import ToolContext, ToolFamily, tool_family
from ...tools.sandbox_runtime import OUTSIDE_EXCLUDED, OUTSIDE_REQUESTED, outside_reason, probe_plan

if TYPE_CHECKING:
    from .approval import ApprovalRequest

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

__all__ = [
    "SANDBOX_AUTO_ALLOWED",
    "SANDBOX_EXCLUDED",
    "SANDBOX_OUTSIDE",
    "apply_sandbox_policy",
    "changes_program",
]

SANDBOX_OUTSIDE = (
    "Bash command (unsandboxed): sandbox DIŞINDA çalıştırma isteniyor "
    "(dangerouslyDisableSandbox=true); yazma, okuma ve ağ sınırı olmadan çalışır"
)
#: Claude'un parametre kuralı belirteci: `Bash(dangerouslyDisableSandbox:true)`.
DISABLE_SANDBOX_RULE = "dangerouslyDisableSandbox:true"
SANDBOX_EXCLUDED = "sandbox dışı listesinde (sandbox.excluded_commands); sandbox'sız çalışır"
SANDBOX_AUTO_ALLOWED = "sandbox içinde: sorulmadan çalışır (sandbox.autoAllowBashIfSandboxed)"


def changes_program(command: str) -> bool:
    """Komut çalışacak programı değiştirebilecek biçimde mi? (Claude: auto-allow uygulanmaz)

    Başta değişken ataması (`FOO=bar npm test`), `make VAR=değer` ve `eval`.
    """
    for segment in re.split(r"&&|\|\||[;|\n]", command):
        words = segment.split()
        if not words:
            continue
        if _ASSIGNMENT.match(words[0]) or words[0] == "eval":
            return True
        if words[0] == "make" and any(_ASSIGNMENT.match(word) for word in words[1:]):
            return True
    return False


def _with_note(request: ApprovalRequest, note: str) -> str:
    return f"{request.note}. {note}" if request.note else note


def _flag_rule(rules: PermissionRuleSet | None) -> PermissionRule | None:
    """`Bash(dangerouslyDisableSandbox:true)` kuralı (en kısıtlayıcısı: deny > ask > allow)."""
    if rules is None:
        return None
    hits = [
        rule
        for rule in rules.rules
        if rule.tool == "Bash" and (rule.specifier or "").replace(" ", "") == DISABLE_SANDBOX_RULE
    ]
    order = (PermissionDecision.DENY, PermissionDecision.ASK, PermissionDecision.ALLOW)
    return next((rule for decision in order for rule in hits if rule.decision is decision), None)


def _outside_request(request: ApprovalRequest, rules: PermissionRuleSet | None) -> ApprovalRequest:
    """Sandbox dışı yeniden denemeyi Claude matrisine göre işaretle (#351)."""
    note = _with_note(request, SANDBOX_OUTSIDE)
    danger = f"{request.danger}; {SANDBOX_OUTSIDE}" if request.danger else None
    flag = _flag_rule(rules)
    if flag is not None and flag.decision is PermissionDecision.DENY:
        reason = f"izin kuralı yasaklıyor: {flag.pattern}"
        return replace(request, pre_denied=request.pre_denied or reason, rule=flag.pattern)
    if flag is not None and flag.decision is PermissionDecision.ASK:
        reason = f"izin kuralı her zaman sorulmasını istiyor: {flag.pattern}"
        return replace(
            request,
            pre_ask=request.pre_ask or reason,
            pre_allowed=False,
            note=note,
            danger=danger,
            rule=flag.pattern,
        )
    if request.pre_allowed or (flag is not None and flag.decision is PermissionDecision.ALLOW):
        # Komuta uyan `allow` kuralı yeniden denemeyi de onaylar (Claude).
        return replace(request, pre_allowed=True, note=note, danger=danger)
    # Kipe bırakılan risk: Manuel/acceptEdits sorar, auto denetçiye, dontAsk reddeder.
    return replace(
        request,
        risk=request.risk or SANDBOX_OUTSIDE,
        read_only=False,
        unattended_safe=False,
        note=note,
        danger=danger,
    )


def apply_sandbox_policy(
    request: ApprovalRequest,
    context: ToolContext | None,
    rules: PermissionRuleSet | None = None,
) -> ApprovalRequest:
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
        # Kartlar tehlike varken notu göstermez (`appserver.bridges`); yıkıcı istekte
        # sandbox dışı bilgisi tehlike metnine eklenir. Ölçüldü (31 Ekim): `git push
        # --force` + unsandboxed kartında yalnız "zorla push" yazıyordu.
        return _outside_request(request, rules)
    if outside == OUTSIDE_EXCLUDED:
        return replace(request, note=_with_note(request, SANDBOX_EXCLUDED))
    plan = probe_plan(context)
    if plan.refused:
        return replace(request, pre_denied=request.pre_denied or plan.refused)
    policy = getattr(context, "sandbox_policy", None) or SandboxPolicy()
    if (
        policy.auto_allow
        and plan.is_active
        and not changes_program(command)
        and request.danger is None
        and request.pre_ask is None
        and request.pre_denied is None
    ):
        return replace(request, pre_allowed=True, note=_with_note(request, SANDBOX_AUTO_ALLOWED))
    return request
