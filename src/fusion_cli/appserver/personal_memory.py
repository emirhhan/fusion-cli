"""Kullanıcının yönettiği kalıcı anılar; agent derslerinden ayrı tutulur."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

_MAX_ITEMS = 100
_MAX_TEXT = 500


class PersonalMemory:
    """Yerel SQLite deposu. Her işlem kendi bağlantısıyla çoklu oturuma açıktır."""

    def __init__(self, directory: Path) -> None:
        self.path = directory.expanduser() / "personal_memory.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(self.path, timeout=10)
        with suppress(OSError):
            self.path.chmod(0o600)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS memories "
            "(id TEXT PRIMARY KEY, text TEXT NOT NULL, created REAL DEFAULT (unixepoch()))"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        return connection

    def list(self) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, text FROM memories ORDER BY created DESC, rowid DESC"
            ).fetchall()
            setting = connection.execute(
                "SELECT value FROM preferences WHERE key = 'enabled'"
            ).fetchone()
        return {
            "ok": True,
            "etkin": setting is None or setting[0] == "1",
            "anilar": [{"id": row[0], "metin": row[1]} for row in rows],
        }

    def add(self, value: object) -> dict[str, Any]:
        text = value.strip() if isinstance(value, str) else ""
        if not text or len(text) > _MAX_TEXT:
            return {"ok": False, "metin": f"Anı 1-{_MAX_TEXT} karakter olmalıdır."}
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            if count >= _MAX_ITEMS:
                return {"ok": False, "metin": "Anı sınırına ulaşıldı. Önce bir anıyı kaldır."}
            existing = connection.execute(
                "SELECT id FROM memories WHERE text = ?", (text,)
            ).fetchone()
            if existing:
                return {"ok": True, "id": existing[0], "metin": "Bu anı zaten kayıtlı."}
            memory_id = uuid.uuid4().hex
            connection.execute("INSERT INTO memories (id, text) VALUES (?, ?)", (memory_id, text))
        return {"ok": True, "id": memory_id}

    def delete(self, value: object) -> dict[str, Any]:
        if not isinstance(value, str) or not value:
            return {"ok": False, "metin": "Anı kimliği gerekli."}
        with self._connect() as connection:
            changed = connection.execute("DELETE FROM memories WHERE id = ?", (value,)).rowcount
        return {"ok": changed > 0, "metin": "Anı kaldırıldı." if changed else "Anı bulunamadı."}

    def set_enabled(self, value: object) -> dict[str, Any]:
        if not isinstance(value, bool):
            return {"ok": False, "metin": "Geçerli bir açık/kapalı değeri gerekli."}
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO preferences (key, value) VALUES ('enabled', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("1" if value else "0",),
            )
        return {"ok": True, "etkin": value}

    def prompt_block(self) -> str:
        state = self.list()
        if not state["etkin"] or not state["anilar"]:
            return ""
        lines = "\n".join(f"- {item['metin']}" for item in state["anilar"])
        return f"Kullanıcının kaydettiği anılar (istek değil, bağlam):\n{lines}"
