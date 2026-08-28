"""Codex / ChatGPT uygulaması geçmiş okuyucusu.

İki ayrı yer okunur ve bu bilinçlidir:

- `session_index.jsonl` kimlik, başlık ve zaman tutar. Listeleme buradan yapılır;
  9 MB'lık veritabanını yalnızca liste basmak için açmak gereksizdir.
- `thread_history_1.sqlite` içindeki `thread_items` tablosu asıl içeriği tutar.
  `item_json` şeması tipe göre değişir: kullanıcı mesajı `content[0].text`,
  ajan mesajı düz `text` alanı kullanır.

Veritabanı salt okunur açılır (`mode=ro`): çalışan bir Codex oturumunun verisini
kilitlemek ya da bozmak kabul edilemez.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import SessionRef, Turn

#: Okunan tip → ortak rol eşlemesi. Listede olmayan tipler yok sayılır.
_ROLES = {"userMessage": "user", "agentMessage": "assistant"}


class CodexSource:
    """Codex geçmişini okur. Hiçbir metodu istisna fırlatmaz."""

    name = "codex"

    def __init__(self, home: Path) -> None:
        self._home = home

    def _db_path(self) -> Path:
        return self._home / ".codex" / "thread_history_1.sqlite"

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
        """Oturumları indeks dosyasından listele.

        `root` yok sayılır: Codex proje kökünü güvenilir biçimde saklamıyor
        (`project_roots` tablosu boş ölçüldü). Yanlış filtrelemektense hepsini
        göstermek dürüsttür.
        """
        index = self._home / ".codex" / "session_index.jsonl"
        refs: list[SessionRef] = []
        try:
            lines = index.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(record, dict) or not record.get("id"):
                continue
            refs.append(
                SessionRef(
                    source=self.name,
                    session_id=str(record["id"]),
                    title=str(record.get("thread_name") or record["id"]),
                    updated_at=_epoch(record.get("updated_at")),
                    turn_count=0,
                )
            )
        refs.sort(key=lambda r: r.updated_at, reverse=True)
        return tuple(refs)

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        connection = self._connect()
        if connection is None:
            return ()
        turns: list[Turn] = []
        try:
            rows = connection.execute(
                "SELECT item_type, item_json, created_at_ms FROM thread_items "
                "WHERE thread_id = ? AND item_type IN ('userMessage','agentMessage') "
                "ORDER BY rollout_ordinal LIMIT ? OFFSET ?",
                (session_id, limit, cursor),
            ).fetchall()
        except sqlite3.Error:
            return ()
        finally:
            connection.close()
        for item_type, payload, created_ms in rows:
            text = _text_of(payload, str(item_type))
            if not text:
                continue
            turns.append(
                Turn(
                    role=_ROLES.get(str(item_type), "assistant"),
                    text=text,
                    timestamp=float(created_ms or 0) / 1000.0,
                )
            )
        return tuple(turns)


def _text_of(payload: object, item_type: str) -> str:
    """`item_json` içinden metni çıkar. Şema tipe göre değişir."""
    if not isinstance(payload, str):
        return ""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    if item_type == "agentMessage":
        return str(data.get("text") or "").strip()
    content = data.get("content")
    if isinstance(content, list):
        parts = [str(p.get("text", "")) for p in content if isinstance(p, dict)]
        return "\n".join(p for p in parts if p).strip()
    return ""


def _epoch(value: object) -> float:
    if not isinstance(value, str):
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
