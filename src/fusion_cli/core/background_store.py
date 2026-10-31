"""Arka plan görev deposu: `<taban>/<kimlik>/` klasörlerini okur ve güvenle günceller (P-048).

Sözleşme ve klasör düzeni `background_tasks` modülündedir; bu modül yalnız disk işlemleridir.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path

from .atomic_file import atomic_replace_text
from .background_tasks import (
    ANSWER_FILE,
    HEARTBEAT_FILE,
    HISTORY_FILE,
    INBOX_FILE,
    LOCK_FILE,
    LOG_FILE,
    NAME_MAX_CHARS,
    PROMPT_MAX_CHARS,
    QUESTION_FILE,
    QUEUED_GRACE_S,
    RESULT_FILE,
    STALE_AFTER_S,
    STOP_FILE,
    TASK_FILE,
    TASK_ID_PATTERN,
    BackgroundTask,
    BackgroundTaskError,
    InboxMessage,
    ShortLease,
    TaskOptions,
    TaskStatus,
    normalize_name,
    read_json_list,
    read_json_object,
)
from .file_lease import FileLease
from .protocols import Clock


class BackgroundTaskStore:
    """`<taban>/<kimlik>/` klasörlerindeki görevleri okuyup güvenle günceller."""

    def __init__(
        self,
        base_dir: Path,
        clock: Clock,
        *,
        new_id: Callable[[], str] | None = None,
    ) -> None:
        self._base = base_dir
        self._clock = clock
        self._new_id = new_id or (lambda: uuid.uuid4().hex[:8])

    @property
    def base_dir(self) -> Path:
        return self._base

    def now(self) -> float:
        return self._clock.now()

    def task_dir(self, task_id: str) -> Path:
        if not TASK_ID_PATTERN.match(task_id):
            raise BackgroundTaskError(f"Geçersiz görev kimliği: {task_id!r}")
        return self._base / task_id

    # ------------------------------------------------------------------ kayıt

    def create(
        self,
        prompt: str,
        *,
        root: Path,
        name: str = "",
        owner: str = "",
        origin: str = "cli",
        mode: str = "auto",
        agent: str = "",
        read_only: bool = False,
        max_turns: int = 0,
        history: list[dict[str, str]] | None = None,
        options: TaskOptions | None = None,
    ) -> BackgroundTask:
        text = prompt.strip()
        if not text:
            raise BackgroundTaskError("Arka plan görevi boş olamaz.")
        if len(text) > PROMPT_MAX_CHARS:
            raise BackgroundTaskError(
                f"Görev metni çok uzun ({len(text)} karakter; sınır {PROMPT_MAX_CHARS})."
            )
        while True:
            task_id = self._new_id()
            folder = self.task_dir(task_id)
            try:
                folder.mkdir(parents=True, mode=0o700)
                break
            except FileExistsError:
                continue
        now = self._clock.now()
        task = BackgroundTask(
            id=task_id,
            name=self._unique_name(normalize_name(name) or f"gorev-{task_id[:4]}", task_id),
            prompt=text,
            root=str(root.resolve()),
            status=TaskStatus.QUEUED,
            created_at=now,
            updated_at=now,
            owner=owner,
            origin=origin,
            mode=mode,
            agent=agent,
            read_only=read_only,
            max_turns=max_turns,
            options=options or TaskOptions(),
        )
        if history:
            atomic_replace_text(folder / HISTORY_FILE, json.dumps(history, ensure_ascii=False))
        atomic_replace_text(folder / TASK_FILE, json.dumps(task.to_dict(), ensure_ascii=False))
        return task

    def get(self, task_id: str) -> BackgroundTask:
        path = self.task_dir(task_id) / TASK_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise BackgroundTaskError(f"Arka plan görevi bulunamadı: {task_id}") from None
        except (OSError, json.JSONDecodeError) as error:
            raise BackgroundTaskError("Arka plan görev kaydı okunamadı.") from error
        if not isinstance(raw, dict):
            raise BackgroundTaskError("Arka plan görev kaydı bozuk.")
        return self._with_liveness(BackgroundTask.from_dict(raw))

    def update(self, task_id: str, **changes: object) -> BackgroundTask:
        """Kaydı kilit altında oku-değiştir-yaz; yeni kaydı döndür."""
        with self._locked(task_id):
            return self._write(replace(self._read_raw(task_id), **changes))  # type: ignore[arg-type]

    def tasks(self, *, root: Path | None = None) -> tuple[BackgroundTask, ...]:
        """Görevler, en yeni önce; `root` verilirse yalnız o projenin görevleri."""
        if not self._base.is_dir():
            return ()
        wanted = str(root.resolve()) if root is not None else None
        tasks: list[BackgroundTask] = []
        for folder in self._base.iterdir():
            if not TASK_ID_PATTERN.match(folder.name):
                continue
            try:
                task = self.get(folder.name)
            except BackgroundTaskError:
                continue
            if wanted is None or task.root == wanted:
                tasks.append(task)
        return tuple(sorted(tasks, key=lambda item: item.created_at, reverse=True))

    def resolve(self, query: str, *, root: Path | None = None) -> BackgroundTask:
        """Kimlik, kimlik öneki (≥4) ya da ad ile görevi bul; belirsizse hata."""
        wanted = query.strip().casefold()
        if not wanted:
            raise BackgroundTaskError("Görev kimliği ya da adı gerekli.")
        tasks = self.tasks(root=root)
        exact = [task for task in tasks if wanted in (task.id, task.name)]
        if len(exact) == 1:
            return exact[0]
        prefixed = [task for task in tasks if len(wanted) >= 4 and task.id.startswith(wanted)]
        matches = exact or prefixed
        if not matches:
            raise BackgroundTaskError(f"Arka plan görevi bulunamadı: {query}")
        if len(matches) > 1:
            raise BackgroundTaskError(f"'{query}' birden çok göreve uyuyor; kimliği yaz.")
        return matches[0]

    def active_count(self) -> int:
        return sum(1 for task in self.tasks() if task.is_active)

    def remove(self, task_id: str) -> None:
        """Etkin olmayan görevin klasörünü sil (yalnız bu deponun dosyaları)."""
        task = self.get(task_id)
        if task.is_active:
            raise BackgroundTaskError("Çalışan görev silinemez; önce durdur.")
        folder = self.task_dir(task_id)
        for item in folder.iterdir():
            if item.is_file() or item.is_symlink():
                item.unlink()
        folder.rmdir()

    # --------------------------------------------------------- gelen kutusu

    def append_inbox(self, task_id: str, message: InboxMessage) -> bool:
        """Mesajı ekle; işçi artık yoksa görevi yeniden sıraya al. İşçi gerekiyorsa True.

        Ekleme ve durum kararı TEK kilit altındadır (`finish_unless_inbox` ile aynı kilit):
        bitmek üzere olan işçi mesajı ya görür ya da "bitti" yazmış olur; iki gönderen aynı
        anda ikinci/üçüncü işçiyi başlatamaz.
        """
        if not message.text.strip():
            raise BackgroundTaskError("Boş mesaj gönderilemez.")
        if len(message.text) > PROMPT_MAX_CHARS:
            raise BackgroundTaskError(f"Mesaj çok uzun (sınır {PROMPT_MAX_CHARS} karakter).")
        with self._locked(task_id):
            path = self.task_dir(task_id) / INBOX_FILE
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(asdict(message), ensure_ascii=False) + "\n")
            task = self._with_liveness(self._read_raw(task_id))
            if task.is_active:
                return False
            (self.task_dir(task_id) / STOP_FILE).unlink(missing_ok=True)
            self._write(replace(task, status=TaskStatus.QUEUED, note="", pid=0))
            return True

    def take_inbox(self, task_id: str) -> tuple[InboxMessage, ...]:
        with self._locked(task_id):
            return self._take_inbox_locked(task_id)

    def finish_unless_inbox(
        self, task_id: str, **changes: object
    ) -> tuple[BackgroundTask, tuple[InboxMessage, ...]]:
        """Gelen kutusu boşsa kaydı bitmiş duruma geçir; doluysa mesajları ver.

        Tek kilit altında yapılır: işçi "bitti" yazarken gelen mesaj kaybolmasın ya da
        gönderen işçinin çıktığını sanıp ikinci bir işçi başlatmasın.
        """
        with self._locked(task_id):
            messages = self._take_inbox_locked(task_id)
            if messages:
                return self._read_raw(task_id), messages
            task = self._write(replace(self._read_raw(task_id), **changes))  # type: ignore[arg-type]
            return task, ()

    def _take_inbox_locked(self, task_id: str) -> tuple[InboxMessage, ...]:
        path = self.task_dir(task_id) / INBOX_FILE
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return ()
        path.unlink()
        messages: list[InboxMessage] = []
        for line in lines:
            try:
                raw = json.loads(line)
                messages.append(InboxMessage(**raw))
            except (json.JSONDecodeError, TypeError):
                continue
        return tuple(messages)

    # ------------------------------------------------ durdurma / nabız

    def request_stop(self, task_id: str) -> None:
        atomic_replace_text(self.task_dir(task_id) / STOP_FILE, str(self._clock.now()))

    def stop_requested(self, task_id: str) -> bool:
        return (self.task_dir(task_id) / STOP_FILE).exists()

    def clear_stop(self, task_id: str) -> None:
        (self.task_dir(task_id) / STOP_FILE).unlink(missing_ok=True)

    def heartbeat(self, task_id: str) -> None:
        atomic_replace_text(self.task_dir(task_id) / HEARTBEAT_FILE, str(self._clock.now()))

    # -------------------------------------------------------- soru / cevap

    def ask(self, task_id: str, request_id: str, payload: Mapping[str, object]) -> None:
        body = {"istek_id": request_id, **payload}
        atomic_replace_text(
            self.task_dir(task_id) / QUESTION_FILE, json.dumps(body, ensure_ascii=False)
        )
        (self.task_dir(task_id) / ANSWER_FILE).unlink(missing_ok=True)

    def pending_question(self, task_id: str) -> dict[str, object] | None:
        return read_json_object(self.task_dir(task_id) / QUESTION_FILE)

    def answer(self, task_id: str, value: str) -> str:
        """Bekleyen isteğe cevap yaz; istek yoksa hata. Cevaplanan istek kimliği döner."""
        question = self.pending_question(task_id)
        if question is None:
            raise BackgroundTaskError("Bu görevde bekleyen bir onay ya da soru yok.")
        request_id = str(question.get("istek_id", ""))
        body = {"istek_id": request_id, "cevap": value.strip()}
        atomic_replace_text(self.task_dir(task_id) / ANSWER_FILE, json.dumps(body))
        return request_id

    def take_answer(self, task_id: str, request_id: str) -> str | None:
        folder = self.task_dir(task_id)
        reply = read_json_object(folder / ANSWER_FILE)
        if reply is None or str(reply.get("istek_id")) != request_id:
            return None
        (folder / ANSWER_FILE).unlink(missing_ok=True)
        (folder / QUESTION_FILE).unlink(missing_ok=True)
        return str(reply.get("cevap", ""))

    def clear_question(self, task_id: str) -> None:
        (self.task_dir(task_id) / QUESTION_FILE).unlink(missing_ok=True)

    # ------------------------------------------------- sonuç / geçmiş / kayıt

    def write_result(self, task_id: str, text: str) -> None:
        atomic_replace_text(self.task_dir(task_id) / RESULT_FILE, text)

    def read_result(self, task_id: str) -> str:
        try:
            return (self.task_dir(task_id) / RESULT_FILE).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def load_history(self, task_id: str) -> list[dict[str, str]]:
        raw = read_json_list(self.task_dir(task_id) / HISTORY_FILE)
        return [
            {"role": str(item["role"]), "content": str(item["content"])}
            for item in raw
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
        ]

    def save_history(self, task_id: str, history: list[dict[str, str]]) -> None:
        atomic_replace_text(
            self.task_dir(task_id) / HISTORY_FILE, json.dumps(history, ensure_ascii=False)
        )

    def log_path(self, task_id: str) -> Path:
        return self.task_dir(task_id) / LOG_FILE

    # ------------------------------------------------------------ iç işler

    def _unique_name(self, name: str, task_id: str) -> str:
        taken = {task.name for task in self.tasks() if task.id != task_id}
        candidate, counter = name, 2
        while candidate in taken:
            candidate = f"{name[: NAME_MAX_CHARS - 3]}-{counter}"
            counter += 1
        return candidate

    def _read_raw(self, task_id: str) -> BackgroundTask:
        raw = read_json_object(self.task_dir(task_id) / TASK_FILE)
        if raw is None:
            raise BackgroundTaskError(f"Arka plan görevi bulunamadı: {task_id}")
        return BackgroundTask.from_dict(raw)

    def _write(self, task: BackgroundTask) -> BackgroundTask:
        stamped = replace(task, updated_at=self._clock.now())
        atomic_replace_text(
            self.task_dir(task.id) / TASK_FILE, json.dumps(stamped.to_dict(), ensure_ascii=False)
        )
        return stamped

    def _with_liveness(self, task: BackgroundTask) -> BackgroundTask:
        """Etkin görünen ama işçisi susmuş görevi `yarim_kaldi` olarak göster (diske yazmaz)."""
        if not task.is_active:
            return task
        now = self._clock.now()
        if task.status is TaskStatus.QUEUED:
            return task if now - task.updated_at <= QUEUED_GRACE_S else _lost(task)
        try:
            beat = (self.task_dir(task.id) / HEARTBEAT_FILE).stat().st_mtime
        except FileNotFoundError:
            beat = task.updated_at
        return task if now - beat <= STALE_AFTER_S else _lost(task)

    def _locked(self, task_id: str) -> ShortLease:
        return ShortLease(FileLease(self.task_dir(task_id) / LOCK_FILE))


def _lost(task: BackgroundTask) -> BackgroundTask:
    return replace(task, status=TaskStatus.LOST)
