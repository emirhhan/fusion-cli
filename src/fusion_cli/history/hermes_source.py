"""Hermes geçmiş okuyucusu.

Hermes `~/.hermes/state.db` içinde `sessions` ve `messages` tablolarını tutar.
Diğer iki kaynaktan farklı olarak `sessions.cwd` sütunu vardır; bu yüzden proje
filtresi burada gerçekten anlamlıdır ve uygulanır.

Veritabanı salt okunur açılır: çalışan bir Hermes oturumunun verisi kilitlenmemeli.
"""

from __future__ import annotations

import builtins
import sqlite3
from pathlib import Path

from .models import SessionRef, Turn, fallback_title

#: Başlık olarak kullanılacak metnin en fazla uzunluğu.
TITLE_BUDGET = 60


class HermesSource:
    """Hermes geçmişini okur. Hiçbir metodu istisna fırlatmaz."""

    name = "hermes"

    def __init__(self, home: Path) -> None:
        self._home = home

    def _db_path(self) -> Path:
        return self._home / ".hermes" / "state.db"

    def is_installed(self) -> bool:
        return self._db_path().is_file()

    def _connect(self) -> sqlite3.Connection | None:
        path = self._db_path()
        if not path.is_file():
            return None
        try:
            return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error:
            return None

    def list(self, root: Path | None = None, limit: int | None = None) -> tuple[SessionRef, ...]:
        """Oturumları veri tabanından listele.

        `root` VERİLMEDİĞİNDE proje önceliklendirmesi gerekmez; bu durumda
        `limit` doğrudan SQL sorgusuna uygulanır, veri tabanı gereksiz satırı
        hiç döndürmez. `root` VERİLDİĞİNDE ise öncelik sıralaması Python
        tarafında yapıldığından (aidiyet, SQL `ORDER BY`'ın bilmediği bir
        kıstastır) SQL seviyesinde sınır uygulanamaz; tüm satırlar çekilip
        öncelik sırasına göre dizildikten SONRA kırpılır.
        """
        wanted = str(root) if root is not None else None
        rows = self._session_rows(limit=limit if wanted is None else None)
        entries = self._entries(rows, wanted)
        entries.sort(key=lambda entry: (entry[0], -entry[1]))
        refs = tuple(ref for _, _, ref in entries)
        return refs[:limit] if wanted is not None and limit is not None else refs

    def list_for_root(self, root: Path, limit: int | None = None) -> tuple[SessionRef, ...]:
        """Yalnızca `cwd` alanı proje köküyle birebir eşleşen oturumları döndür."""
        rows = self._session_rows(root=root, limit=limit)
        return tuple(ref for _, _, ref in self._entries(rows, str(root)))

    def _session_rows(
        self, *, root: Path | None = None, limit: int | None = None
    ) -> builtins.list[tuple[object, ...]]:
        connection = self._connect()
        if connection is None:
            return []
        query = (
            "SELECT s.id, s.title, s.cwd, s.started_at, s.message_count, "
            "(SELECT content FROM messages m WHERE m.session_id = s.id "
            " AND m.role = 'user' ORDER BY m.timestamp LIMIT 1), "
            "(SELECT COALESCE(SUM(length(CAST(content AS BLOB))), 0) "
            " FROM messages m WHERE m.session_id = s.id) "
            "FROM sessions s"
        )
        params: tuple[object, ...] = ()
        if root is not None:
            query += " WHERE s.cwd = ?"
            params = (str(root),)
        query += " ORDER BY s.started_at DESC"
        if limit is not None:
            query += " LIMIT ?"
            params = (*params, limit)
        try:
            return list(connection.execute(query, params).fetchall())
        except sqlite3.Error:
            return []
        finally:
            connection.close()

    def _entries(
        self, rows: builtins.list[tuple[object, ...]], wanted: str | None
    ) -> builtins.list[tuple[bool, float, SessionRef]]:
        entries: builtins.list[tuple[bool, float, SessionRef]] = []
        for row in rows:
            if row[0] is None or not str(row[0]).strip():
                continue
            updated_at = _safe_float(row[3])
            size_bytes = _safe_int(row[6])
            ref = SessionRef(
                source=self.name,
                session_id=str(row[0]),
                title=_title(row[1], row[5], updated_at, size_bytes),
                updated_at=updated_at,
                turn_count=_safe_int(row[4]),
                size_bytes=size_bytes,
            )
            is_other_project = wanted is not None and str(row[2] or "") != wanted
            entries.append((is_other_project, ref.updated_at, ref))
        return entries

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        """`cursor`'dan başlayarak en fazla `limit` GEÇERLİ tur döndür.

        `cursor`, satır sırasını değil, metni boş olmayan turların sırasını sayar
        (kardeş adapter'larla aynı sözleşme). SQL seviyesinde `LIMIT`/`OFFSET`
        uygulanmaz: sıralama veritabanında yapılır, sayım Python tarafında imleç
        ilerledikçe yürütülür. sqlite3 imleci tembeldir, sonuç `fetchall` ile
        belleğe alınmaz, satır satır dolaşılır.
        """
        connection = self._connect()
        if connection is None:
            return ()
        turns: list[Turn] = []
        try:
            cursor_obj = connection.execute(
                "SELECT role, content, timestamp FROM messages "
                "WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            )
            seen = 0
            for role, content, ts in cursor_obj:
                text = str(content or "").strip()
                if not text:
                    continue
                if seen < cursor:
                    seen += 1
                    continue
                turns.append(
                    Turn(
                        role=str(role or "assistant"),
                        text=text,
                        timestamp=_safe_float(ts),
                    )
                )
                seen += 1
                if len(turns) >= limit:
                    break
        except sqlite3.Error:
            return ()
        finally:
            connection.close()
        return tuple(turns)


def _title(stored: object, first_user: object, updated_at: float, size_bytes: int) -> str:
    """Başlık çözümü: kayıtlı başlık → ilk kullanıcı mesajı → tarih + boyut."""
    text = str(stored or "").strip()
    if text:
        return text[:TITLE_BUDGET]
    text = str(first_user or "").strip()
    if text:
        return text.splitlines()[0][:TITLE_BUDGET]
    return fallback_title(updated_at, size_bytes)


def _safe_float(value: object) -> float:
    """Bozuk SQLite sayısal alanını 0.0'a düşür."""
    if not isinstance(value, (int, float, str)):
        return 0.0
    try:
        return float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _safe_int(value: object) -> int:
    """Bozuk SQLite sayısal alanını negatif olmayan tam sayıya düşür."""
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError, OverflowError):
        return 0
