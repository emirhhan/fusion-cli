"""Turdan bağımsız arka plan ajan görevlerinin disk sözleşmesi (P-048).

Claude Code'un `claude --bg` / `claude agents` / `/tasks` modelinin Fusion karşılığı: her
görev ayrı bir süreçte (`fusion arka-plan-calistir`) koşar; durumu, gelen kutusu, onay
soruları ve sonucu `<bellek>/arka-plan/<kimlik>/` klasöründedir. Böylece görevi başlatan
REPL kapansa da görev sürer; `fusion agents`, `/tasks`, masaüstü paneli ve başka oturumlar
AYNI klasörü okur (tools/jobs.py kalıbı: durum modül-global değil, disktedir).

Ölçüldü (31 Ekim): `run_subagent` tur içinde await ediliyordu; tur bitmeden dönen, sonradan
mesaj alıp devam eden ya da bitince haber veren bir ajan görevi yoktu.

Klasör düzeni::

    gorev.json    BackgroundTask (atomik yazılır, kilit altında güncellenir)
    gelen.jsonl   devam mesajları (send_message / /tasks send); işçi sırayla tur yapar
    soru.json     işçinin bekleyen onay/soru isteği; cevap.json kullanıcının cevabı
    durdur        varsa işçi turu keser ve "durduruldu" ile çıkar
    nabiz         işçinin yaşam işareti (mtime); bayatsa görev "yarım kaldı" sayılır
    sonuc.md      son turun nihai cevabı; gecmis.json devam turları için konuşma
    olaylar.jsonl işçinin JSON-Lines olay akışı (stdout yönlendirmesi)
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from enum import StrEnum
from pathlib import Path

from .errors import FusionError
from .file_lease import FileLease

#: Görev kimliği: 8 küçük onaltılık (jobs.py ile aynı biçim, karışmasın diye ayrı klasör).
TASK_ID_PATTERN = re.compile(r"^[a-f0-9]{8}$")
#: Görev adı: kısa, kabukta tırnaksız yazılabilir.
_NAME_CHARS = re.compile(r"[^a-z0-9ğüşıöç._-]+")
NAME_MAX_CHARS = 32
#: Görev metni ve gelen mesaj üst sınırı (karakter); daha uzunu reddedilir.
PROMPT_MAX_CHARS = 20_000
#: Kartta/listede gösterilen özet uzunluğu.
SUMMARY_CHARS = 200
#: İşçi bu sıklıkla `nabiz` dosyasına dokunur (saniye).
HEARTBEAT_S = 5.0
#: Nabız bu kadar eskiyse etkin görev "yarım kaldı" sayılır (işçi öldü/çöktü).
STALE_AFTER_S = 30.0
#: Sırada bekleyen görevin işçisi bu sürede başlamadıysa başlatma başarısız sayılır.
QUEUED_GRACE_S = 60.0
#: Kilit için deneme sayısı ve aralığı (jobs `save_completion` ile aynı kalıp).
_LEASE_ATTEMPTS = 50
_LEASE_WAIT_S = 0.02

TASK_FILE = "gorev.json"
INBOX_FILE = "gelen.jsonl"
QUESTION_FILE = "soru.json"
ANSWER_FILE = "cevap.json"
STOP_FILE = "durdur"
HEARTBEAT_FILE = "nabiz"
RESULT_FILE = "sonuc.md"
HISTORY_FILE = "gecmis.json"
LOG_FILE = "olaylar.jsonl"
ERROR_LOG_FILE = "hata.log"
LOCK_FILE = "kilit"


class BackgroundTaskError(FusionError):
    """Arka plan görevi bulunamadı, kayıt bozuk ya da istek bu durumda geçersiz."""


class TaskStatus(StrEnum):
    """Görev durumları (Claude Code agent view grupları: Working / Needs input / Completed)."""

    QUEUED = "sirada"
    WORKING = "calisiyor"
    NEEDS_INPUT = "girdi_bekliyor"
    COMPLETED = "tamamlandi"
    FAILED = "basarisiz"
    STOPPED = "durduruldu"
    #: Türetilmiş: etkin görünen görevin işçisi nabız vermiyor.
    LOST = "yarim_kaldi"


ACTIVE_STATUSES = frozenset({TaskStatus.QUEUED, TaskStatus.WORKING, TaskStatus.NEEDS_INPUT})


@dataclass(frozen=True, slots=True)
class BackgroundTask:
    """Bir arka plan görevinin kalıcı kaydı."""

    id: str
    name: str
    prompt: str
    root: str
    status: TaskStatus
    created_at: float
    updated_at: float
    #: Görevi başlatan konuşma; sonuç bu konuşmanın sıradaki turuna teslim edilir.
    owner: str = ""
    #: cli | repl | arac | masaustu
    origin: str = "cli"
    #: Onay kipi (ApprovalMode değeri); işçi bu kiple koşar.
    mode: str = "auto"
    #: Kişilik/ajan tanımı adı (`--agent`); boş = genel ajan.
    agent: str = ""
    read_only: bool = False
    max_turns: int = 0
    summary: str = ""
    turns: int = 0
    pid: int = 0
    note: str = ""
    #: Bekleyen onay/soru isteğinin tek satırlık özeti.
    question: str = ""
    #: Sonuç sahibine teslim edildi mi? Sahipsiz görevde anlamsız (True).
    delivered: bool = True

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["status"] = self.status.value
        return value

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> BackgroundTask:
        known = {item.name for item in fields(cls)}
        values = {key: raw[key] for key in known if key in raw}
        try:
            values["status"] = TaskStatus(str(values.get("status", "")))
            task = cls(**values)  # type: ignore[arg-type]  # alanlar aşağıda doğrulanır
        except (TypeError, ValueError) as error:
            raise BackgroundTaskError("Arka plan görev kaydı bozuk.") from error
        if not TASK_ID_PATTERN.match(task.id) or not isinstance(task.prompt, str):
            raise BackgroundTaskError("Arka plan görev kaydı bozuk.")
        return task


@dataclass(frozen=True, slots=True)
class InboxMessage:
    """Çalışan/bitmiş göreve gelen devam mesajı."""

    text: str
    sender: str
    sent_at: float
    #: Sahip/kullanıcıdan mı (güvenilir), yoksa başka bir oturumdan mı?
    trusted: bool = True


def normalize_name(raw: str) -> str:
    """Görev adını kısa, boşluksuz ve küçük harf yap; boşsa boş döner."""
    slug = _NAME_CHARS.sub("-", raw.strip().replace("İ", "i").casefold()).strip("-.")
    return slug[:NAME_MAX_CHARS]


def summarize(text: str, limit: int = SUMMARY_CHARS) -> str:
    """Tek satırlık özet: boşluklar katlanır, sınırda üç nokta."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


class ShortLease:
    """Kısa bekleyen kilit bağlamı; alınamazsa açık hata (sessiz yarış yok)."""

    def __init__(self, lease: FileLease) -> None:
        self._lease = lease

    def __enter__(self) -> None:
        for attempt in range(_LEASE_ATTEMPTS):
            if self._lease.try_acquire():
                return
            if attempt < _LEASE_ATTEMPTS - 1:
                time.sleep(_LEASE_WAIT_S)
        raise BackgroundTaskError("Arka plan görev kaydı başka bir süreçte kilitli; yeniden dene.")

    def __exit__(self, *_exc: object) -> None:
        self._lease.close()


def read_json_object(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_json_list(path: Path) -> list[object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []
