"""Bounded desktop presentation; engine verification and model history stay unchanged."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from typing import TYPE_CHECKING

from ..core.redaction import redact
from ..core.text_fold import fold_tr
from ..engines.agent.completion_evidence import evidence_payload
from ..engines.agent.response_format import requested_response_format
from ..engines.agent.teacher_plan import short_static_report_output
from ..engines.agent.turn_report import summarize_evidence

if TYPE_CHECKING:
    from ..engines.agent.loop import AgentOutcome

MAX_BYTES = 32 * 1024
MAX_TEXT = 500
_DETAILS = {"kontroller": 10, "olculmeyen": 10, "oneriler": 10, "degisiklik_ozeti": 50}
_LISTS = {"degisen": 50, "sorunlar": 10, "uyarilar": 10, **_DETAILS}
_BOOLS = (
    "engelliyor",
    "yanlis_iddia",
    "degisen_kisaltildi",
    "sorunlar_kisaltildi",
    "criteria_truncated",
    "ayrintilar_kisaltildi",
)
_COUNTS = ("degisen_sayisi", "sorun_sayisi", "criteria_count")
_EXPLICIT_DETAILS = re.compile(
    r"\b(?:diff|audit|evidence|proof|verification|kanıt\w*|denetim\w*|satır\s+fark\w*)\b"
)
_EXPLICIT_CODE = re.compile(
    r"\b(?:show|include|display|return|give)\b[^.!?\n]{0,100}\b(?:source\s+code|code\s+changes|code)\b"
    r"|\b(?:reply|answer|response|cevab\w*|yanıt\w*)\b[^.!?\n]{0,100}\b(?:code|kod\w*)\b"
    r"|\b(?:html\s+)?kod(?:u|unu|ları|larını|lar|daki)?\b[^.!?\n]{0,60}\b(?:göster|ekle|ver|yaz)\w*"
)


@dataclass(frozen=True)
class DeliveryPresentation:
    text: str
    evidence: dict[str, object] | None
    compact: bool = False


def _invalid(value: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "dogrulandi": None,
        "engelliyor": True,
        "yanlis_iddia": isinstance(value, dict) and value.get("yanlis_iddia") is True,
        "degisen": [],
        "degisen_sayisi": 0,
        "sorunlar": ["Kanıt özeti okunamadı."],
        "sorun_sayisi": 1,
    }


def _warnings_preserved(warnings: Sequence[str], projected: Mapping[str, object]) -> bool:
    """Compact delivery is safe only when every public warning remains complete."""
    return (
        len(warnings) <= _LISTS["uyarilar"]
        and all(len(item) <= MAX_TEXT for item in warnings)
        and projected.get("uyarilar", []) == [redact(item) for item in warnings]
    )


def public_delivery_evidence(value: object) -> dict[str, object] | None:
    """Malformed journal metadata cannot break replay or claim verified success."""
    try:
        return _project_delivery_evidence(value)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return _invalid(value)


def _project_delivery_evidence(value: object) -> dict[str, object] | None:
    """Whitelist and bound completion metadata without weakening failure signals."""
    if value is None:
        return None
    if not isinstance(value, dict):
        return _invalid(value)
    version = value.get("schema_version")
    if type(version) is not int or version != 1:
        # Preserve an unsupported version for the existing defensive UI decoder.
        return (
            {"schema_version": version}
            if type(version) is int and 0 <= version <= 2**53 - 1
            else _invalid(value)
        )
    if any(key not in value for key in ("dogrulandi", "degisen", "sorunlar")):
        return _invalid(value)
    if value.get("dogrulandi") is not None and type(value.get("dogrulandi")) is not bool:
        return _invalid(value)
    if any(type(value.get(key)) is not bool for key in ("engelliyor", "yanlis_iddia")):
        return _invalid(value)
    result: dict[str, object] = {"schema_version": 1, "dogrulandi": value.get("dogrulandi")}
    shortened = value.get("ayrintilar_kisaltildi") is True
    for key in _BOOLS:
        if key in value:
            if type(value[key]) is not bool:
                return _invalid(value)
            result[key] = value[key]
    for key in _COUNTS:
        if key in value:
            number = value[key]
            if type(number) is not int or number < 0 or number > 2**53 - 1:
                return _invalid(value)
            result[key] = number
    for key, limit in _LISTS.items():
        if key not in value and key not in {"degisen", "sorunlar"}:
            continue
        items = value.get(key, [])
        if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
            return _invalid(value)
        shortened |= len(items) > limit
        if key == "degisen":
            # A shortened or rewritten path could open a different file.
            paths = [item for item in items[:limit] if redact(item) == item]
            shortened |= len(paths) != len(items[:limit])
            result[key] = paths
            if len(paths) != len(items):
                result["degisen_kisaltildi"] = True
        else:
            shortened |= any(len(item) > MAX_TEXT for item in items[:limit])
            result[key] = [redact(item)[:MAX_TEXT] for item in items[:limit]]
        if len(items) > limit and key in {"degisen", "sorunlar"}:
            result["degisen_kisaltildi" if key == "degisen" else "sorunlar_kisaltildi"] = True
    for count, items in (("degisen_sayisi", "degisen"), ("sorun_sayisi", "sorunlar")):
        original = value.get(items, [])
        count_value = result.get(count)
        if not isinstance(count_value, int) or count_value < len(original):
            return _invalid(value)
    kind = value.get("teslim_turu")
    if isinstance(kind, str) and kind in {"code", "artifact", "observation"}:
        result["teslim_turu"] = kind
    elif "teslim_turu" in value:
        return _invalid(value)
    criteria = value.get("criteria")
    if "criteria" in value:
        if not isinstance(criteria, list):
            return _invalid(value)
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get("status"), str)
            or item["status"] not in {"passed", "failed", "unverified"}
            for item in criteria
        ):
            return _invalid(value)
        if result.get("dogrulandi") is True and any(
            item["status"] != "passed" for item in criteria
        ):
            result["dogrulandi"] = (
                False if any(item["status"] == "failed" for item in criteria) else None
            )
        if result.get("engelliyor") is False and any(
            item["status"] == "failed" for item in criteria
        ):
            result["engelliyor"] = True
        shortened |= len(criteria) > 50
        if len(criteria) > 50:
            result["criteria_truncated"] = True
        projected = []
        for item in criteria[:50]:
            safe: dict[str, object] = {
                key: redact(item[key])[:MAX_TEXT]
                for key in ("criterion_id", "step_id", "summary", "source_digest", "call_id")
                if isinstance(item.get(key), str)
            }
            safe.update(
                status=item["status"],
                applicable=item.get("applicable") is True,
                text_truncated=item.get("text_truncated") is True,
            )
            projected.append(safe)
        result["criteria"] = projected
    counts = value.get("criteria_status_counts")
    if "criteria_status_counts" in value:
        if not isinstance(counts, dict) or not all(
            type(counts.get(key)) is int and 0 <= counts[key] <= 2**53 - 1
            for key in ("passed", "failed", "unverified")
        ):
            return _invalid(value)
        result["criteria_status_counts"] = {
            key: counts[key] for key in ("passed", "failed", "unverified")
        }
        # Summary counts remain authoritative even if their detail list is
        # missing/truncated. Never turn missing details into verified success.
        if counts["failed"]:
            result.update(dogrulandi=False, engelliyor=True)
        elif counts["unverified"] and result.get("dogrulandi") is True:
            result["dogrulandi"] = None
    if result.get("sorun_sayisi", 0):
        result.update(dogrulandi=False, engelliyor=True)
    represented = (
        sum(counts[key] for key in ("passed", "failed", "unverified"))
        if isinstance(counts, dict)
        else len(criteria or [])
    )
    criteria_total = result.get("criteria_count")
    if represented > 2**53 - 1 or (
        isinstance(criteria_total, int)
        and (criteria_total < represented or criteria_total < len(criteria or []))
    ):
        return _invalid(value)
    if (
        isinstance(criteria_total, int)
        and criteria_total > represented
        and result.get("dogrulandi") is True
    ):
        result["dogrulandi"] = None
    tamper = value.get("supheli_test_degisikligi")
    if "supheli_test_degisikligi" in value:
        if not isinstance(tamper, dict) or any(
            type(tamper.get(k)) is not int or not 0 <= tamper[k] <= 2**53 - 1
            for k in ("adet", "zayiflatan")
        ):
            return _invalid(value)
        if tamper["zayiflatan"] > tamper["adet"]:
            return _invalid(value)
        safe_tamper: dict[str, object] = {k: tamper[k] for k in ("adet", "zayiflatan")}
        for key in ("turler", "yollar"):
            items = tamper.get(key, [])
            if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                return _invalid(value)
            safe_tamper[key] = [redact(item)[:MAX_TEXT] for item in items[:50]]
        result["supheli_test_degisikligi"] = safe_tamper
        if tamper["zayiflatan"] and value.get("dogrulandi") is True:
            return _invalid(value)
        if tamper["adet"] and result.get("dogrulandi") is True:
            result["dogrulandi"] = None
    warnings_preserved = _warnings_preserved(value.get("uyarilar", []), result)
    shortened |= not warnings_preserved
    changed_paths = result.get("degisen")
    if not isinstance(changed_paths, list):
        return _invalid(value)
    if (
        value.get("sunum") == "document"
        and result.get("dogrulandi") is True
        and result.get("engelliyor") is False
        and result.get("yanlis_iddia") is False
        and not result.get("sorunlar")
        and warnings_preserved
        and not result.get("olculmeyen")
        and not tamper
        and result.get("degisen_sayisi") == 1
        and len(changed_paths) == 1
        and PurePath(str(changed_paths[0])).suffix.lower()
        in {".html", ".htm", ".md", ".txt", ".rst"}
    ):
        result["sunum"] = "document"
    for key in ("degisiklik_ozeti", "oneriler", "kontroller", "criteria"):
        items = result.get(key)
        while (
            isinstance(items, list)
            and items
            and len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_BYTES - 64
        ):
            items.pop()
            shortened = True
    while (
        changed_paths
        and len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_BYTES - 64
    ):
        changed_paths.pop()
        result["degisen_kisaltildi"] = True
        shortened = True
    if result.get("sunum") == "document" and len(changed_paths) != 1:
        result.pop("sunum")
    if shortened:
        result["ayrintilar_kisaltildi"] = True
    return (
        result
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) <= MAX_BYTES
        else _invalid(value)
    )


def present_delivery(task: str, outcome: AgentOutcome) -> DeliveryPresentation:
    """Only separate an exact generated prefix from a fully measured document delivery."""
    report = getattr(outcome, "completion_report", None)
    payload = evidence_payload(report)
    if report is None:
        return DeliveryPresentation(outcome.final_text, None)
    summary = summarize_evidence(report)
    if payload is not None:
        payload.update(
            kontroller=list(summary.verified),
            olculmeyen=list(summary.unmeasured),
            oneriler=list(report.gate.advisories if report.gate else ()),
            degisiklik_ozeti=list(report.change_lines),
        )
    projected = public_delivery_evidence(payload)
    safe = (
        outcome.ok
        and not outcome.budget_stopped
        and not outcome.hit_step_limit
        and requested_response_format(task) is None
        and not _EXPLICIT_DETAILS.search(fold_tr(task))
        and not _EXPLICIT_CODE.search(fold_tr(task))
        and report.is_verified is True
        and not report.blocks_success
        and not report.false_claim
        and not report.job_deliveries
        and not report.test_tamper
        and not summary.unmeasured
        and report.gate is not None
        and projected is not None
        and _warnings_preserved(report.gate.warnings, projected)
        and len(report.changed_paths) == 1
        and short_static_report_output(task) == report.changed_paths[0].removeprefix("./")
        and payload is not None
    )
    prefix = report.render()
    remainder = (
        outcome.final_text[len(prefix) :]
        if prefix and outcome.final_text.startswith(prefix)
        else ""
    )
    if safe and remainder.strip() and not remainder.lstrip().startswith(("⚠", "Ajanın açıklaması")):
        assert payload is not None
        payload["sunum"] = "document"
        evidence = public_delivery_evidence(payload)
        if evidence is not None and evidence.get("sunum") == "document":
            return DeliveryPresentation(remainder.strip(), evidence, True)
    return DeliveryPresentation(outcome.final_text, projected)
