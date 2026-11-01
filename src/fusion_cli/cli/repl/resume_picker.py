"""Claude Code oturum seçicisi (`/resume`, `fusion --resume`) tuşları ve süzgeçleri (#202).

Claude Code: satırda zaman, git dalı ve boyut görünür; Space önizler, Ctrl+R yeniden adlandırır,
Ctrl+A bütün projeleri, Ctrl+W bütün çalışma ağaçlarını gösterir, Ctrl+B yalnız geçerli dalın
oturumlarını bırakır; `/` ya da yazmak arar (`ChoiceSearch`; PR adresi yapıştırmak o PR'a
bağlı oturumu bulur), 1-9 doğrudan seçer. Varsayılan
liste geçerli çalışma ağacının (dizinin) oturumlarıdır. Yüzeyden bağımsız durum ve satırlar
burada; seçiciyi TUI (`FusionTui.await_choice`) ya da satır içi `ui.picker.pick` sürer.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ...core.redaction import redact
from ...ui import messages
from ...ui.picker import Choice
from . import linked_pr
from .resume_lookup import _other_projects
from .transcript_store import (
    _NAME_EVENT,
    TITLE_BUDGET,
    ConversationRef,
    current_git_branch,
    list_conversations,
    load_transcript_messages,
    transcript_events_path,
)

PREVIEW_KEY, RENAME_KEY = "space", "c-r"
ALL_PROJECTS_KEY, ALL_WORKTREES_KEY, BRANCH_KEY = "c-a", "c-w", "c-b"
KEYS = (PREVIEW_KEY, RENAME_KEY, ALL_PROJECTS_KEY, ALL_WORKTREES_KEY, BRANCH_KEY)
#: Seçicide gösterilen en çok satır (önceki `SESSION_LIST_LIMIT` ile aynı).
LIST_LIMIT = 50
#: Önizlemede gösterilen son mesaj sayısı.
PREVIEW_MESSAGES = 6
PREVIEW_CHARS = 200


@dataclass(frozen=True, slots=True)
class PickerView:
    """Seçicinin süzgeç durumu; tuşlar yeni bir görünüm üretir (değiştirmez)."""

    all_projects: bool = False
    all_worktrees: bool = False
    branch_only: bool = False

    def toggled(self, key: str) -> PickerView:
        if key == ALL_PROJECTS_KEY:
            return replace(self, all_projects=not self.all_projects)
        if key == ALL_WORKTREES_KEY:
            return replace(self, all_worktrees=not self.all_worktrees)
        if key == BRANCH_KEY:
            return replace(self, branch_only=not self.branch_only)
        return self


@dataclass(frozen=True, slots=True)
class Row:
    ref: ConversationRef
    events_path: Path
    #: Oturuma bağlı PR adresi (`linked_pr`); aramada eşleşir, satırda görünmez.
    pr_url: str = ""


def _pr_url(memory_dir: Path, conversation_id: str) -> str:
    link = linked_pr.load(memory_dir, conversation_id)
    return link.url if link is not None else ""


def rows(memory_dir: Path, root: Path, view: PickerView) -> list[Row]:
    """Görünüme göre oturumlar; en yeni önce."""
    current = transcript_events_path(memory_dir, root)
    paths = [current, *(_other_projects(memory_dir, root) if view.all_projects else ())]
    found = [
        Row(ref, path, _pr_url(memory_dir, ref.conversation_id))
        for path in paths
        for ref in list_conversations(memory_dir, root, events_path=path)
    ]
    here = str(root.expanduser().resolve())
    if not view.all_projects and not view.all_worktrees:
        found = [row for row in found if not row.ref.cwd or row.ref.cwd == here]
    if view.branch_only:
        branch = current_git_branch(root)
        found = [row for row in found if row.ref.git_branch == branch]
    found.sort(key=lambda row: row.ref.updated_at, reverse=True)
    return grouped(found[:LIST_LIMIT])


def _root_of(conversation_id: str, parents: dict[str, str]) -> str:
    seen = {conversation_id}
    while (parent := parents.get(conversation_id)) and parent not in seen:
        seen.add(parent)
        conversation_id = parent
    return conversation_id


def grouped(found: list[Row]) -> list[Row]:
    """Dallar (kopyalar) kök oturumlarının hemen altında; gruplar en yeni üyeye göre sıralı."""
    present = {row.ref.conversation_id for row in found}
    parents = {
        row.ref.conversation_id: row.ref.forked_from
        for row in found
        if row.ref.forked_from in present
    }
    order: dict[str, int] = {}
    for index, row in enumerate(found):
        order.setdefault(_root_of(row.ref.conversation_id, parents), index)
    return sorted(
        found,
        key=lambda row: (
            order[_root_of(row.ref.conversation_id, parents)],
            row.ref.conversation_id in parents,
            found.index(row),
        ),
    )


def is_branch(row: Row, found: list[Row]) -> bool:
    return any(other.ref.conversation_id == row.ref.forked_from for other in found)


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def _when(epoch: float) -> str:
    return time.strftime("%d/%m %H:%M", time.localtime(epoch)) if epoch else ""


def choices(found: list[Row]) -> list[Choice]:
    """Satırlar: başlık; açıklamada zaman · dal · boyut · mesaj sayısı (Claude Code sütunları)."""
    result = []
    for row in found:
        ref = row.ref
        parts = [_when(ref.updated_at), ref.git_branch, human_size(ref.size_bytes)]
        detail = " · ".join(part for part in parts if part)
        result.append(
            Choice(
                ref.conversation_id,
                f"{messages.SESSION_BRANCH_MARK}{ref.title}"
                if is_branch(row, found)
                else ref.title,
                messages.SESSION_PICKER_DETAIL.format(detail=detail, count=ref.message_count),
                keywords=row.pr_url,
            )
        )
    return result


def title(view: PickerView) -> str:
    scope = (
        messages.SESSION_SCOPE_ALL_PROJECTS
        if view.all_projects
        else messages.SESSION_SCOPE_ALL_WORKTREES
        if view.all_worktrees
        else messages.SESSION_SCOPE_HERE
    )
    branch = messages.SESSION_SCOPE_BRANCH if view.branch_only else ""
    return messages.SESSION_PICKER_TITLE.format(scope=scope, branch=branch)


def split(picked: str) -> tuple[str, str]:
    for key in KEYS:
        if picked.startswith(f"{key}:"):
            return key, picked[len(key) + 1 :]
    return "", picked


def find(found: list[Row], conversation_id: str) -> Row | None:
    return next((row for row in found if row.ref.conversation_id == conversation_id), None)


def preview_rows(memory_dir: Path, root: Path, row: Row) -> list[Choice]:
    """Space önizlemesi: oturumun son mesajları (salt okunur satırlar)."""
    history = load_transcript_messages(
        memory_dir, root, conversation_id=row.ref.conversation_id, events_path=row.events_path
    )
    lines: list[Choice] = []
    for index, message in enumerate(history[-PREVIEW_MESSAGES:]):
        text = " ".join(message.content.split())[:PREVIEW_CHARS]
        speaker = messages.SESSION_PREVIEW_USER if message.role == "user" else ""
        lines.append(Choice(f"onizleme:{index}", f"{speaker}{text}"))
    return lines or [Choice("onizleme:0", messages.SESSION_PREVIEW_EMPTY)]


def rename(row: Row, name: str) -> bool:
    """Ctrl+R: oturuma ad ver (son ad geçerlidir; `/rename` ile aynı olay)."""
    cleaned = name.strip()
    if not cleaned:
        return False
    payload = {
        "session_id": row.ref.conversation_id,
        "timestamp": time.time(),
        "event": _NAME_EVENT,
        "name": redact(cleaned)[:TITLE_BUDGET],
    }
    try:
        with row.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return False
    return True


#: (başlık, satırlar, ek tuşlar, imlecin değeri) → seçim; önizleme de aynı seçiciyle gösterilir.
Asker = Callable[[str, Sequence[Choice], tuple[str, ...], str], str | None]
AsyncAsker = Callable[[str, Sequence[Choice], tuple[str, ...], str], Awaitable[str | None]]


@dataclass(frozen=True, slots=True)
class Step:
    """Bir seçimin sonucu: seçilen kimlik, yeni görünüm ya da önizleme/ad isteği."""

    chosen: str | None = None
    done: bool = False
    view: PickerView = PickerView()
    preview: Row | None = None
    rename: Row | None = None
    highlight: str = ""


def step(picked: str | None, view: PickerView, found: list[Row]) -> Step:
    if picked is None:
        return Step(done=True)
    key, value = split(picked)
    if not key:
        return Step(chosen=value, done=True)
    row = find(found, value)
    if key == PREVIEW_KEY:
        return Step(view=view, preview=row, highlight=value)
    if key == RENAME_KEY:
        return Step(view=view, rename=row, highlight=value)
    return Step(view=view.toggled(key), highlight=value)


def run(memory_dir: Path, root: Path, ask: Asker, ask_text: Callable[[], str]) -> str | None:
    """Satır içi seçici sürücüsü; seçilen sohbet kimliği ya da vazgeçmede None."""
    view, highlight = PickerView(), ""
    while True:
        found = rows(memory_dir, root, view)
        current = step(ask(title(view), choices(found), KEYS, highlight), view, found)
        if current.done:
            return current.chosen
        view, highlight = current.view, current.highlight
        if current.preview is not None:
            ask(
                messages.SESSION_PREVIEW_TITLE,
                preview_rows(memory_dir, root, current.preview),
                (),
                "",
            )
        if current.rename is not None:
            rename(current.rename, ask_text())


async def run_async(
    memory_dir: Path, root: Path, ask: AsyncAsker, ask_text: Callable[[], Awaitable[str]]
) -> str | None:
    """Tam ekran TUI sürücüsü (`run` ile aynı akış)."""
    view, highlight = PickerView(), ""
    while True:
        found = rows(memory_dir, root, view)
        current = step(await ask(title(view), choices(found), KEYS, highlight), view, found)
        if current.done:
            return current.chosen
        view, highlight = current.view, current.highlight
        if current.preview is not None:
            rows_ = preview_rows(memory_dir, root, current.preview)
            await ask(messages.SESSION_PREVIEW_TITLE, rows_, (), "")
        if current.rename is not None:
            rename(current.rename, await ask_text())
