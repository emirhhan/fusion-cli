"""Arka plan ajan görevlerini başlat, mesaj gönder, durdur, bekle ve teslim et (P-048).

Bütün yüzeyler (REPL `/bg` `/tasks`, `fusion agent --bg`, `fusion agents`, `spawn_agent`
aracının `arka_plan` kipi, masaüstü `arkaplan.*` RPC'leri) bu modülden geçer; ikinci bir
başlatma yolu yoktur. Görev kaydı `core.background_store`, işçi `cli.background_worker`.

İşçi bağımsız bir süreç grubunda başlar: görevi başlatan REPL kapanınca ölmez. Durdurma
önce işbirliklidir (`durdur` dosyası → işçi turu keser); zorla durdurma yalnız süreç
komut satırında görev kimliği DOĞRULANINCA yapılır (PID tek başına öldürme yetkisi değildir,
bkz. `job_owner.process_identity`).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..core.background_store import BackgroundTaskStore
from ..core.background_tasks import (
    ERROR_LOG_FILE,
    BackgroundTask,
    BackgroundTaskError,
    InboxMessage,
    TaskOptions,
    TaskStatus,
    summarize,
)
from ..core.clock import SystemClock
from ..core.errors import CleanupFailedError
from ..core.peers import PeerRegistry
from ..core.process_control import process_group_options, terminate_process_tree
from ..core.protocols import Clock
from ..core.redaction import redact
from ..core.types import Message
from ..core.untrusted_text import neutralize_closing_tags
from ..ui import background_messages as texts

#: Bellek dizini altındaki klasör adları.
STORE_DIR_NAME = "arka-plan"
PEERS_DIR_NAME = "oturumlar"
#: Gizli işçi komutunun adı (paketlenmiş uygulamada `fusion arka-plan-calistir`).
WORKER_COMMAND = "arka-plan-calistir"
_WORKER_MODULE = "fusion_cli.cli.background_worker"
#: `wait_task` yoklama aralığı ve üst sınırı (saniye).
WAIT_POLL_S = 0.5
WAIT_MAX_S = 600.0
#: Teslim bloğunda görev başına sonuç alıntısı (karakter).
DELIVERY_EXCERPT_CHARS = 1_500

#: (argv, çalışma dizini, olay günlüğü, hata günlüğü) → başlayan sürecin PID'i.
Launcher = Callable[[list[str], Path, Path, Path], int]


def task_store(memory_dir: Path, clock: Clock | None = None) -> BackgroundTaskStore:
    return BackgroundTaskStore(memory_dir / STORE_DIR_NAME, clock or SystemClock())


def peer_registry(memory_dir: Path, clock: Clock | None = None) -> PeerRegistry:
    return PeerRegistry(memory_dir / PEERS_DIR_NAME, clock or SystemClock())


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    """Yeni arka plan görevinin istenen özellikleri."""

    prompt: str
    root: Path
    name: str = ""
    owner: str = ""
    origin: str = "cli"
    mode: str = "auto"
    agent: str = ""
    read_only: bool = False
    max_turns: int = 0
    #: Devralınan konuşma (`/bg`, Ctrl+B): yalnız user/assistant metinleri.
    history: tuple[Mapping[str, str], ...] = ()
    #: Başlatan yüzeyin kısıtları (araç tavanı/yasakları, yazma alanı, bütçe, -c…).
    options: TaskOptions = field(default_factory=TaskOptions)


def worker_argv(store_dir: Path, task_id: str) -> list[str]:
    """İşçi komutu; paketlenmiş ikili `-m` tanımaz (bkz. `providers.web_control`).

    `-P` (Python 3.11+): çalışma dizini `sys.path`'e GİRMEZ. Ölçüldü (31 Ekim): işçi görev
    kökünde `python -m` ile başlıyordu; güvenilmeyen depodaki `yaml/__init__.py` gibi bir
    gölge paket Fusion'ın bağımlılığı yerine onaysız içe aktarılıyordu. Ortam değişkeni
    (`PYTHONSAFEPATH`) yerine bayrak: ajanın açtığı alt süreçlere sızmaz.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, WORKER_COMMAND, "--dizin", str(store_dir), task_id]
    return [sys.executable, "-P", "-m", _WORKER_MODULE, "--dizin", str(store_dir), task_id]


def spawn_detached(argv: list[str], cwd: Path, log_path: Path, error_path: Path) -> int:
    """Süreci ayrı süreç grubunda başlat; çıktısı dosyalara gider, beklenmez."""
    with log_path.open("ab") as stdout, error_path.open("ab") as stderr:
        process = subprocess.Popen(  # argv sabit: python + işçi modülü
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            **process_group_options(),
        )
    return process.pid


