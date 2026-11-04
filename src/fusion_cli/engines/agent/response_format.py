"""Preserve explicitly requested output formats without inventing answer contents."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Literal, NoReturn

from ...core.redaction import redact
from ...core.text_fold import fold_tr
from ...ui.text import strip_thinking
from .completion_evidence import evidence_payload

if TYPE_CHECKING:
    from .turn_report import TurnReport

_QUOTED = re.compile(
    r"```.*?```|`[^`]*`|\"[^\"\n]*\"|“[^”\n]*”|‘[^’\n]*’|"
    r"(?<!\w)'[^'\n]+'(?!\w)|^[ \t]*>[^\n]*",
    re.S | re.M,
)
_CLAUSE = re.compile(r"[.!?;\n]+|\b(?:ama|ancak|fakat|but|however)\b")
_ONLY = r"(?:sadece|yalnız|yalnızca|yalniz|yalnizca|only|exclusively|strictly)"
_JSON_OUTPUT = re.compile(
    rf"\b{_ONLY}\s+(?:in\s+)?(?:(?:geçerli|gecerli|valid)\s+)?json\b"
    r"(?=\s*(?:$|[:,]|(?:olarak|formatında|formatinda|olsun|yaz|ver|döndür|dondur|"
    r"with|containing|using)\b))"
    r"|\b(?:return|respond|answer|output|reply)\b.{0,30}\bjson\s+only\b"
)
_JSON_NEGATED = re.compile(
    r"\bjson\s+(?:(?:olarak|formatında|formatinda)\s+)?"
    r"(?:yazma|verme|döndürme|dondurme|olmasın|olmasin)\b"
    r"|\b(?:do not|don't|never)\s+(?:return|respond|answer|output|reply)\b"
    r"|\bnot\s+only\s+json\b"
)
_RESULT_OUTPUT = re.compile(
    rf"\b{_ONLY}\s+(?:sonucu|sonuç|sonuc|(?:the\s+)?result)\s*"
    r"(?:$|[:,]|(?:yaz|söyle|soyle|ver|döndür|dondur|olsun)\b)"
    r"|\b(?:return|output|give)\s+only\s+(?:the\s+)?result\b"
)
_RESULT_NEGATED = re.compile(
    r"\b(?:sonucu|sonuç|sonuc)\s+(?:yazma|söyleme|soyleme|verme|döndürme|dondurme)\b"
    r"|\b(?:do not|don't|never)\s+(?:return|output|give)\b"
    r"|\bnot\s+only\s+(?:the\s+)?result\b"
)
_FILE_TARGET = re.compile(r"\b(?:dosya\w*|file\w*)\b")
_REPLY_TARGET = re.compile(r"\b(?:yanıt\w*|yanit\w*|cevap\w*|return|respond|answer|reply)\b")


def requested_response_format(task: str) -> Literal["json", "minimal"] | None:
    """Recognize direct affirmative format requests, not examples or file names."""
    clauses = _CLAUSE.split(fold_tr(_QUOTED.sub(" ", task)))
    json_allowed, minimal_allowed = True, True
    for clause in reversed(clauses):
        if _JSON_NEGATED.search(clause):
            json_allowed = False
        if _RESULT_NEGATED.search(clause):
            minimal_allowed = False
        match = _JSON_OUTPUT.search(clause) if json_allowed else None
        if match:
            prefix = clause[: match.start()]
            if not _FILE_TARGET.search(prefix) or _REPLY_TARGET.search(prefix):
                return "json"
        if minimal_allowed and _RESULT_OUTPUT.search(clause):
            return "minimal"
    return None


def _non_json_constant(value: str) -> NoReturn:
    raise ValueError(f"Non-JSON constant: {value}")


def _json_error(code: str, message: str, report: TurnReport, *, details: str = "") -> str:
    # This is an explicitly identified harness error, not invented values for
    # the user's requested result schema. The original report stays authoritative.
    error: dict[str, object] = {
        "source": "fusion",
        "code": code,
        "message": message,
        "completion_evidence": evidence_payload(report),
    }
    if details:
        error["details"] = redact(details)[:2_000]
    return json.dumps({"error": error}, ensure_ascii=False)


def format_reported_response(
    task: str, text: str, report: TurnReport, *, successful: bool
) -> tuple[str, bool] | None:
    """Return a strict reply and success verdict, or retain ordinary report rendering.

    No facts are extracted, numeric substrings guessed, schema fields filled or
    failed verification promoted. Result-only prose is preserved as generated;
    this function prevents the harness from making its format worse.
    """
    requested = requested_response_format(task)
    if requested is None:
        return None
    text = strip_thinking(text).strip()
    if not successful or report.blocks_success:
        if requested != "json":
            return None  # A genuine failure must remain visible in ordinary prose.
        try:
            previous = json.loads(text, parse_constant=_non_json_constant)
        except (ValueError, RecursionError):
            previous = None
        error = previous.get("error") if isinstance(previous, dict) else None
        if (
            isinstance(error, dict)
            and error.get("source") == "fusion"
            and error.get("code")
            in {"verification_failed", "turn_failed", "invalid_response_format"}
            and error.get("completion_evidence") == evidence_payload(report)
        ):
            return text, False
        code = "verification_failed" if report.blocks_success else "turn_failed"
        return _json_error(code, "Tur başarıyla tamamlanmış kabul edilemez.", report), False
    if requested == "json":
        try:
            json.loads(text, parse_constant=_non_json_constant)
        except (ValueError, RecursionError):
            # Late harness disclosures must not be silently discarded to make
            # an earlier success object parse again. Retain the actual appended
            # warning in a bounded error; no result fields are extracted.
            details = ""
            try:
                _, end = json.JSONDecoder(parse_constant=_non_json_constant).raw_decode(text)
                details = text[end:].strip()
            except (ValueError, RecursionError):
                pass
            return (
                _json_error(
                    "invalid_response_format",
                    "Yanıt istenen geçerli JSON biçiminde değil.",
                    report,
                    details=details,
                ),
                False,
            )
    return text, True
