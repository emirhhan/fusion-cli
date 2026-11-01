"""Kanca çıktısını karara çevirme (P-009) — Claude Code'un çıkış kodu / JSON sözleşmesi.

    çıkış 0     stdout JSON ise alanları okunur; düz metin UserPromptSubmit/SessionStart'ta
                modele bağlam olur, ötekilerde yok sayılır
    çıkış 2     engeller (engelleyebilen olaylarda); gerekçe stderr ya da JSON `reason`'ı,
                JSON alanları yine okunur ama engeli kaldıramaz
    diğer       şemaya uyan JSON varsa çıkış kodu yok sayılır, alanlar karar verir; yoksa
                engellemeyen hata (`<Olay>:<eşleşen> hook error`, stderr'in ilk satırı)

`{` ile başlayıp `}` ile biten ama ayrıştırılamayan çıktı ve `hookEventName`'i eksik/yanlış
`hookSpecificOutput` şema hatasıdır: engellemez, bağlama EKLENMEZ. Birden çok kanca
birleşirken en kısıtlayıcı kazanır (izinde deny > defer > ask > allow).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import TypeVar

from .events import BLOCKING_EVENTS, STDOUT_CONTEXT_EVENTS, HookEvent, HookRun, HookVerdict
from .output import (
    DISCARDS_ALL_JSON,
    DISCARDS_CONTINUE,
    DISCARDS_SYSTEM_MESSAGE,
    IGNORES_EXIT_CODE,
    string_list,
    terminal_sequence,
    tool_output_text,
)

#: Kancanın modele ekleyebileceği bağlam üst sınırı (Claude: 10.000 karakter); aşan metin
#: oturum katmanında dosyaya yazılır (bkz. `engines/hooks/overflow.py`).
HOOK_CONTEXT_CHARS = 10_000
#: Engelleyici çıkış kodu.
BLOCK_EXIT_CODE = 2
#: Claude'un engellemeyen hata satırı.
NON_BLOCKING_STATUS = "Failed with non-blocking status code"

_T = TypeVar("_T")
_PERMISSIONS = ("allow", "ask", "defer")
_ELICITATION_ACTIONS = ("accept", "decline", "cancel")
_STRICTNESS = {"deny": 0, "defer": 1, "ask": 2, "allow": 3}
#: `watchPaths` okuyan olaylar (FileChanged izleme listesini değiştirir).
WATCH_PATH_EVENTS = frozenset(
    {HookEvent.SESSION_START, HookEvent.CWD_CHANGED, HookEvent.FILE_CHANGED}
)


def verdict_from_run(event: HookEvent, run: HookRun, subject: str = "") -> HookVerdict:
    """Tek bir komutun sonucunu karara çevir (`subject`: eşleşen değer, ör. araç adı)."""
    label = hook_label(event, subject)
    if event in IGNORES_EXIT_CODE:
        return _ignoring_exit(event, run)
    if run.error is not None:
        return _failure(f"{label} hook error: başlatılamadı ({run.error})")
    if run.timed_out:
        return _failure(f"{label} hook error: {run.command.timeout_s:g} sn'de bitmedi, durduruldu")
    payload, schema_error = _json_payload(event, run.stdout)
    if run.exit_code == BLOCK_EXIT_CODE:
        return _exit_two(event, run, label, payload)
    if schema_error is not None:
        return _failure(f"{label} hook error: {schema_error}")
    if payload is not None:
        return replace(_from_json(event, payload), ran=1)
    if run.exit_code != 0:
        return _failure(
            f"{label} hook error\n{NON_BLOCKING_STATUS}: {_first_line(run.stderr)}".rstrip(": ")
        )
    stdout = run.stdout.strip()
    if event is HookEvent.WORKTREE_CREATE:
        # Claude: komut kancası oluşturduğu ağacın yolunu stdout'a yazar.
        return HookVerdict(worktree_path=_last_line(stdout), ran=1)
    if stdout and event in STDOUT_CONTEXT_EVENTS:
        return HookVerdict(additional_context=(stdout,), ran=1)
    return HookVerdict(ran=1)


def hook_label(event: HookEvent, subject: str = "") -> str:
    """Claude'un kanca etiketi: `PreToolUse:Bash` (eşleşen değer yoksa yalnız olay)."""
    return f"{event.value}:{subject}" if subject else event.value


def is_failure(verdict: HookVerdict) -> bool:
    """`onFailure: block` için: kanca başarısız mı (başlatılamadı, ≠0/2, zaman aşımı, şema)?"""
    return bool(verdict.errors) and not verdict.blocked


def _failure(message: str) -> HookVerdict:
    return HookVerdict(errors=(message,), ran=1)


def _ignoring_exit(event: HookEvent, run: HookRun) -> HookVerdict:
    """Notification: çıkış kodu/stderr yok sayılır; yalnız JSON'un yan etki alanları."""
    payload, _ = _json_payload(event, run.stdout) if run.error is None else (None, None)
    if payload is None:
        return HookVerdict(ran=1)
    return replace(_from_json(event, payload), ran=1)