def start_task(
    store: BackgroundTaskStore,
    request: LaunchRequest,
    *,
    max_active: int,
    launcher: Launcher | None = None,
) -> BackgroundTask:
    """Görevi kaydet ve işçisini başlat; tavan doluysa ya da başlatma düşerse açık hata."""
    if max_active > 0 and store.active_count() >= max_active:
        raise BackgroundTaskError(
            f"Aynı anda en çok {max_active} arka plan görevi çalışabilir; "
            "birini bitmesini bekle ya da /tasks stop ile durdur."
        )
    task = store.create(
        request.prompt,
        root=request.root,
        name=request.name,
        owner=request.owner,
        origin=request.origin,
        mode=request.mode,
        agent=request.agent,
        read_only=request.read_only,
        max_turns=request.max_turns,
        history=[dict(item) for item in request.history],
        options=request.options,
    )
    return _launch(store, task, launcher)


def _launch(
    store: BackgroundTaskStore, task: BackgroundTask, launcher: Launcher | None
) -> BackgroundTask:
    folder = store.task_dir(task.id)
    # Varsayılan çalışma anında çözülür: testler modüldeki `spawn_detached`'ı değiştirebilsin.
    run = launcher or spawn_detached
    try:
        pid = run(
            worker_argv(store.base_dir, task.id),
            Path(task.root),
            store.log_path(task.id),
            folder / ERROR_LOG_FILE,
        )
    except OSError as error:
        store.update(task.id, status=TaskStatus.FAILED, note=f"İşçi başlatılamadı: {error}")
        raise BackgroundTaskError(f"Arka plan görevi başlatılamadı: {error}") from error
    return store.update(task.id, pid=pid)


def send_to_task(
    store: BackgroundTaskStore,
    task: BackgroundTask,
    text: str,
    *,
    sender: str,
    trusted: bool = True,
    launcher: Launcher | None = None,
) -> BackgroundTask:
    """Devam mesajı: çalışan görev sıradaki turunda alır, bitmiş görev yeniden başlar."""
    message = InboxMessage(text=text.strip(), sender=sender, sent_at=store.now(), trusted=trusted)
    if store.append_inbox(task.id, message):
        return _launch(store, store.get(task.id), launcher)
    return store.get(task.id)


def stop_task(
    store: BackgroundTaskStore, task: BackgroundTask, *, force: bool = False
) -> BackgroundTask:
    """Görevi durdur: işçi varsa durdurma isteği, yoksa kayıt doğrudan kapanır."""
    if task.status is TaskStatus.LOST or task.status is TaskStatus.QUEUED:
        store.request_stop(task.id)
        return store.update(task.id, status=TaskStatus.STOPPED, note="Kullanıcı durdurdu.")
    if not task.is_active:
        raise BackgroundTaskError(f"'{task.name}' zaten bitmiş ({task.status.value}).")
    store.request_stop(task.id)
    if force and task.pid > 0:
        _terminate_verified(task)
        return store.update(task.id, status=TaskStatus.STOPPED, note="Zorla durduruldu.")
    return store.get(task.id)


def _terminate_verified(task: BackgroundTask) -> None:
    """Süreç komut satırında görev kimliği varsa grubu sonlandır; yoksa dokunma."""
    from .job_owner import process_identity

    try:
        process_identity(task.pid, task.id)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise BackgroundTaskError(
            "İşçi sürecinin kimliği doğrulanamadı; zorla durdurulmadı (durdurma isteği bırakıldı)."
        ) from None
    try:
        terminate_process_tree(task.pid, force=True)
    except CleanupFailedError as error:
        raise BackgroundTaskError(str(error)) from error


#: Temizlikte silinen durumlar; "yarım kaldı" görev mesajla sürdürülebilir, kalır.
_CLEANABLE = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED})


def clean_finished(store: BackgroundTaskStore, root: Path | None) -> tuple[int, tuple[str, ...]]:
    """Bitmiş görevleri sil (`root` verilirse yalnız o proje); (silinen, silinemeyenler).

    Ölçüldü (31 Ekim): temizlik bütün projelerin sonuçlarını siliyordu (liste yalnız bu
    projeyi gösterirken) ve tek bir silme hatası CLI'da yakalanmayan iz basıyordu.
    """
    removed, failed = 0, []
    for task in store.tasks(root=root):
        if task.status not in _CLEANABLE:
            continue
        try:
            store.remove(task.id)
        except (BackgroundTaskError, OSError):
            failed.append(task.name)
            continue
        removed += 1
    return removed, tuple(failed)


def answer_task(store: BackgroundTaskStore, task: BackgroundTask, value: str) -> BackgroundTask:
    """Bekleyen onay/soruyu cevapla (`evet` / `hayir` / `oturum` ya da serbest metin)."""
    if not value.strip():
        raise BackgroundTaskError("Cevap boş olamaz: evet, hayir, oturum ya da metin yaz.")
    store.answer(task.id, value)
    return store.get(task.id)


