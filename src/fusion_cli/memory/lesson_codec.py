"""Chroma ders metadata kodlayıcısı; eski kayıtlar göç gerektirmeden okunur."""

from __future__ import annotations

import json
from enum import Enum
from typing import TypeVar

from ..core.memory import DEFAULT_LESSON_CONFIDENCE, Lesson, LessonKind, LessonSource


def _to_metadata(lesson: Lesson, timestamp: float) -> dict[str, object]:
    """Dersi ChromaDB metadata'sına çevir. Güven/sayaç alanları burada kalıcılaşır."""
    return {
        # Ders METNİ burada saklanır: belge alanı artık görev bağlamını da
        # içerir ve doğrudan metin olarak okunamaz.
        "text": lesson.text[:2000],
        "task": lesson.task[:500],
        "kind": lesson.kind.value,
        "source": lesson.source.value,
        "confidence": float(lesson.confidence),
        "success_count": int(lesson.success_count),
        "failure_count": int(lesson.failure_count),
        "scope": lesson.scope[:100],
        "trigger": lesson.trigger[:200],
        "workspace": lesson.workspace[:500],
        # Chroma metadata yalnız skaler tutar; etiketler virgülle saklanır.
        "tags": ",".join(sorted(lesson.tags))[:300],
        # Chroma metadata skaler tutar; bayrak 0/1 saklanır (eski kayıtlarda alan yok = 0).
        "external": int(lesson.external),
        "timestamp": timestamp,
        "subject_key": lesson.subject_key,
        "applies_to": json.dumps(lesson.applies_to),
        "version": lesson.version,
        "supersedes": json.dumps(lesson.supersedes),
        "verified_at": lesson.verified_at,
        "quarantined": int(lesson.quarantined),
        "source_split": lesson.source_split,
        "evidence_refs": json.dumps(lesson.evidence_refs),
    }


def _to_lesson(document: str, metadata: dict[str, object], *, row_id: str = "") -> Lesson:
    # Geriye dönük uyumluluk: güven/sayaç alanları taşınmadan önce yazılmış eski
    # kayıtlar bu alanları içermez; makul varsayılanlarla okunur.
    return Lesson(
        text=str(metadata.get("text") or document),
        kind=_enum(LessonKind, metadata.get("kind"), LessonKind.SUCCESS),
        task=str(metadata.get("task", "")),
        source=_enum(LessonSource, metadata.get("source"), LessonSource.LEARNED),
        confidence=_number(float, metadata.get("confidence"), DEFAULT_LESSON_CONFIDENCE),
        success_count=_number(int, metadata.get("success_count"), 0),
        failure_count=_number(int, metadata.get("failure_count"), 0),
        scope=str(metadata.get("scope", "")),
        trigger=str(metadata.get("trigger", "")),
        workspace=str(metadata.get("workspace", "")),
        tags=tuple(t for t in str(metadata.get("tags", "")).split(",") if t),
        external=bool(_number(int, metadata.get("external"), 0)),
        id=row_id,
        subject_key=str(metadata.get("subject_key") or ""),
        applies_to=_string_tuple(metadata.get("applies_to")),
        version=str(metadata.get("version") or ""),
        supersedes=_string_tuple(metadata.get("supersedes")),
        verified_at=str(metadata.get("verified_at") or ""),
        quarantined=bool(_number(int, metadata.get("quarantined"), 0)),
        source_split=str(metadata.get("source_split") or ""),
        evidence_refs=_string_tuple(metadata.get("evidence_refs")),
    )


NumberT = TypeVar("NumberT", int, float)
EnumT = TypeVar("EnumT", bound=Enum)


def _number(kind: type[NumberT], raw: object, fallback: NumberT) -> NumberT:
    """Bozuk sayısal metadata tek kaydı değil bütün `recall`ı düşürürdü."""
    if not isinstance(raw, (int, float, str)):
        return fallback
    try:
        return kind(raw)
    except (TypeError, ValueError):
        return fallback


def _idle_seconds(metadata: dict[str, object], now: float) -> float:
    """Güvenin son güncellenmesinden geçen süre; zaman damgası yoksa 0 (yeniden deneme yok)."""
    try:
        return max(0.0, now - float(str(metadata["timestamp"])))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _enum(enum_type: type[EnumT], raw: object, fallback: EnumT) -> EnumT:
    """Bilinmeyen değer kaydı bozmaz; makul bir varsayılana düşülür."""
    try:
        return enum_type(str(raw))
    except ValueError:
        return fallback


def _string_tuple(raw: object) -> tuple[str, ...]:
    """Skaler JSON listesini doğrula; eski veya bozuk değerlerden köken uydurma."""
    if not isinstance(raw, str):
        return ()
    try:
        values = json.loads(raw)
    except (ValueError, TypeError):
        return ()
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        return ()
    return tuple(values)
