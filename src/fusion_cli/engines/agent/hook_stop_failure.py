"""`StopFailure` kancası: tur API hatasıyla bitince `Stop` yerine (Claude Code).

Eşleştirici `error` türüdür. Çıktı ve çıkış kodu yok sayılır (yalnız `terminalSequence`
uygulanır); kanca günlük/uyarı içindir. `last_assistant_message` kullanıcıya gösterilen
hata metnidir.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...core.hooks.events import HookEvent
from .hook_bridge import session_of

if TYPE_CHECKING:
    from .loop import AgentDeps

#: Ham sağlayıcı hatasından Claude'un `error` türüne (sıra önemli: ilk eşleşen kazanır).
_ERROR_TYPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rate_limit", re.compile(r"\b429\b|rate.?limit|too many requests|kota aşıldı", re.I)),
    ("overloaded", re.compile(r"\b529\b|overload", re.I)),
    ("billing_error", re.compile(r"billing|credit|insufficient.?(funds|quota)|payment", re.I)),
    (
        "authentication_failed",
        re.compile(r"\b401\b|\b403\b|auth|api.?key|unauthori[sz]ed|kimlik", re.I),
    ),
    ("model_not_found", re.compile(r"model.{0,40}(not.?found|does not exist)|\b404\b", re.I)),
    ("max_output_tokens", re.compile(r"max.?(output.?)?tokens|length limit", re.I)),
    ("invalid_request", re.compile(r"\b400\b|invalid.?request|bad request", re.I)),
    ("server_error", re.compile(r"\b5\d\d\b|server error|internal error|timeout|timed out", re.I)),
)


def error_type(raw: str) -> str:
    """Claude `error` değeri: rate_limit, overloaded, … ya da `unknown`."""
    for name, pattern in _ERROR_TYPES:
        if pattern.search(raw):
            return name
    return "unknown"


async def stop_failure(deps: AgentDeps, model_error: str, shown: str) -> None:
    """Turun API hatasıyla bittiğini kancalara bildir (karar okunmaz)."""
    session = session_of(deps)
    if session is None or not model_error:
        return
    kind = error_type(model_error)
    fields: dict[str, object] = {
        "error": kind,
        "error_details": model_error[:2000],
        "last_assistant_message": shown or model_error[:2000],
    }
    await session.emit(HookEvent.STOP_FAILURE, subjects=(kind,), fields=fields)