async def wait_task(store: BackgroundTaskStore, task_id: str, timeout_s: float) -> BackgroundTask:
    """Görev çalışmayı bırakana (bitti/girdi bekliyor) ya da süre dolana kadar bekle."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, min(timeout_s, WAIT_MAX_S))
    while True:
        task = store.get(task_id)
        if task.status not in {TaskStatus.QUEUED, TaskStatus.WORKING} or loop.time() >= deadline:
            return task
        await asyncio.sleep(WAIT_POLL_S)


def collect_deliveries(store: BackgroundTaskStore, owner: str) -> tuple[BackgroundTask, ...]:
    """Sahibine henüz teslim edilmemiş bitmiş görevleri al ve teslim edildi işaretle."""
    if not owner:
        return ()
    delivered: list[BackgroundTask] = []
    for task in store.tasks():
        if task.owner != owner or task.delivered or task.is_active:
            continue
        delivered.append(store.update(task.id, delivered=True))
    return tuple(delivered)


#: Teslim bloğunun etiketleri; içerik bunları kapatamaz (`neutralize_closing_tags`).
_DELIVERY_TAGS = ("gorev", "arka_plan_sonuclari")


def delivery_block(store: BackgroundTaskStore, tasks: tuple[BackgroundTask, ...]) -> str:
    """Bitmiş görevlerin sonucunu sıradaki tura konacak etiketli bağlam bloğuna çevir.

    Sonuç bir alt ajanın ÇIKTISIDIR (web/dosyadan enjekte talimat taşıyabilir): blok
    güvenilmez etiketlidir, sırlar maskelenir, kapanış etiketleri etkisizleştirilir.
    Ölçüldü (31 Ekim): metin sistem bağlamına etiketsiz, maskesiz ve kaçışsız giriyordu.
    """
    if not tasks:
        return ""
    parts = ['<arka_plan_sonuclari guvenilmez="evet">']
    for task in tasks:
        excerpt = summarize(store.read_result(task.id) or task.summary, DELIVERY_EXCERPT_CHARS)
        body = neutralize_closing_tags(
            redact(excerpt or task.note or "(sonuç metni yok)"), *_DELIVERY_TAGS
        )
        parts.append(
            f'<gorev id="{task.id}" ad="{task.name}" durum="{task.status.value}">\n{body}\n</gorev>'
        )
    parts.append(f"</arka_plan_sonuclari>\n{texts.BG_DELIVERY_NOTE}")
    return "\n".join(parts)


def start_with_settings(
    runtime: object, memory_dir: Path, request: LaunchRequest
) -> BackgroundTask:
    """Yapılandırma kapısından geçerek başlat (REPL, CLI, masaüstü ortak yolu)."""
    if not getattr(runtime, "background_agents", True):
        raise BackgroundTaskError(texts.BG_DISABLED)
    return start_task(
        task_store(memory_dir),
        request,
        max_active=int(getattr(runtime, "max_background_agents", DEFAULT_MAX_ACTIVE)),
    )


#: `max_background_agents` okunamazsa (eski yapılandırma) kullanılan tavan.
DEFAULT_MAX_ACTIVE = 4
#: Devralınan konuşmadan taşınacak en çok mesaj ve mesaj başına karakter.
FORK_MESSAGES = 12
FORK_MESSAGE_CHARS = 4_000


def fork_history(messages: Sequence[Message]) -> tuple[dict[str, str], ...]:
    """Ana konuşmanın son user/assistant metinleri: araç çıktısı ve harness notu taşınmaz."""
    picked = [
        {"role": message.role, "content": message.content[:FORK_MESSAGE_CHARS]}
        for message in messages
        if message.role in {"user", "assistant"}
        and not message.harness_note
        and message.content.strip()
    ]
    return tuple(picked[-FORK_MESSAGES:])


def last_user_text(messages: Sequence[Message]) -> str:
    """Konuşmadaki son kullanıcı görevi (harness notu sayılmaz); yoksa boş."""
    for message in reversed(messages):
        if message.role == "user" and not message.harness_note and message.content.strip():
            return message.content
    return ""


#: Olay günlüğünden gösterilecek son satır sayısı.
LOG_TAIL_LINES = 12


def log_tail(store: BackgroundTaskStore, task_id: str, limit: int = LOG_TAIL_LINES) -> str:
    """İşçinin JSON-Lines olaylarından okunur kısa özet (son `limit` olay)."""
    try:
        lines = store.log_path(task_id).read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    readable: list[str] = []
    for line in lines[-limit * 4 :]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = str(event.get("event") or event.get("type") or "")
        detail = next(
            (str(event[key]) for key in ("name", "tool", "text", "message") if event.get(key)), ""
        )
        if kind:
            readable.append(f"{kind} {summarize(redact(detail), 100)}".rstrip())
    return "\n".join(readable[-limit:])
