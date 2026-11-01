"""Argümansız `--resume` / `-r` oturum seçicisini açar (#188).

Claude Code: `claude --resume` değer verilmezse etkileşimli seçiciyi açar; değer kimlik ya
da ad olabilir. Ölçüldü (1 Kasım): typer seçeneği değer zorunlu tutuyordu ve argümansız
`fusion --resume` "requires an argument" hatasıyla çıkıyordu. typer isteğe bağlı değerli
seçenek tanımadığı için giriş noktası argümansız bayrağa seçici işaretini ekler.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from ...core.errors import SessionNotFoundError
from ...ui import messages
from ...ui.picker import Choice, pick
from .transcript_store import list_conversations

#: Argümansız `--resume` yerine konan işaret; bir sohbet adı olamaz (kontrol karakteri).
RESUME_PICKER = "\x1fsecici"
_RESUME_FLAGS = frozenset({"--resume", "-r"})

Chooser = Callable[[list[Choice], str], str | None]


def normalize_resume_argv(argv: Sequence[str]) -> list[str]:
    """Değersiz `--resume`/`-r` (sonda ya da ardından başka seçenek) için seçici işareti ekle."""
    result: list[str] = []
    for index, token in enumerate(argv):
        result.append(token)
        if token not in _RESUME_FLAGS:
            continue
        following = argv[index + 1] if index + 1 < len(argv) else None
        if following is None or following.startswith("-"):
            result.append(RESUME_PICKER)
    return result


def _default_chooser(choices: list[Choice], title: str) -> str | None:
    return pick(choices, title=title)


def pick_conversation(memory_dir: Path, root: Path, chooser: Chooser | None = None) -> str:
    """Bu projedeki sohbetlerden birini seçtir ve kimliğini döndür."""
    from .session_resume import resume_choices

    refs = list_conversations(memory_dir, root)
    if not refs:
        raise SessionNotFoundError(messages.SESSION_LIST_EMPTY)
    chosen = (chooser or _default_chooser)(resume_choices(refs), messages.SESSION_PICK_TITLE)
    if not chosen:
        raise SessionNotFoundError(messages.SESSION_PICK_CANCELLED)
    return chosen
