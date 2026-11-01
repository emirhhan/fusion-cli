"""Masaüstü protokolü için salt-okunur geçmiş servisleri.

Sunum ayrıntısı içermez. Kaynak adaptörlerini ortak HistorySource sözleşmesi
üzerinden çağırır; uygulama hiçbir Claude/Codex/Hermes dosyasını doğrudan açmaz.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.types import Message
from ..history import available_sources, build_digest, source_by_name
from ..history.models import HistorySource, SessionRef, Turn
from ..history.sanitize import sanitize_title, sanitize_turns
from ..history.search import SessionMatch
from ..history.search import search_sessions as _search_sessions
from ..history.work_dirs import codex_work_dirs

DEFAULT_LIMIT = 30
MAX_LIMIT = 100
MAX_CURSOR = 10_000

#: Devralmada modele verilen mesaj sayısı (oturumun SONU), tarama sayfa boyu ve
#: `turn_count`'tan geriye bakılan pencere.
RESUME_MESSAGE_LIMIT = 100
RESUME_PAGE_SIZE = 200
RESUME_TAIL_WINDOW = 400

#: Arama sonucu tek sayfada döner; seçici bunu ayrıca sayfalamaz.
SEARCH_LIMIT = 30

_EMPTY_QUERY = "Arama için en az bir karakter yazın."


@dataclass(frozen=True, slots=True)
class PreparedResume:
    payload: dict[str, Any]
    digest: str
    messages: tuple[Message, ...]
    #: Devralınan oturumun çalıştığı, proje kökünün dışındaki klasörler.
    work_dirs: tuple[Path, ...] = ()


def list_sources(home: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "kaynaklar": [
            {"ad": source.name, "komut": f"/import history {source.name}"}
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


def search_sessions(home: Path, root: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Kaynağın TAMAMINDA ara; seçicinin elindeki sayfada değil.

    `list_sessions` ile aynı künye şemasını döndürür, üstüne eşleşmenin nerede
    bulunduğunu (`baslikta`) ve maskelenmiş kanıtını (`parca`) ekler. Tarama
    sınıra takılırsa `kismi` ile bildirilir; kesilmiş bir arama sessizce
    "sonuç yok" gibi görünmemelidir.
    """
    source = _source(home, data)
    if source is None:
        return _missing_source(data)
    query = data.get("sorgu")
    if not isinstance(query, str) or not query.strip():
        return {"ok": False, "metin": _EMPTY_QUERY}
    sonuc = _search_sessions(source, query, root, limit=SEARCH_LIMIT)
    return {
        "ok": True,
        "kaynak": source.name,
        "oturumlar": [_serialize_match(match) for match in sonuc.matches],
        "taranan": sonuc.scanned,
        "kismi": sonuc.partial,
        "metin": sonuc.reason,
    }


def preview_session(home: Path, data: dict[str, Any]) -> dict[str, Any]:
    source = _source(home, data)
    if source is None:
        return _missing_source(data)
    session_id = _session_id(data)
    if not session_id:
        return {"ok": False, "metin": "Oturum kimliği zorunludur."}
    cursor, limit = _pagination(data)
    turns = sanitize_turns(source.read(session_id, cursor=cursor, limit=limit + 1))
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
    work_dirs = (
        _outside_root(codex_work_dirs(home, ref.session_id), root) if source.name == "codex" else ()
    )
    return PreparedResume(
        payload={
            "ok": True,
            "kaynak": source.name,
            "oturum_id": ref.session_id,
            "baslik": sanitize_title(ref.title),
            "sir_sayisi": digest.secret_count,
            "klasorler": [str(path) for path in work_dirs],
            "kok_uyusmuyor": bool(work_dirs) and not _inside_any(work_dirs, root),
        },
        digest=_with_work_dirs(digest.text, work_dirs, root),
        work_dirs=work_dirs,
        messages=_tail_messages(source, ref),
    )


def _tail_messages(source: HistorySource, ref: SessionRef) -> tuple[Message, ...]:
    """Devralınan oturumun SON `RESUME_MESSAGE_LIMIT` mesajı (güncel durum sondadır).

    İlk sayfayı almak uzun oturumda modele başı gösterip sonu atardı. `turn_count`
    yalnız başlangıç noktasını seçmek içindir; kaynak ile uyuşmazsa (az mesaj dönerse)
    baştan taranır, böylece sonuç her durumda gerçek son kesittir.
    """
    start = max(0, ref.turn_count - RESUME_TAIL_WINDOW) if ref.turn_count > 0 else 0
    tail = _collect_tail(source, ref.session_id, start)
    if len(tail) < RESUME_MESSAGE_LIMIT and start > 0:
        tail = _collect_tail(source, ref.session_id, 0)
    return tuple(tail)


def _collect_tail(source: HistorySource, session_id: str, cursor: int) -> deque[Message]:
    tail: deque[Message] = deque(maxlen=RESUME_MESSAGE_LIMIT)
    while True:
        page = source.read(session_id, cursor=cursor, limit=RESUME_PAGE_SIZE)
        if not page:
            break
        for turn in sanitize_turns(page):
            if turn.role in {"user", "assistant"} and turn.text.strip():
                tail.append(Message(turn.role, turn.text))
        cursor += len(page)
        if len(page) < RESUME_PAGE_SIZE:
            break
    return tail


def _is_inside(path: Path, root: Path) -> bool:
    resolved = root.expanduser().resolve()
    return path == resolved or resolved in path.parents


def _inside_any(paths: tuple[Path, ...], root: Path) -> bool:
    return any(_is_inside(path, root) for path in paths)


def _outside_root(paths: tuple[Path, ...], root: Path) -> tuple[Path, ...]:
    return tuple(path for path in paths if not _is_inside(path, root))


def _with_work_dirs(digest: str, work_dirs: tuple[Path, ...], root: Path) -> str:
    """Künyeye, oturumun gerçek çalışma klasörlerini ve proje kökü uyarısını ekle."""
    if not work_dirs:
        return digest
    note = (
        "çalışılan klasörler (Codex kaydından): " + ", ".join(str(path) for path in work_dirs),
        f"şu anki proje kökü: {root}",
        "Görev yukarıdaki klasörlerdeyse dosya araçlarını o MUTLAK yollarla kullan; "
        "yalnız proje kökünde arama. Bu klasörlere erişim açıldı.",
    )
    closing = "</devralinan_oturum>"
    if closing not in digest:
        return "\n".join((digest, *note))
    # Gerçek kapanış etiketi künyenin SON satırıdır. Oturum metni sahte bir kapanış
    # etiketi taşırsa o, güvenilir bloğu erken bitirip notu dışarıda bırakmasın diye
    # kaçırılır (içerik silinmez).
    body, _, tail = digest.rpartition(closing)
    body = body.replace(closing, "&lt;/devralinan_oturum&gt;")
    return "\n".join((body.rstrip("\n"), *note, closing)) + tail


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
        "baslik": sanitize_title(ref.title),
        "guncellendi": ref.updated_at,
        "tur_sayisi": ref.turn_count,
        "boyut": ref.size_bytes,
    }


def _serialize_match(match: SessionMatch) -> dict[str, Any]:
    """Künye + eşleşme kanıtı. Parça `search` içinde zaten maskelenmiştir."""
    return {**_serialize_ref(match.ref), "baslikta": match.in_title, "parca": match.snippet}


def _serialize_turn(turn: Turn) -> dict[str, Any]:
    safe = sanitize_turns((turn,))[0]
    return {"rol": safe.role, "metin": safe.text, "zaman": safe.timestamp}
