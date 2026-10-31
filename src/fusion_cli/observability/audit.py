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

from ..core.events import AutoModeFellBack, AutoReviewDecided, Event, ToolExecuted
from ..core.redaction import redact

_LOG = logging.getLogger(__name__)
#: Bir konuşmanın günlüğü bu boyutu aşınca `.1` dosyasına döner. 5 MB, aylarca
#: süren yoğun bir sohbetin binlerce araç kaydını tutar; disk büyümesi sınırlıdır.
AUDIT_MAX_BYTES = 5 * 1024 * 1024
#: Kayda girecek araç çıktısının başı (karakter).
AUDIT_OUTPUT_CHARS = 400
#: Kayda girecek TEK bir argüman değerinin başı (karakter). `write_file` içeriği gibi
#: yüzlerce KB'lık değerler günlüğü doldurmasın ve kullanıcı kaynağını kopyalamasın.
AUDIT_ARG_CHARS = 300
#: Döndürmede tutulan yedek sayısı (`.jsonl.1` en yeni).
AUDIT_BACKUPS = 3
#: Denetçi kayıtlarının `tur` etiketi (araç kayıtlarında alan yoktur; geri uyumlu).
AUDIT_CLASSIFIER_KIND = "sınıflandırıcı"
_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def _short_args(args: object) -> object:
    """Uzun metin değerlerini kısalt; yol/komut gibi kısa alanlar aynen kalır."""
    if isinstance(args, str):
        if len(args) <= AUDIT_ARG_CHARS:
            return args
        return f"{args[:AUDIT_ARG_CHARS]}…[+{len(args) - AUDIT_ARG_CHARS} karakter]"
    if isinstance(args, dict):
        return {key: _short_args(value) for key, value in args.items()}
    if isinstance(args, (list, tuple)):
        return [_short_args(value) for value in args]
    return args


def _rotate(path: Path) -> None:
    """`.1` → `.2` → … kaydır; en eskisi düşer. Eskiden tek yedek üzerine yazılıyordu."""
    for numara in range(AUDIT_BACKUPS, 1, -1):
        eski = path.with_suffix(f".jsonl.{numara - 1}")
        if eski.exists():
            eski.replace(path.with_suffix(f".jsonl.{numara}"))
    path.replace(path.with_suffix(".jsonl.1"))


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
    """`ToolExecuted` ve denetçi (P-011) olaylarını kalıcı denetim günlüğüne ekleyen dinleyici."""

    def __init__(self, directory: Path, conversation_id: str, *, root: Path) -> None:
        self._path = audit_path(directory, conversation_id)
        self._root = str(root)

    @property
    def path(self) -> Path:
        return self._path

    def handle(self, event: Event) -> None:
        record = self._record(event)
        if record is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            if self._path.exists() and self._path.stat().st_size > AUDIT_MAX_BYTES:
                _rotate(self._path)
            with self._path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as error:
            # Günlük yazılamaması turu düşürmez ama sessiz de kalmaz.
            _LOG.warning("denetim günlüğü yazılamadı", extra={"hata": str(error)})

    def _record(self, event: Event) -> dict[str, object] | None:
        if isinstance(event, (AutoReviewDecided, AutoModeFellBack)):
            return self._review_record(event)
        if not isinstance(event, ToolExecuted):
            return None
        record: dict[str, object] = {
            "zaman": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "kok": self._root,
            "ajan": event.agent_id or "ana",
            "arac": event.name,
            "argumanlar": redact(
                json.dumps(_short_args(dict(event.args)), ensure_ascii=False, default=str)
            ),
            "sonuc": event.outcome.value,
            "cikti": redact(event.output[:AUDIT_OUTPUT_CHARS]),
        }
        if event.workspace:
            record["calisma_alani"] = event.workspace
        return record

    def _review_record(self, event: AutoReviewDecided | AutoModeFellBack) -> dict[str, object]:
        """Otomatik kip denetçisinin kararı / kip düşüşü (P-011): `tur: sınıflandırıcı`."""
        record: dict[str, object] = {
            "zaman": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "kok": self._root,
            "ajan": event.agent_id or "ana",
            "tur": AUDIT_CLASSIFIER_KIND,
        }
        if isinstance(event, AutoModeFellBack):
            return {**record, "arac": "-", "sonuc": "manuel-kipe-dustu", "gerekce": event.reason}
        return {
            **record,
            "arac": event.tool,
            "argumanlar": redact(event.summary),
            "sonuc": f"sınıflandırıcı:{event.verdict.value}",
            "gerekce": redact(event.reason),
            "kaynak": event.source.value,
        }
