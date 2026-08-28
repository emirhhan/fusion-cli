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

from .models import SessionRef, Turn, fallback_title

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

    def list(self, root: Path | None = None, limit: int | None = None) -> tuple[SessionRef, ...]:
        """Oturumları indeks dosyasından listele.

        `root` yok sayılır: Codex proje kökünü güvenilir biçimde saklamıyor
        (`project_roots` tablosu boş ölçüldü). Yanlış filtrelemektense hepsini
        göstermek dürüsttür.

        Listeleme zaten ucuz indeks dosyasından geldiği için (bkz. modül
        docstring'i) gereksiz ayrıştırmayı önlemeye gerek yok; `limit` burada
        yalnızca sonucu kırpar.
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
            session_id = str(record["id"])
            updated_at = _epoch(record.get("updated_at"))
            stored_title = str(record.get("thread_name") or "").strip()
            first_user, size_bytes = (
                self._fallback_metadata(session_id) if not stored_title else ("", 0)
            )
            refs.append(
                SessionRef(
                    source=self.name,
                    session_id=session_id,
                    title=stored_title or first_user or fallback_title(updated_at, size_bytes),
                    updated_at=updated_at,
                    turn_count=0,
                    size_bytes=size_bytes,
                )
            )
        refs.sort(key=lambda r: r.updated_at, reverse=True)
        if limit is not None:
            refs = refs[:limit]
        return tuple(refs)

    def list_for_root(self, root: Path, limit: int | None = None) -> tuple[SessionRef, ...]:
        """Codex proje aidiyetini kanıtlamadığı için açılış listesine katılmaz."""
        return ()

    def _fallback_metadata(self, session_id: str) -> tuple[str, int]:
        """Başlıksız bir Codex kaydı için ilk kullanıcı metni ve içerik boyutu."""
        connection = self._connect()
        if connection is None:
            return "", 0
        try:
            row = connection.execute(
                "SELECT (SELECT item_json FROM thread_items "
                "WHERE thread_id = ? AND item_type = 'userMessage' "
                "ORDER BY rollout_ordinal LIMIT 1), "
                "COALESCE(SUM(length(CAST(item_json AS BLOB))), 0) "
                "FROM thread_items WHERE thread_id = ?",
                (session_id, session_id),
            ).fetchone()
        except sqlite3.Error:
            return "", 0
        finally:
            connection.close()
        if row is None:
            return "", 0
        first_user = _text_of(row[0], "userMessage")
        title = first_user.splitlines()[0][:60] if first_user else ""
        return title, _safe_int(row[1])

    def read(self, session_id: str, cursor: int = 0, limit: int = 50) -> tuple[Turn, ...]:
        """`cursor`'dan başlayarak en fazla `limit` GEÇERLİ tur döndür.

        `cursor`, satır sırasını değil, metni boş olmayan turların sırasını sayar
        (kardeş adapter `claude_source.py` ile aynı sözleşme). Bu yüzden SQL
        seviyesinde `LIMIT`/`OFFSET` uygulanmaz: sıralama veritabanında yapılır,
        ama sayım Python tarafında imleç ilerledikçe yürütülür. sqlite3 imleci
        tembel olduğundan sonuç `fetchall` ile belleğe alınmaz, satır satır
        dolaşılır.
        """
        connection = self._connect()
        if connection is None:
            return ()
        turns: list[Turn] = []
        try:
            cursor_obj = connection.execute(
                "SELECT item_type, item_json, created_at_ms FROM thread_items "
                "WHERE thread_id = ? AND item_type IN ('userMessage','agentMessage') "
                "ORDER BY rollout_ordinal",
                (session_id,),
            )
            seen = 0
            for item_type, payload, created_ms in cursor_obj:
                text = _text_of(payload, str(item_type))
                if not text:
                    continue
                if seen < cursor:
                    seen += 1
                    continue
                turns.append(
                    Turn(
                        role=_ROLES.get(str(item_type), "assistant"),
                        text=text,
                        timestamp=_millis_to_seconds(created_ms),
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
        parts = [
            str(p.get("text"))
            for p in content
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        ]
        return "\n".join(p for p in parts if p).strip()
    return ""


def _millis_to_seconds(value: object) -> float:
    """Milisaniye zaman damgasını unix saniyeye çevir. Çözülemezse 0.0 döner."""
    if not isinstance(value, (int, float, str)):
        return 0.0
    try:
        return float(value or 0) / 1000.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _safe_int(value: object) -> int:
    """Beklenmedik SQLite değerini negatif olmayan tam sayıya daralt."""
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _epoch(value: object) -> float:
    if not isinstance(value, str):
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
