"""Kanca çıktısını karara çevirme (P-009) — Claude Code'un çıkış kodu / JSON sözleşmesi.

    çıkış 0     stdout JSON ise alanları okunur; düz metin UserPromptSubmit/SessionStart'ta
                modele bağlam olur, ötekilerde yok sayılır
    çıkış 2     engeller (engelleyebilen olaylarda); stderr gerekçedir ve modele gider
    diğer       engellemez; stderr kullanıcıya hata olarak gösterilir

JSON alanları: `continue` (false = tur durur, `stopReason`), `systemMessage` (kullanıcıya),
`decision: block|approve` + `reason`, `hookSpecificOutput` içinde `permissionDecision`
(`allow|deny|ask`), `permissionDecisionReason`, `updatedInput`, `updatedToolOutput`,
`additionalContext`. Birden çok kanca birleşirken en kısıtlayıcı kazanır.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace

from .events import BLOCKING_EVENTS, STDOUT_CONTEXT_EVENTS, HookEvent, HookRun, HookVerdict

#: Kancanın modele ekleyebileceği bağlam üst sınırı (Claude: 10.000 karakter).
HOOK_CONTEXT_CHARS = 10_000
#: Kullanıcıya gösterilen hata kuyruğu uzunluğu.
HOOK_ERROR_CHARS = 600
#: Engelleyici çıkış kodu.
BLOCK_EXIT_CODE = 2

_PERMISSIONS = ("allow", "ask")
_STRICTNESS = {"deny": 0, "ask": 1, "allow": 2}


def verdict_from_run(event: HookEvent, run: HookRun) -> HookVerdict:
    """Tek bir komutun sonucunu karara çevir."""
    label = _label(run)
    if run.error is not None:
        return HookVerdict(errors=(f"{label}: çalıştırılamadı ({run.error})",), ran=1)
    if run.timed_out:
        return HookVerdict(
            errors=(f"{label}: {run.command.timeout_s:g} sn'de bitmedi, durduruldu",), ran=1
        )
    stderr = run.stderr.strip()
    if run.exit_code == BLOCK_EXIT_CODE:
        if event in BLOCKING_EVENTS:
            reason = stderr[-HOOK_CONTEXT_CHARS:] or f"{label} çıkış 2 ile engelledi"
            return HookVerdict(blocked=True, reason=reason, ran=1)
        return HookVerdict(errors=(f"{label}: {stderr[-HOOK_ERROR_CHARS:]}".rstrip(": "),), ran=1)
    if run.exit_code != 0:
        tail = f"\n{stderr[-HOOK_ERROR_CHARS:]}" if stderr else ""
        return HookVerdict(errors=(f"{label}: çıkış kodu {run.exit_code}{tail}",), ran=1)
    stdout = run.stdout.strip()
    if stdout.startswith("{"):
        try:
            payload = json.loads(stdout)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            return replace(_from_json(event, payload), ran=1)
    if stdout and event in STDOUT_CONTEXT_EVENTS:
        return HookVerdict(additional_context=(stdout[:HOOK_CONTEXT_CHARS],), ran=1)
    return HookVerdict(ran=1)


def _from_json(event: HookEvent, payload: Mapping[str, object]) -> HookVerdict:
    specific = payload.get("hookSpecificOutput")
    specific = specific if isinstance(specific, Mapping) else {}
    verdict = HookVerdict()
    if payload.get("continue") is False:
        verdict = replace(verdict, halt=True, stop_reason=_text(payload.get("stopReason")))
    message = _text(payload.get("systemMessage"))
    if message:
        verdict = replace(verdict, system_messages=(message,))
    reason = _text(payload.get("reason"))
    decision = payload.get("decision")
    if decision == "block" and event in BLOCKING_EVENTS:
        verdict = replace(verdict, blocked=True, reason=reason or "kanca engelledi")
    elif decision == "approve" and event is HookEvent.PRE_TOOL_USE:
        verdict = replace(verdict, permission="allow")
    if event is HookEvent.PRE_TOOL_USE:
        verdict = _pre_tool_fields(verdict, specific)
    output = specific.get("updatedToolOutput")
    if isinstance(output, str) and event is HookEvent.POST_TOOL_USE:
        verdict = replace(verdict, updated_output=output)
    context = _text(specific.get("additionalContext"))
    if context:
        verdict = replace(verdict, additional_context=(context[:HOOK_CONTEXT_CHARS],))
    return verdict


def _pre_tool_fields(verdict: HookVerdict, specific: Mapping[str, object]) -> HookVerdict:
    decision = specific.get("permissionDecision")
    reason = _text(specific.get("permissionDecisionReason"))
    if decision == "deny":
        verdict = replace(verdict, blocked=True, reason=reason or "kanca yasakladı")
    elif decision in _PERMISSIONS:
        verdict = replace(verdict, permission=str(decision), reason=reason)
    updated = specific.get("updatedInput")
    if isinstance(updated, Mapping):
        verdict = replace(verdict, updated_input=dict(updated))
    return verdict


def merge_verdicts(verdicts: Iterable[HookVerdict]) -> HookVerdict:
    """Birden çok kancanın kararı: engel/durdurma herhangi birinden; izin en kısıtlayıcı."""
    merged = HookVerdict()
    for item in verdicts:
        merged = HookVerdict(
            blocked=merged.blocked or item.blocked,
            reason=_join(merged.reason, item.reason if item.blocked else ""),
            permission=_stricter(merged.permission, item.permission),
            updated_input=item.updated_input
            if item.updated_input is not None
            else merged.updated_input,
            updated_output=item.updated_output
            if item.updated_output is not None
            else merged.updated_output,
            additional_context=merged.additional_context + item.additional_context,
            system_messages=merged.system_messages + item.system_messages,
            halt=merged.halt or item.halt,
            stop_reason=_join(merged.stop_reason, item.stop_reason),
            errors=merged.errors + item.errors,
            ran=merged.ran + item.ran,
        )
    return merged


def _stricter(first: str | None, second: str | None) -> str | None:
    if first is None:
        return second
    if second is None:
        return first
    return first if _STRICTNESS[first] <= _STRICTNESS[second] else second


def _join(first: str, second: str) -> str:
    return "\n".join(part for part in (first, second) if part)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _label(run: HookRun) -> str:
    command = run.command.command
    short = command if len(command) <= 60 else command[:57] + "…"
    return f"{run.command.event.value} kancası `{short}`"
