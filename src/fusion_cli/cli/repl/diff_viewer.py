"""`/diff` etkileşimli görüntüleyici (#230, Claude Code "Review changes with /diff").

Claude Code `/diff` görüntüleyicisi: sol/sağ oklar git çalışma ağacı farkı ile Claude'un tek
tek turları arasında geçer, yukarı/aşağı dosyaları gezer, Enter dosyanın farkını açar.
Fusion: ilk görünüm `git diff HEAD`, sonrakiler tur checkpoint defterindeki (`/rewind`)
dosya değiştiren turlar. Tur farkı, turun ilk anlık görüntüsü ile o dosyayı sonra değiştiren
ilk turun anlık görüntüsü (yoksa dosyanın şimdiki hâli) arasındadır. Salt okurdur.
"""

from __future__ import annotations

import difflib
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ...core.changeset import Snapshot
from ...ui import messages
from ...ui.picker import Choice
from .diff_command import _git, _relative
from .state import ReplState

VIEW_KEYS = ("left", "right")
#: Bir dosya farkından gösterilecek en çok satır.
FILE_DIFF_MAX_LINES = 400
AsyncAsker = Callable[[str, Sequence[Choice], tuple[str, ...], str], Awaitable[str | None]]


@dataclass(frozen=True, slots=True)
class DiffView:
    """Bir görünüm: başlık ve dosya → fark satırları üreticisi."""

    title: str
    files: tuple[str, ...]
    diff_of: Callable[[str], list[str]]


#: Ad kaçışsız (`-z`, `core.quotepath` kapalı), yeniden adlandırma iki ayrı dosya (`old => new`
#: biçimi pathspec olamaz); fark açılırken ad glob değil birebir yol (`:(literal)`).
_GIT_QUIET_NAMES = ("-c", "core.quotepath=false")


def _numstat_files(numstat: str) -> tuple[str, ...]:
    """`git diff --numstat -z --no-renames` çıktısı: `ekl<TAB>sil<TAB>ad<NUL>` kayıtları."""
    records = (record.split("\t", 2) for record in numstat.split("\0"))
    return tuple(parts[2] for parts in records if len(parts) == 3 and parts[2])


def _git_view(state: ReplState) -> DiffView | None:
    numstat = _git(state.root, *_GIT_QUIET_NAMES, "diff", "HEAD", "--numstat", "-z", "--no-renames")
    if numstat is None:
        return None
    files = _numstat_files(numstat)

    def _diff(name: str) -> list[str]:
        output = _git(
            state.root, *_GIT_QUIET_NAMES, "diff", "HEAD", "--no-renames", "--", f":(literal){name}"
        )
        return (output or "").splitlines()

    return DiffView(messages.DIFF_VIEW_GIT, files, _diff)


def _text(content: bytes | None) -> list[str]:
    if content is None:
        return []
    return content.decode("utf-8", errors="replace").splitlines()


def _after(state: ReplState, index: int, path: Path) -> bytes | None:
    """Turdan sonraki hâl: dosyayı sonra değiştiren turun anlık görüntüsü ya da şimdiki dosya."""
    for entry in state.checkpoints.entries():
        if entry.index <= index:
            continue
        for snapshot in entry.changes.snapshots:
            if snapshot.path == path:
                return snapshot.content
    try:
        return path.read_bytes()
    except OSError:
        return None


def _turn_views(state: ReplState) -> list[DiffView]:
    views = []
    for entry in state.checkpoints.entries():
        snapshots = {_relative(s.path, state.root): s for s in entry.changes.snapshots}
        if not snapshots:
            continue

        def _diff(
            name: str, snapshots: dict[str, Snapshot] = snapshots, index: int = entry.index
        ) -> list[str]:
            snapshot = snapshots[name]
            after = _after(state, index, snapshot.path)
            return list(
                difflib.unified_diff(
                    _text(snapshot.content),
                    _text(after),
                    fromfile=f"a/{name}",
                    tofile=f"b/{name}",
                    lineterm="",
                )
            )

        task = entry.task.strip().splitlines()[0][:60] if entry.task.strip() else ""
        title = messages.DIFF_VIEW_TURN.format(index=entry.index, task=task)
        views.append(DiffView(title, tuple(snapshots), _diff))
    return views


def views(state: ReplState) -> list[DiffView]:
    git = _git_view(state)
    return [*([git] if git is not None else []), *_turn_views(state)]


def file_rows(view: DiffView) -> list[Choice]:
    if not view.files:
        return [Choice("bilgi:bos", messages.DIFF_VIEW_EMPTY)]
    return [Choice(f"dosya:{name}", name) for name in view.files]


def diff_rows(lines: list[str]) -> list[Choice]:
    shown = lines[:FILE_DIFF_MAX_LINES] or [messages.DIFF_VIEW_NO_CHANGE]
    rows = [Choice(f"satir:{index}", line or " ") for index, line in enumerate(shown)]
    if len(lines) > FILE_DIFF_MAX_LINES:
        rows.append(
            Choice(
                "satir:son", messages.DIFF_TRUNCATED.format(count=len(lines) - FILE_DIFF_MAX_LINES)
            )
        )
    return rows


def _title(all_views: list[DiffView], position: int) -> str:
    return messages.DIFF_VIEW_TITLE.format(
        title=all_views[position].title, position=position + 1, total=len(all_views)
    )


def _split(picked: str) -> tuple[str, str]:
    for key in VIEW_KEYS:
        if picked.startswith(f"{key}:"):
            return key, picked[len(key) + 1 :]
    return "", picked


async def run_async(state: ReplState, ask: AsyncAsker) -> bool:
    """Görüntüleyiciyi sür; gösterilecek bir şey yoksa False (çağıran metin basar)."""
    all_views = views(state)
    if not all_views:
        return False
    position = 0
    while True:
        view = all_views[position]
        picked = await ask(_title(all_views, position), file_rows(view), VIEW_KEYS, "")
        if picked is None:
            return True
        key, value = _split(picked)
        if key:
            step = -1 if key == "left" else 1
            position = max(0, min(len(all_views) - 1, position + step))
            continue
        if value.startswith("dosya:"):
            name = value.removeprefix("dosya:")
            await ask(name, diff_rows(view.diff_of(name)), (), "")
