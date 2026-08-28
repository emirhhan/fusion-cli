"""Hermes geçmiş okuyucusu.

Hermes `~/.hermes/state.db` içinde `sessions` ve `messages` tablolarını tutar.
Diğer iki kaynaktan farklı olarak `sessions.cwd` sütunu vardır; bu yüzden proje
filtresi burada gerçekten anlamlıdır ve uygulanır.

Veritabanı salt okunur açılır: çalışan bir Hermes oturumunun verisi kilitlenmemeli.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import SessionRef, Turn

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

    def list(self, root: Path | None = None) -> tuple[SessionRef, ...]:
        connection = self._connect()
        if connection is None:
            return ()
        try:
            rows = connection.execute(
                "SELECT s.id, s.title, s.cwd, s.started_at, s.message_count, "
                "(SELECT content FROM messages m WHERE m.session_id = s.id "
                " AND m.role = 'user' ORDER BY m.timestamp LIMIT 1) "
                "FROM sessions s ORDER BY s.started_at DESC"
            ).fetchall()
        except sqlite3.Error:
            return ()
        finally:
            connection.close()

        wanted = str(root) if root is not None else None
        entries: list[tuple[bool, float, SessionRef]] = []
        for row in rows:
            ref = SessionRef(
                source=self.name,
                session_id=str(row[0]),
                title=_title(row[1], row[5], str(row[0])),
                updated_at=float(row[3] or 0.0),
                turn_count=int(row[4] or 0),
            )
            is_other_project = wanted is not None and str(row[2] or "") != wanted
            entries.append((is_other_project, ref.updated_at, ref))
        # `root` verilmişse o projeye ait oturumlar önce gelir; diğer projeler
        # kaybolmaz, yalnızca geriye itilir. Öncelik grubu içinde ise en yeni
        # oturum baştadır (mevcut started_at sıralaması korunur).
        entries.sort(key=lambda e: (e[0], -e[1]))
        return tuple(ref for _, _, ref in entries)

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
                        timestamp=float(ts or 0.0),
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


def _title(stored: object, first_user: object, fallback: str) -> str:
    """Başlık çözümü: kayıtlı başlık → ilk kullanıcı mesajı → kimlik."""
    text = str(stored or "").strip()
    if text:
        return text[:TITLE_BUDGET]
    text = str(first_user or "").strip()
    if text:
        return text.splitlines()[0][:TITLE_BUDGET]
    return fallback
