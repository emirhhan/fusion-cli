"""Kalıcı araç denetim günlüğü — "hangi komut çalıştı?" sorusunun her zaman cevabı.

Ölçülen boşluk (1 Ekim 2026): bir sohbet kullanıcının projelerini sildi; transcript
yalnız soru ve cevabı, çekirdek logu hiçbir şeyi tutuyordu. Hangi komutun hangi
yolu sildiği sonradan bulunamadı. Bu günlük her araç sonucunu konuşma başına bir
JSONL dosyasına EKLER; tur bitince ya da sohbet silinince temizlenmez.

Kayıt kısadır ve `redact`'tan geçer: araç adı, argümanlar, sonuç, çıktının başı,
hangi ajan (alt ajansa) ve zaman. Dosya `AUDIT_MAX_BYTES`'ı aşınca bir yedeğe döner.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from ..core.events import Event, ToolExecuted
from ..core.redaction import redact

_LOG = logging.getLogger(__name__)
#: Bir konuşmanın günlüğü bu boyutu aşınca `.1` dosyasına döner. 5 MB, aylarca
#: süren yoğun bir sohbetin binlerce araç kaydını tutar; disk büyümesi sınırlıdır.
AUDIT_MAX_BYTES = 5 * 1024 * 1024
#: Kayda girecek araç çıktısının başı (karakter).
AUDIT_OUTPUT_CHARS = 400
_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def audit_path(directory: Path, conversation_id: str) -> Path:
    """Bir konuşmanın denetim günlüğü dosyası (yazan ve okuyan aynı adı kullanır)."""
    return directory / f"{_SAFE_ID.sub('_', conversation_id) or 'oturum'}.jsonl"


def read_recent(path: Path, limit: int) -> list[dict[str, object]]:
    """Günlüğün son `limit` kaydı (eskiden yeniye); okunamazsa boş liste."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, object]] = []
    for line in lines[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


class AuditSink:
    """`ToolExecuted` olaylarını kalıcı denetim günlüğüne ekleyen dinleyici."""

    def __init__(self, directory: Path, conversation_id: str, *, root: Path) -> None:
        self._path = audit_path(directory, conversation_id)
        self._root = str(root)

    @property
    def path(self) -> Path:
        return self._path

    def handle(self, event: Event) -> None:
        if not isinstance(event, ToolExecuted):
            return
        record = {
            "zaman": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "kok": self._root,
            "ajan": event.agent_id or "ana",
            "arac": event.name,
            "argumanlar": redact(json.dumps(event.args, ensure_ascii=False, default=str)),
            "sonuc": event.outcome.value,
            "cikti": redact(event.output[:AUDIT_OUTPUT_CHARS]),
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists() and self._path.stat().st_size > AUDIT_MAX_BYTES:
                self._path.replace(self._path.with_suffix(".jsonl.1"))
            with self._path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as error:
            # Günlük yazılamaması turu düşürmez ama sessiz de kalmaz.
            _LOG.warning("denetim günlüğü yazılamadı", extra={"hata": str(error)})
