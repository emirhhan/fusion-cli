"""`PermissionDenied` kancası: otomatik kip denetçisi bir çağrıyı reddedince (Claude Code).

Claude: kanca yalnız auto kip sınıflandırıcısının reddinde çalışır; elle verilen ret,
PreToolUse engeli ve `deny` kuralı tetiklemez. Eşleştirici araç adıdır; girdi `tool_name`,
`tool_input`, `tool_use_id` ve `reason` (sınıflandırıcının gerekçesi). Çıkış kodu ve stderr
yok sayılır; `hookSpecificOutput.retry: true` modele çağrıyı yeniden deneyebileceğini söyler.

Fusion'da denetçinin "riskli" kararı etkileşimli oturumda kullanıcıya sorulur (soru ve
cevabı elle karardır); soru sorulamayan koşuda (`fusion agent`, `-p`) aynı karar çağrıyı
sormadan reddeder — kanca tam bu durumda çalışır.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...core.auto_review import ReviewSource, ReviewVerdict
from ...core.hooks.events import HookEvent
from .hook_bridge import session_of, tool_hook_fields

if TYPE_CHECKING:
    from .auto_guard import AutoReviewState
    from .loop import AgentDeps

#: `retry: true` dönünce reddin sonuna eklenen not (model yeniden deneyebilir).
RETRY_NOTE = "PermissionDenied kancası bu çağrının yeniden denenebileceğini bildirdi."


@dataclass(frozen=True, slots=True)
class ReviewMark:
    """Denetçiden geçmeden önceki sayaçlar; çağrının riskli sayılıp sayılmadığını ayırır."""

    total: int
    trips: int


def review_mark(guard: AutoReviewState | None) -> ReviewMark | None:
    return None if guard is None else ReviewMark(guard.total, guard.trips)


def classifier_reason(guard: AutoReviewState | None, mark: ReviewMark | None) -> str | None:
    """Bu çağrıda denetçi MODELİ "riskli" dediyse gerekçesi; demediyse `None`.

    Riskli model kararı `total`'ı artırır (eşik aşılırsa sayaç sıfırlanır, `trips` artar).
    """
    if guard is None or mark is None:
        return None
    if guard.total == mark.total and guard.trips == mark.trips:
        return None
    recent = guard.snapshot().recent
    if not recent:
        return None
    last = recent[-1]
    if last.verdict is not ReviewVerdict.RISKY or last.source is ReviewSource.RULE:
        return None
    return last.reason


async def permission_denied(
    deps: AgentDeps,
    tool_name: str,
    args: Mapping[str, object],
    call_id: str,
    *,
    reason: str,
    message: str,
) -> str:
    """Kancayı çalıştır; modele gidecek ret metnini (gerekirse yeniden deneme notuyla) döndür."""
    session = session_of(deps)
    if session is None or getattr(deps, "interactive", False):
        return message
    if not session.has(HookEvent.PERMISSION_DENIED):
        return message
    root = session.project_dir or session.root
    fields = tool_hook_fields(tool_name, args, call_id, root=root, deps=deps)
    fields["reason"] = reason
    verdict = await session.emit(
        HookEvent.PERMISSION_DENIED,
        subjects=(str(fields["tool_name"]),),
        fields=fields,
        target=(tool_name, args),
    )
    return f"{message}\n{RETRY_NOTE}" if verdict.retry else message
