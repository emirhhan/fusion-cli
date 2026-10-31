"""Ajan ekibinin paylaşımlı görev listesi ve posta kutusu (P-061): model ve dosya deposu.

Claude Code'daki `~/.claude/tasks/{team}/` ve `~/.claude/teams/{team}/inboxes/{agent}.json`
karşılığı PROJE içindedir (ekip o depo için kurulur):

    .fusion/ekip/<ad>/pano.json                 hedef, üyeler, görevler, okunma imleçleri
    .fusion/ekip/<ad>/gelen_kutusu/<üye>.jsonl  üyeye (ve "lider"e) gelen mesajlar

Depo senkrondur ve kilitsizdir; tek yazar `team_runtime.TeamSession`'dır (asyncio kilidi
altında, dosya işi thread'de). Değer nesneleri donmuştur; her değişiklik yeni pano üretir.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ...core.errors import FusionError
from ...tools.files import atomic_write

_LOG = logging.getLogger(__name__)

TEAMS_DIR = Path(".fusion") / "ekip"
BOARD_FILE = "pano.json"
INBOX_DIR = "gelen_kutusu"
LEAD = "lider"
BROADCAST = "herkes"
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
#: Görev durumları.
PENDING, RUNNING, DONE, FAILED = "bekliyor", "calisiyor", "tamam", "basarisiz"
#: Tek mesajın ve görev sonucunun saklanan en fazla karakteri.
MESSAGE_CHARS = 4_000
RESULT_CHARS = 4_000


class TeamError(FusionError):
    """Ekip isteği geçersiz (mesaj modele/kullanıcıya gider)."""


@dataclass(frozen=True, slots=True)
class TeamMember:
    name: str
    persona: str = ""
    read_only: bool = False
    write_scope: tuple[str, ...] = ()
    isolation: str = ""


@dataclass(frozen=True, slots=True)
class TeamTask:
    id: str
    title: str
    description: str = ""
    status: str = PENDING
    owner: str = ""
    depends_on: tuple[str, ...] = ()
    result: str = ""
    assignee: str = ""
    created_by: str = LEAD


@dataclass(frozen=True, slots=True)
class TeamMessage:
    sender: str
    recipient: str
    text: str
    at: float = 0.0


@dataclass(frozen=True, slots=True)
class TeamBoard:
    name: str
    goal: str
    members: tuple[TeamMember, ...]
    tasks: tuple[TeamTask, ...] = ()
    created_at: float = 0.0
    updated_at: float = 0.0
    #: (alıcı, okunan mesaj sayısı) — gelen kutusunun okunma imleci.
    read_counts: tuple[tuple[str, int], ...] = ()

    def member(self, name: str) -> TeamMember | None:
        return next((member for member in self.members if member.name == name), None)

    def task(self, task_id: str) -> TeamTask | None:
        return next((task for task in self.tasks if task.id == task_id), None)

    def read_count(self, recipient: str) -> int:
        return dict(self.read_counts).get(recipient, 0)

    def with_task(self, task: TeamTask) -> TeamBoard:
        tasks = tuple(task if item.id == task.id else item for item in self.tasks)
        if self.task(task.id) is None:
            tasks = (*tasks, task)
        return replace(self, tasks=tasks)

    def with_read_count(self, recipient: str, count: int) -> TeamBoard:
        counts = {**dict(self.read_counts), recipient: count}
        return replace(self, read_counts=tuple(sorted(counts.items())))

    def next_task_id(self) -> str:
        numbers = [int(task.id[1:]) for task in self.tasks if re.fullmatch(r"g\d+", task.id)]
        return f"g{max(numbers, default=0) + 1}"

    def is_claimable(self, task: TeamTask, member: str) -> bool:
        if task.status != PENDING or task.assignee not in {"", member}:
            return False
        return all(
            (dep := self.task(dep_id)) is not None and dep.status == DONE
            for dep_id in task.depends_on
        )

    def is_blocked(self, task: TeamTask) -> bool:
        """Bağımlılığı başarısız olduğu için hiç alınamayacak görev."""
        return task.status == PENDING and any(
            (dep := self.task(dep_id)) is None or dep.status == FAILED for dep_id in task.depends_on
        )


def check_name(name: str, what: str = "Ekip adı") -> str:
    cleaned = name.strip().casefold()
    if not NAME_PATTERN.match(cleaned):
        raise TeamError(f"{what} küçük harf, rakam, '-' ya da '_' olmalı (en fazla 40): {name!r}")
    if cleaned in {LEAD, BROADCAST}:
        raise TeamError(f"'{cleaned}' ayrılmış bir ad; başka bir ad seç.")
    return cleaned


class TeamStore:
    """`.fusion/ekip/` altındaki panolar ve gelen kutuları."""

    def __init__(self, root: Path) -> None:
        self.base = root / TEAMS_DIR

    def names(self) -> list[str]:
        if not self.base.is_dir():
            return []
        return sorted(
            path.name
            for path in self.base.iterdir()
            if (path / BOARD_FILE).is_file() and NAME_PATTERN.match(path.name)
        )

    def load(self, name: str) -> TeamBoard | None:
        path = self.base / name / BOARD_FILE
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as error:
            raise TeamError(f"{path} okunamadı: {error}") from error
        return _board_from(raw, name)

    def save(self, board: TeamBoard) -> None:
        directory = self.base / board.name
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write(
            directory / BOARD_FILE, json.dumps(asdict(board), ensure_ascii=False, indent=1)
        )

    def append(self, team: str, message: TeamMessage) -> None:
        directory = self.base / team / INBOX_DIR
        directory.mkdir(parents=True, exist_ok=True)
        line = json.dumps(asdict(message), ensure_ascii=False)
        with (directory / f"{message.recipient}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def inbox(self, team: str, recipient: str) -> list[TeamMessage]:
        path = self.base / team / INBOX_DIR / f"{recipient}.jsonl"
        if not path.is_file():
            return []
        messages: list[TeamMessage] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                raw = json.loads(line)
                messages.append(
                    TeamMessage(
                        str(raw["sender"]),
                        str(raw["recipient"]),
                        str(raw["text"]),
                        float(raw.get("at", 0)),
                    )
                )
        return messages

    def delete(self, name: str) -> bool:
        directory = self.base / name
        if not (directory / BOARD_FILE).is_file():
            return False
        shutil.rmtree(directory)
        return True


def _board_from(raw: object, name: str) -> TeamBoard:
    if not isinstance(raw, dict):
        raise TeamError(f"'{name}' panosu bozuk.")
    try:
        return TeamBoard(
            name=str(raw.get("name") or name),
            goal=str(raw.get("goal", "")),
            members=tuple(
                TeamMember(
                    name=str(item["name"]),
                    persona=str(item.get("persona", "")),
                    read_only=bool(item.get("read_only", False)),
                    write_scope=tuple(str(path) for path in item.get("write_scope", ())),
                    isolation=str(item.get("isolation", "")),
                )
                for item in raw.get("members", ())
            ),
            tasks=tuple(
                TeamTask(
                    id=str(item["id"]),
                    title=str(item.get("title", "")),
                    description=str(item.get("description", "")),
                    status=str(item.get("status", PENDING)),
                    owner=str(item.get("owner", "")),
                    depends_on=tuple(str(dep) for dep in item.get("depends_on", ())),
                    result=str(item.get("result", "")),
                    assignee=str(item.get("assignee", "")),
                    created_by=str(item.get("created_by", LEAD)),
                )
                for item in raw.get("tasks", ())
            ),
            created_at=float(raw.get("created_at", 0.0)),
            updated_at=float(raw.get("updated_at", 0.0)),
            read_counts=tuple((str(key), int(value)) for key, value in raw.get("read_counts", ())),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise TeamError(f"'{name}' panosu bozuk: {type(error).__name__}.") from error
