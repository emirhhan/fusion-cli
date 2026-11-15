"""Sandbox içindeki komut listede olmayan bir ana makineye bağlanınca kimin karar verdiği (#323).

Claude Code (sandboxing, "Hosts outside your allowed domains"): sandbox içindeki komutun
doğrudan çıkışı yoktur; trafik proxy'den geçer ve `allowedDomains` boş başlar. Liste dışı bir
ad istendiğinde komut sandbox'ta bekler ve karar izin kipine göredir:

| Kip | Bağlantı |
| --- | --- |
| bypassPermissions, bypass kullanılabilen plan kipi | sorulmadan izin |
| Manual (default), acceptEdits, öteki plan kipi | kullanıcıya sorulur |
| auto | reddedilir (Fusion'da sınıflandırıcı ana makine listesini onaylamaz) |
| dontAsk | reddedilir |

`strictAllowlist` her kipte reddeder (proxy bakar); `deniedDomains` her kipte önce gelir.
`WebFetch(domain:…)` allow kuralındaki adlar sorulmadan geçer. "Evet" ad için oturum
boyunca izin verir; "Evet, bir daha sorma" yerel ayara `WebFetch(domain:<ad>)` yazar.

Karar proxy thread'inden verilir; soru motorun olay döngüsünde sorulur (kabuk komutu ayrı
thread'de koştuğu için döngü serbesttir).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from ...config.permission_admin import add_permission_rule
from ...config.permission_rules import PermissionDecision, PermissionRule, PermissionRuleSet
from ...core.shell_sandbox import SHELL_SANDBOX_WRITE_ROOT
from ...core.tools import Tool, ToolContext, ToolResult
from ...tools.permission_match import evaluate
from .approval import (
    ApprovalAnswer,
    ApprovalPolicy,
    ApprovalReply,
    ApprovalRequest,
    AutoApproval,
    BypassApproval,
    DontAskApproval,
    Prompter,
)
from .plan_approval import PlanApproval

__all__ = ["NetworkChoice", "install_network_gate", "network_choice", "network_prompt_tool"]

_LOG = logging.getLogger(__name__)
#: Kullanıcının cevabını bekleme sınırı (sn); dolarsa bağlantı reddedilir.
PROMPT_TIMEOUT_S = 600.0
_WEB_FETCH = "web_fetch"


class NetworkChoice(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


def network_choice(policy: ApprovalPolicy) -> NetworkChoice:
    """Kipin liste dışı ana makine kararı (Claude tablosu)."""
    if isinstance(policy, BypassApproval):
        return NetworkChoice.ALLOW
    if isinstance(policy, PlanApproval):
        return NetworkChoice.ALLOW if policy.bypass_available else NetworkChoice.ASK
    if isinstance(policy, (AutoApproval, DontAskApproval)):
        return NetworkChoice.DENY
    return (
        NetworkChoice.ASK if getattr(policy, "prompter", None) is not None else NetworkChoice.DENY
    )


def _no_run(_args: object, _context: ToolContext) -> ToolResult:
    return ToolResult.failure("Yalnız onay kartı içindir.")


def network_prompt_tool() -> Tool:
    """Kartta gösterilen çağrı: `web_fetch` (kalıcı kural `WebFetch(domain:…)` olur)."""
    return Tool(name=_WEB_FETCH, description="Sandbox ağ erişimi", parameters={}, run=_no_run)


def _request(host: str) -> ApprovalRequest:
    return ApprovalRequest(
        tool=network_prompt_tool(),
        args={"url": f"https://{host}"},
        danger=None,
        note=(
            f"Sandbox içindeki komut {host} adresine bağlanmak istiyor "
            "(sandbox.network.allowedDomains listesinde değil)."
        ),
    )


def _pre_allowed(rules: PermissionRuleSet | None, host: str, root: Path) -> bool:
    """`WebFetch(domain:…)` allow kuralı adı sorulmadan açar (Claude)."""
    if rules is None:
        return False
    match = evaluate(rules, _WEB_FETCH, {"url": f"https://{host}"}, root)
    return (
        match is not None
        and match.decision is PermissionDecision.ALLOW
        and (match.rule.specifier or "").startswith("domain:")
    )


class _Decider:
    """Proxy thread'inden çağrılan karar; aynı anda tek soru, aynı ad bir kez sorulur."""

    def __init__(
        self,
        context: ToolContext,
        choice: NetworkChoice,
        prompter: Prompter | None,
        loop: asyncio.AbstractEventLoop,
        rules: PermissionRuleSet | None,
    ) -> None:
        self._context = context
        self._choice = choice
        self._prompter = prompter
        self._loop = loop
        self._rules = rules
        self._lock = threading.Lock()
        self._refused: set[str] = set()

    def __call__(self, host: str) -> bool:
        gate = self._context.sandbox_hosts
        if host in gate.session_hosts or _pre_allowed(self._rules, host, self._context.root):
            return True
        if self._choice is not NetworkChoice.ASK or self._prompter is None:
            return self._choice is NetworkChoice.ALLOW
        with self._lock:
            if host in gate.session_hosts:
                return True
            if host in self._refused:
                return False
            allowed = self._ask(host)
            (gate.session_hosts if allowed else self._refused).add(host)
            return allowed

    def _ask(self, host: str) -> bool:
        assert self._prompter is not None
        future = asyncio.run_coroutine_threadsafe(
            self._prompter.confirm(_request(host)), self._loop
        )
        try:
            reply = future.result(timeout=PROMPT_TIMEOUT_S)
        except Exception as error:  # zaman aşımı, kapanan döngü: bağlantı geçmez
            future.cancel()
            _LOG.warning("sandbox ağ sorusu cevaplanmadı", extra={"hata": str(error)})
            return False
        answer = reply.answer if isinstance(reply, ApprovalReply) else reply
        if answer is ApprovalAnswer.ALWAYS:
            self._persist(host)
        return answer in (True, ApprovalAnswer.ONCE, ApprovalAnswer.SESSION, ApprovalAnswer.ALWAYS)

    def _persist(self, host: str) -> None:
        rule = PermissionRule("WebFetch", f"domain:{host}", PermissionDecision.ALLOW)
        try:
            add_permission_rule(self._context.root, rule)
        except Exception as error:  # izin yine verilir; yalnız kayıt düşer
            _LOG.warning("WebFetch(domain:) kuralı yazılamadı", extra={"hata": str(error)})


def install_network_gate(
    context: ToolContext,
    policy: ApprovalPolicy,
    rules: PermissionRuleSet | None = None,
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> Callable[[str], bool] | None:
    """Kabuk çağrısından önce bu çağrının kipine göre karar vereni kur (sandbox kapalıysa yok)."""
    gate = getattr(context, "sandbox_hosts", None)
    if gate is None:
        return None
    if getattr(context, "shell_sandbox", "off") != SHELL_SANDBOX_WRITE_ROOT:
        gate.decider = None
        return None
    running = loop or asyncio.get_running_loop()
    prompter = getattr(policy, "prompter", None)
    decider = _Decider(context, network_choice(policy), prompter, running, rules)
    gate.decider = decider
    return decider
