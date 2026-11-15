"""Claude in Chrome çağrısını onaydan önce iç `chrome_*` çağrısına çevir (#431).

Sıra: `--disallowedTools`, kapsam ve PreToolUse kancası Claude adını görür (Claude'daki
gibi `mcp__claude-in-chrome__computer` ile eşleşir); onay, yasak eylem denetimi, plan kipi
ve panel akışı ise iç adı. Claude adına yazılmış izin kuralları bu çağrı için iç ada da
kopyalanır; toplu çağrıda yalnız deny/ask kopyalanır (allow bir iç aracın tüm eylemlerine
yayılıp gevşetmesin diye).
"""

from __future__ import annotations

import json
from dataclasses import replace

from ...config.permission_rules import PermissionDecision, PermissionRule, PermissionRuleSet
from ...core.claude_chrome_names import claude_chrome_short
from ...core.tools import ToolArgs, ToolContext, ToolResult
from ...core.types import ToolCall
from ...tools.claude_chrome import select_requested_tab
from ...tools.claude_chrome_translate import translate
from ...tools.permission_match import _tool_matches

ChromeCall = tuple[ToolCall, dict[str, object], PermissionRuleSet | None]


async def claude_chrome_call(
    call: ToolCall,
    args: ToolArgs,
    rules: PermissionRuleSet | None,
    context: ToolContext,
) -> ChromeCall | ToolResult | None:
    """İç çağrı; argüman/sekme hatasında başarısız sonuç; Claude aracı değilse `None`."""
    if claude_chrome_short(call.name) is None:
        return None
    translated = translate(call.name, args)
    if translated is None:
        return None  # yerel işlenir (computer wait, tarayıcı listesi)
    if isinstance(translated, str):
        return ToolResult.failure(translated)
    refused = await select_requested_tab(call.name, args, context)
    if refused is not None:
        return refused
    legacy, legacy_args = translated
    inner = replace(call, name=legacy, arguments=json.dumps(legacy_args, ensure_ascii=False))
    return inner, legacy_args, _mapped_rules(call.name, args, legacy, rules)


def _mapped_rules(
    name: str, args: ToolArgs, legacy: str, rules: PermissionRuleSet | None
) -> PermissionRuleSet | None:
    if rules is None or not rules.rules:
        return rules
    names = {name}
    batch = claude_chrome_short(name) == "browser_batch"
    if batch:
        names |= _batch_names(args)
    copies: list[PermissionRule] = []
    for rule in rules.rules:
        if not any(_tool_matches(rule, item) for item in names):
            continue
        if batch and rule.decision is PermissionDecision.ALLOW:
            continue
        targets = _batch_targets(args) if batch else {legacy}
        copies.extend(replace(rule, tool=target) for target in targets)
    return rules.with_rules((*rules.rules, *copies)) if copies else rules


def _batch_names(args: ToolArgs) -> set[str]:
    from ...core.claude_chrome_names import claude_chrome_name

    raw = args.get("actions")
    items = raw if isinstance(raw, list) else []
    return {
        claude_chrome_name(short)
        for item in items
        if isinstance(item, dict) and (short := claude_chrome_short(str(item.get("name", ""))))
    }


def _batch_targets(args: ToolArgs) -> set[str]:
    translated = translate("browser_batch", args)
    if not isinstance(translated, tuple):
        return set()
    steps = translated[1].get("actions")
    return (
        {str(step["name"]) for step in steps if isinstance(step, dict)}
        if isinstance(steps, list)
        else set()
    )