def _exit_two(
    event: HookEvent, run: HookRun, label: str, payload: Mapping[str, object] | None
) -> HookVerdict:
    stderr = run.stderr.strip()
    if event is HookEvent.PERMISSION_REQUEST:
        # Claude: kararsız çıkış 2 izin akışını değiştirmez, stderr atılır.
        fields = _from_json(event, payload) if payload is not None else HookVerdict()
        return replace(fields, ran=1)
    if event not in BLOCKING_EVENTS:
        return _failure(f"{label} hook error: {stderr}".rstrip(": "))
    fields = _from_json(event, payload) if payload is not None else HookVerdict()
    json_reason = fields.reason if fields.blocked else ""
    reason = json_reason or stderr or f"{label} çıkış 2 ile engelledi"
    permission = fields.permission if fields.permission in ("deny", "defer") else None
    return replace(
        fields,
        blocked=True,
        reason=reason,
        permission=permission,
        updated_input=None,
        block_source="" if json_reason else run.command.command,
        ran=1,
    )


def _json_payload(event: HookEvent, stdout: str) -> tuple[Mapping[str, object] | None, str | None]:
    """(geçerli JSON nesnesi, şema hatası). Düz metin ikisini de `None` döndürür."""
    text = stdout.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None, None
    try:
        payload = json.loads(text)
    except ValueError:
        return None, "JSON çıktısı ayrıştırılamadı"
    if not isinstance(payload, dict):
        return None, "JSON çıktısı nesne değil"
    specific = payload.get("hookSpecificOutput")
    if specific is not None:
        name = specific.get("hookEventName") if isinstance(specific, Mapping) else None
        if name != event.value:
            return None, f"hookSpecificOutput.hookEventName '{event.value}' olmalı"
    return payload, None


def _from_json(event: HookEvent, payload: Mapping[str, object]) -> HookVerdict:
    if event in DISCARDS_ALL_JSON:
        return HookVerdict()
    specific = payload.get("hookSpecificOutput")
    specific = specific if isinstance(specific, Mapping) else {}
    verdict = _universal_fields(event, payload)
    reason = _text(payload.get("reason"))
    decision = payload.get("decision")
    if decision == "block" and event in BLOCKING_EVENTS:
        verdict = replace(verdict, blocked=True, reason=reason or "kanca engelledi")
    elif decision == "approve" and event is HookEvent.PRE_TOOL_USE:
        verdict = replace(verdict, permission="allow")
    if event is HookEvent.PRE_TOOL_USE:
        verdict = _pre_tool_fields(verdict, specific)
    if event is HookEvent.POST_TOOL_USE:
        verdict = _post_tool_fields(verdict, specific)
    if event is HookEvent.PERMISSION_REQUEST:
        verdict = _permission_request_fields(verdict, specific)
    if event is HookEvent.PRE_MODEL_SWITCH:
        return _model_switch_fields(verdict, specific)
    if event is HookEvent.WORKTREE_CREATE:
        return replace(verdict, worktree_path=_text(specific.get("worktreePath")))
    if event is HookEvent.PERMISSION_DENIED:
        return replace(verdict, retry=specific.get("retry") is True)
    if event in (HookEvent.ELICITATION, HookEvent.ELICITATION_RESULT):
        return _elicitation_fields(verdict, specific)
    context = _text(specific.get("additionalContext"))
    if context and verdict.permission != "defer":
        verdict = replace(verdict, additional_context=(context,))
    return _session_fields(event, verdict, specific)


def _elicitation_fields(verdict: HookVerdict, specific: Mapping[str, object]) -> HookVerdict:
    """`action` accept|decline|cancel ve `content`; `action`'sız çıktı yok sayılır (Claude)."""
    action = specific.get("action")
    if action not in _ELICITATION_ACTIONS:
        return verdict
    content = specific.get("content")
    return replace(
        verdict,
        elicitation_action=str(action),
        elicitation_content=dict(content) if isinstance(content, Mapping) else None,
    )


def _model_switch_fields(verdict: HookVerdict, specific: Mapping[str, object]) -> HookVerdict:
    """PreModelSwitch: allow|deny|ask (`defer`, `updatedInput`, `additionalContext` yok)."""
    decision = specific.get("permissionDecision")
    reason = _text(specific.get("permissionDecisionReason"))
    if decision == "deny":
        return replace(verdict, blocked=True, permission="deny", reason=reason or "kanca reddetti")
    if decision in ("allow", "ask"):
        return replace(
            verdict, permission=str(decision), ask_reason=reason if decision == "ask" else ""
        )
    return verdict


def _universal_fields(event: HookEvent, payload: Mapping[str, object]) -> HookVerdict:
    verdict = HookVerdict()
    if payload.get("continue") is False and event not in DISCARDS_CONTINUE:
        verdict = replace(verdict, halt=True, stop_reason=_text(payload.get("stopReason")))
    message = _text(payload.get("systemMessage"))
    if message and event not in DISCARDS_SYSTEM_MESSAGE:
        verdict = replace(verdict, system_messages=(message,))
    sequence = terminal_sequence(payload.get("terminalSequence"))
    if sequence is not None:
        verdict = replace(verdict, terminal_sequences=(sequence,))
    return verdict


