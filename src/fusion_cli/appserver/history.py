"""Masaüstü protokolü için salt-okunur geçmiş servisleri.

Sunum ayrıntısı içermez. Kaynak adaptörlerini ortak HistorySource sözleşmesi
üzerinden çağırır; uygulama hiçbir Claude/Codex/Hermes dosyasını doğrudan açmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..history import available_sources, build_digest, source_by_name
from ..history.models import HistorySource, SessionRef, Turn

DEFAULT_LIMIT = 30
MAX_LIMIT = 100
MAX_CURSOR = 10_000


@dataclass(frozen=True, slots=True)
class PreparedResume:
    payload: dict[str, Any]
    digest: str


def list_sources(home: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "kaynaklar": [
            {"ad": source.name, "komut": f"/resume{source.name}"}
            for source in available_sources(home)
        ],
    }


def list_sessions(home: Path, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    source = _source(home, data)
    if source is None:
        return _missing_source(data)
    cursor, limit = _pagination(data)
    refs = source.list(root, limit=cursor + limit + 1)
    page = refs[cursor : cursor + limit]
    has_more = len(refs) > cursor + len(page)
    return {
        "ok": True,
        "kaynak": source.name,
        "oturumlar": [_serialize_ref(ref) for ref in page],
        "next_cursor": cursor + len(page) if has_more else None,
        "has_more": has_more,
    }


def preview_session(home: Path, data: dict[str, Any]) -> dict[str, Any]:
    source = _source(home, data)
    if source is None:
        return _missing_source(data)
    session_id = _session_id(data)
    if not session_id:
        return {"ok": False, "metin": "Oturum kimliği zorunludur."}
    cursor, limit = _pagination(data)
    turns = source.read(session_id, cursor=cursor, limit=limit + 1)
    page = turns[:limit]
    has_more = len(turns) > len(page)
    return {
        "ok": True,
        "kaynak": source.name,
        "oturum_id": session_id,
        "turlar": [_serialize_turn(turn) for turn in page],
        "next_cursor": cursor + len(page) if has_more else None,
        "has_more": has_more,
    }


def prepare_resume(home: Path, root: Path, data: dict[str, Any]) -> PreparedResume | dict[str, Any]:
    source = _source(home, data)
    if source is None:
        return _missing_source(data)
    session_id = _session_id(data)
    if not session_id:
        return {"ok": False, "metin": "Oturum kimliği zorunludur."}
    ref = next(
        (candidate for candidate in source.list(root) if candidate.session_id == session_id), None
    )
    if ref is None:
        return {"ok": False, "metin": "Seçilen geçmiş oturumu bulunamadı."}
    digest = build_digest(source, ref)
    return PreparedResume(
        payload={
            "ok": True,
            "kaynak": source.name,
            "oturum_id": ref.session_id,
            "baslik": ref.title,
            "sir_sayisi": digest.secret_count,
        },
        digest=digest.text,
    )


def _source(home: Path, data: dict[str, Any]) -> HistorySource | None:
    name = data.get("kaynak")
    return source_by_name(home, name) if isinstance(name, str) and name.strip() else None


def _missing_source(data: dict[str, Any]) -> dict[str, Any]:
    name = str(data.get("kaynak", "")).strip() or "istenen"
    return {"ok": False, "metin": f"{name} geçmiş kaynağı bulunamadı."}


def _session_id(data: dict[str, Any]) -> str:
    value = data.get("oturum_id")
    return value.strip() if isinstance(value, str) else ""


def _pagination(data: dict[str, Any]) -> tuple[int, int]:
    cursor_value = data.get("cursor", 0)
    limit_value = data.get("limit", DEFAULT_LIMIT)
    cursor = (
        cursor_value if isinstance(cursor_value, int) and not isinstance(cursor_value, bool) else 0
    )
    limit = (
        limit_value
        if isinstance(limit_value, int) and not isinstance(limit_value, bool)
        else DEFAULT_LIMIT
    )
    return min(max(cursor, 0), MAX_CURSOR), min(max(limit, 1), MAX_LIMIT)


def _serialize_ref(ref: SessionRef) -> dict[str, Any]:
    return {
        "kaynak": ref.source,
        "oturum_id": ref.session_id,
        "baslik": ref.title,
        "guncellendi": ref.updated_at,
        "tur_sayisi": ref.turn_count,
        "boyut": ref.size_bytes,
    }


def _serialize_turn(turn: Turn) -> dict[str, Any]:
    return {"rol": turn.role, "metin": turn.text, "zaman": turn.timestamp}
