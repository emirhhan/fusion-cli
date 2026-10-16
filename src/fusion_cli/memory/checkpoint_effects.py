"""Dış işlem intent metadata'sının sıkı checkpoint kodlayıcısı."""

from __future__ import annotations

from ..core.effects import EffectPhase, ExternalEffectIntent
from ..core.tools import AuthorizationScope, ToolEffect


def effects_payload(values: tuple[ExternalEffectIntent, ...]) -> list[dict[str, object]]:
    return [
        {
            "step_id": item.step_id,
            "attempt": item.attempt,
            "call_id": item.call_id,
            "tool_name": item.tool_name,
            "effect": item.effect.value,
            "phase": item.phase.value,
            "scope": {
                "server": item.scope.server,
                "account": item.scope.account,
                "action": item.scope.action,
                "targets": list(item.scope.targets),
            }
            if item.scope
            else None,
        }
        for item in values
    ]


def _text(value: dict[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError("Dış işlem intent kimliği geçersiz.")
    return result


def parse_effects(value: object) -> tuple[ExternalEffectIntent, ...]:
    if not isinstance(value, list):
        raise ValueError("Dış işlem intent listesi geçersiz.")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Dış işlem intent kaydı geçersiz.")
        attempt = item.get("attempt")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("Dış işlem deneme kimliği geçersiz.")
        scope = item.get("scope")
        parsed_scope = None
        if scope is not None:
            if not isinstance(scope, dict) or not isinstance(scope.get("targets"), list):
                raise ValueError("Dış işlem kapsamı geçersiz.")
            targets = scope["targets"]
            if not all(isinstance(target, str) and target for target in targets):
                raise ValueError("Dış işlem hedefi geçersiz.")
            parsed_scope = AuthorizationScope(
                _text(scope, "server"),
                _text(scope, "account"),
                _text(scope, "action"),
                tuple(targets),
            )
            if not parsed_scope.is_complete:
                raise ValueError("Dış işlem kapsamı eksik.")
        effect = ToolEffect(_text(item, "effect"))
        if effect not in {ToolEffect.REMOTE_WRITE, ToolEffect.REMOTE_DESTRUCTIVE}:
            raise ValueError("Dış işlem etkisi geçersiz.")
        result.append(
            ExternalEffectIntent(
                _text(item, "step_id"),
                attempt,
                _text(item, "call_id"),
                _text(item, "tool_name"),
                effect,
                parsed_scope,
                EffectPhase(_text(item, "phase")),
            )
        )
    keys = {(item.step_id, item.attempt, item.call_id) for item in result}
    if len(keys) != len(result):
        raise ValueError("Yinelenen dış işlem intent kimliği.")
    return tuple(result)