def _pre_tool_fields(verdict: HookVerdict, specific: Mapping[str, object]) -> HookVerdict:
    decision = specific.get("permissionDecision")
    reason = _text(specific.get("permissionDecisionReason"))
    if decision == "deny":
        verdict = replace(
            verdict, blocked=True, permission="deny", reason=reason or "kanca yasakladı"
        )
    elif decision in _PERMISSIONS:
        ask_reason = reason if decision == "ask" else ""
        verdict = replace(verdict, permission=str(decision), ask_reason=ask_reason)
    updated = specific.get("updatedInput")
    if isinstance(updated, Mapping):
        verdict = replace(verdict, updated_input=dict(updated))
    return verdict


def _permission_request_fields(verdict: HookVerdict, specific: Mapping[str, object]) -> HookVerdict:
    """`decision.behavior` allow|deny; deny'da `message` gerekçe, `interrupt` turu durdurur."""
    decision = specific.get("decision")
    if not isinstance(decision, Mapping):
        return verdict
    behavior = decision.get("behavior")
    if behavior == "allow":
        updated = decision.get("updatedInput")
        return replace(
            verdict,
            permission="allow",
            updated_input=dict(updated) if isinstance(updated, Mapping) else None,
        )
    if behavior == "deny":
        message = _text(decision.get("message"))
        return replace(
            verdict,
            permission="deny",
            reason=message,
            halt=verdict.halt or decision.get("interrupt") is True,
        )
    return verdict


def _post_tool_fields(verdict: HookVerdict, specific: Mapping[str, object]) -> HookVerdict:
    output = tool_output_text(specific.get("updatedToolOutput"))
    if output is None:
        output = tool_output_text(specific.get("updatedMCPToolOutput"))
    if output is not None:
        verdict = replace(verdict, updated_output=output)
    classifier = _text(specific.get("classifierContext"))
    return replace(verdict, classifier_context=classifier) if classifier else verdict


def _session_fields(
    event: HookEvent, verdict: HookVerdict, specific: Mapping[str, object]
) -> HookVerdict:
    if event in (HookEvent.USER_PROMPT_SUBMIT, HookEvent.SESSION_START):
        verdict = replace(verdict, session_title=_text(specific.get("sessionTitle")))
    if event is HookEvent.USER_PROMPT_SUBMIT:
        suppress = specific.get("suppressOriginalPrompt") is True
        verdict = replace(verdict, suppress_original_prompt=suppress)
    if event is HookEvent.SESSION_START:
        verdict = replace(
            verdict,
            initial_user_message=_text(specific.get("initialUserMessage")),
            reload_skills=specific.get("reloadSkills") is True,
        )
    if event in WATCH_PATH_EVENTS and "watchPaths" in specific:
        verdict = replace(
            verdict, watch_paths=string_list(specific.get("watchPaths")), watch_paths_given=True
        )
    return verdict


def merge_verdicts(verdicts: Iterable[HookVerdict]) -> HookVerdict:
    """Birden çok kancanın kararı: engel/durdurma herhangi birinden; izin en kısıtlayıcı."""
    merged = HookVerdict()
    for item in verdicts:
        merged = HookVerdict(
            blocked=merged.blocked or item.blocked,
            reason=_join(
                merged.reason, item.reason if item.blocked or item.permission == "deny" else ""
            ),
            permission=_stricter(merged.permission, item.permission),
            updated_input=_last(merged.updated_input, item.updated_input),
            updated_output=_last(merged.updated_output, item.updated_output),
            additional_context=merged.additional_context + item.additional_context,
            system_messages=merged.system_messages + item.system_messages,
            halt=merged.halt or item.halt,
            stop_reason=_join(merged.stop_reason, item.stop_reason),
            errors=merged.errors + item.errors,
            ran=merged.ran + item.ran,
            block_source=merged.block_source or (item.block_source if item.blocked else ""),
            ask_reason=_join(merged.ask_reason, item.ask_reason),
            classifier_context=_join(merged.classifier_context, item.classifier_context),
            session_title=item.session_title or merged.session_title,
            suppress_original_prompt=merged.suppress_original_prompt
            or item.suppress_original_prompt,
            initial_user_message=item.initial_user_message or merged.initial_user_message,
            watch_paths=merged.watch_paths + item.watch_paths,
            watch_paths_given=merged.watch_paths_given or item.watch_paths_given,
            reload_skills=merged.reload_skills or item.reload_skills,
            terminal_sequences=merged.terminal_sequences + item.terminal_sequences,
            worktree_path=merged.worktree_path or item.worktree_path,
            retry=merged.retry or item.retry,
            elicitation_action=item.elicitation_action or merged.elicitation_action,
            elicitation_content=item.elicitation_content
            if item.elicitation_action
            else merged.elicitation_content,
        )
    return merged


def _last(first: _T | None, second: _T | None) -> _T | None:
    return second if second is not None else first


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


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _first_line(text: str) -> str:
    stripped = text.strip()
    return stripped.splitlines()[0] if stripped else ""
