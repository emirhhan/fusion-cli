"""Otomatik kip denetçisinin (P-011) kullanıcı metinleri: olay satırı ve durum ekranı.

REPL, TUI, `fusion auto-mode` ve masaüstü RPC'si aynı metni buradan alır.
"""

from __future__ import annotations

from ..core.auto_review import (
    AUTO_REVIEW_CONSECUTIVE_LIMIT,
    AUTO_REVIEW_MODEL_FAILURE_LIMIT,
    AUTO_REVIEW_TOTAL_LIMIT,
    AutoClassifierMode,
    AutoReviewSnapshot,
    ReviewOutcome,
    ReviewSource,
    ReviewVerdict,
)
from ..core.events import AutoReviewDecided
from . import messages


def verdict_label(verdict: ReviewVerdict) -> str:
    return messages.AUTO_REVIEW_VERDICT_LABELS.get(verdict.value, verdict.value)


def source_label(source: ReviewSource) -> str:
    return messages.AUTO_REVIEW_SOURCE_LABELS.get(source.value, source.value)


def decided_line(event: AutoReviewDecided) -> str:
    """Akışta tek satır: kim karar verdi, ne dedi, neden."""
    return messages.AUTO_REVIEW_DECIDED.format(
        source=source_label(event.source),
        verdict=verdict_label(event.verdict),
        summary=event.summary,
        reason=event.reason,
    )


def setting_label(setting: AutoClassifierMode) -> str:
    value = setting.value
    return f"{value} — {messages.AUTO_REVIEW_SETTING_LABELS.get(value, value)}"


def status_text(
    snapshot: AutoReviewSnapshot, setting: AutoClassifierMode, model: str, *, recent: int = 5
) -> str:
    """`/auto-mode` ve `fusion auto-mode durum` ekranı. `model`: görünen denetçi modeli."""
    offline = snapshot.model_failures >= AUTO_REVIEW_MODEL_FAILURE_LIMIT
    head = messages.AUTO_REVIEW_STATUS.format(
        setting=setting_label(setting),
        model=model,
        consecutive=snapshot.consecutive,
        consecutive_limit=AUTO_REVIEW_CONSECUTIVE_LIMIT,
        total=snapshot.total,
        total_limit=AUTO_REVIEW_TOTAL_LIMIT,
        trips=snapshot.trips,
        fell_back=messages.AUTO_REVIEW_STATUS_FELL_BACK.format(reason=snapshot.last_trip_reason)
        if snapshot.fell_back
        else "",
        offline=messages.AUTO_REVIEW_STATUS_OFFLINE if offline else "",
    )
    items = snapshot.recent[-recent:] if recent > 0 else ()
    if not items:
        return head
    return "\n".join([head, messages.AUTO_REVIEW_STATUS_RECENT, *map(outcome_line, items)])


def outcome_line(outcome: ReviewOutcome) -> str:
    return messages.AUTO_REVIEW_STATUS_RECENT_LINE.format(
        verdict=verdict_label(outcome.verdict),
        source=source_label(outcome.source),
        tool=outcome.tool,
        summary=outcome.summary,
        reason=outcome.reason,
    )
