"""`/export` ve `/copy` işleyicileri (P-028, #206).

`/export [dosya]` Claude Code'daki gibi konuşmayı DÜZ METİN olarak aktarır: dosya adı
verilirse doğrudan yazar (uzantısızsa `.txt` eklenir), verilmezse Pano/Dosya seçicisi açar.
Fusion ekleri: `md`/`json` bayrakları ya da `.md`/`.json` uzantısı biçimi seçer, `pano`
doğrudan panoya, `dosya` varsayılan adla dosyaya yazar. Dosya PROJE KÖKÜ (ya da `--add-dir`
kökleri) dışına yazılmaz; var olan dosya onaysız EZİLMEZ (`zorla` ister; Ölçüldü 31 Ekim:
`/export README.md` kaynak dosyayı geri alma kaydı olmadan eziyordu). `/copy [N]` sondan N.
asistan cevabını panoya kopyalar.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from ...core.transcript_export import (
    default_export_name,
    export_json,
    export_markdown,
    export_text,
    last_answer,
)
from ...ui import messages
from ...ui.clipboard import ClipboardResult, copy_to_clipboard
from ...ui.picker import Choice, pick
from .state import ReplState

#: Panoya yazan yardımcı; testte sahte verilir.
Copier = Callable[[str], ClipboardResult]
#: Seçici (`ui.picker.pick` imzası); testte sahte verilir.
Picker = Callable[..., str | None]

_JSON_FLAGS = frozenset({"json", "--json"})
_MARKDOWN_FLAGS = frozenset({"md", "--md", "markdown", "--markdown"})
_CLIPBOARD_FLAGS = frozenset({"pano", "--pano", "clipboard", "--clipboard"})
_FILE_FLAGS = frozenset({"dosya", "--dosya", "file", "--file"})
_FORCE_FLAGS = frozenset({"zorla", "--zorla", "force", "--force"})
_ALL_FLAGS = _JSON_FLAGS | _MARKDOWN_FLAGS | _CLIPBOARD_FLAGS | _FILE_FLAGS | _FORCE_FLAGS
#: Biçim → (üretici, varsayılan uzantı).
_FORMATS = {
    "text": (export_text, "txt"),
    "markdown": (export_markdown, "md"),
    "json": (export_json, "json"),
}
_SUFFIX_FORMATS = {".md": "markdown", ".markdown": "markdown", ".json": "json"}


def export_dialog_choices() -> tuple[Choice, ...]:
    """Argümansız `/export` seçicisi: Claude Code'daki Pano / Dosya diyaloğu."""
    return (
        Choice("pano", messages.EXPORT_CHOICE_CLIPBOARD, messages.EXPORT_CHOICE_CLIPBOARD_HINT),
        Choice("dosya", messages.EXPORT_CHOICE_FILE, messages.EXPORT_CHOICE_FILE_HINT),
    )


def _title(state: ReplState) -> str:
    first = next((m.content for m in state.history if m.role == "user" and m.content.strip()), "")
    return first.strip().splitlines()[0][:80] if first else messages.EXPORT_DEFAULT_TITLE


def _inside_roots(state: ReplState, target: Path) -> bool:
    concrete = target.resolve()
    roots = (state.root, *state.extra_roots)
    return any(concrete == root.resolve() or root.resolve() in concrete.parents for root in roots)


def _format_for(words: Sequence[str], paths: Sequence[str]) -> str:
    lowered = {word.lower() for word in words}
    if lowered & _JSON_FLAGS:
        return "json"
    if lowered & _MARKDOWN_FLAGS:
        return "markdown"
    suffix = Path(paths[0]).suffix.lower() if paths else ""
    return _SUFFIX_FORMATS.get(suffix, "text")


def export_transcript(
    state: ReplState,
    argument: str,
    *,
    copier: Copier = copy_to_clipboard,
    now: Callable[[], float] = time.time,
    picker: Picker = pick,
) -> str:
    """`/export` — konuşmayı düz metin (ya da md/json) dosyasına veya panoya aktar."""
    if not any(m.role in ("user", "assistant") for m in state.history):
        return messages.EXPORT_EMPTY
    words = argument.split()
    if not words:
        chosen = picker(export_dialog_choices(), title=messages.EXPORT_DIALOG_TITLE)
        if chosen is None:
            return ""
        words = [chosen]
    paths = [word for word in words if word.lower() not in _ALL_FLAGS]
    fmt = _format_for(words, paths)
    produce, ext = _FORMATS[fmt]
    text = produce(state.history, title=_title(state))
    if any(word.lower() in _CLIPBOARD_FLAGS for word in words):
        result = copier(text)
        if not result.ok:
            return messages.CLIPBOARD_FAILED.format(error=result.error)
        return messages.EXPORT_COPIED.format(chars=len(text))
    force = any(word.lower() in _FORCE_FLAGS for word in words)
    return _write(state, paths[0] if paths else "", text, ext=ext, force=force, now=now)


def _write(
    state: ReplState, raw: str, text: str, *, ext: str, force: bool, now: Callable[[], float]
) -> str:
    target = Path(raw or default_export_name(ext=ext, now=now)).expanduser()
    if not target.suffix and raw:
        target = target.with_name(f"{target.name}.{ext}")
    if not target.is_absolute():
        target = state.root / target
    if not _inside_roots(state, target):
        return messages.EXPORT_OUTSIDE_ROOT.format(path=target, root=state.root)
    if target.is_dir():
        target = target / default_export_name(ext=ext, now=now)
    if target.exists() and not force:
        return messages.EXPORT_EXISTS.format(path=target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError as error:
        return messages.EXPORT_WRITE_FAILED.format(path=target, error=error)
    return messages.EXPORT_WRITTEN.format(path=target, chars=len(text))


def copy_answer(state: ReplState, argument: str, *, copier: Copier = copy_to_clipboard) -> str:
    """`/copy [N]` — sondan N. asistan cevabını panoya kopyala (varsayılan: son)."""
    wanted = argument.strip()
    try:
        index = int(wanted) if wanted else 1
    except ValueError:
        return messages.COPY_USAGE
    answer = last_answer(state.history, index)
    if answer is None:
        return messages.COPY_NOTHING
    result = copier(answer)
    if not result.ok:
        return messages.CLIPBOARD_FAILED.format(error=result.error)
    return messages.COPY_DONE.format(chars=len(answer))
