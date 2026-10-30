"""`/export` ve `/copy` işleyicileri (P-028).

`/export [yol] [json] [pano]` konuşmayı dosyaya (varsayılan: proje kökünde
`fusion-sohbet-<tarih>.md`) ya da panoya yazar. Dosya PROJE KÖKÜ (ya da `--add-dir`
kökleri) dışına yazılmaz: "proje kökü dışına yazma onaysız olmaz" ilkesi.
`/copy [N]` sondan N. asistan cevabını panoya kopyalar.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from ...core.transcript_export import (
    default_export_name,
    export_json,
    export_markdown,
    last_answer,
)
from ...ui import messages
from ...ui.clipboard import ClipboardResult, copy_to_clipboard
from .state import ReplState

#: Panoya yazan yardımcı; testte sahte verilir.
Copier = Callable[[str], ClipboardResult]

_JSON_FLAGS = frozenset({"json", "--json"})
_CLIPBOARD_FLAGS = frozenset({"pano", "--pano", "clipboard", "--clipboard"})


def _title(state: ReplState) -> str:
    first = next((m.content for m in state.history if m.role == "user" and m.content.strip()), "")
    return first.strip().splitlines()[0][:80] if first else messages.EXPORT_DEFAULT_TITLE


def _inside_roots(state: ReplState, target: Path) -> bool:
    concrete = target.resolve()
    roots = (state.root, *state.extra_roots)
    return any(concrete == root.resolve() or root.resolve() in concrete.parents for root in roots)


def export_transcript(
    state: ReplState,
    argument: str,
    *,
    copier: Copier = copy_to_clipboard,
    now: Callable[[], float] = time.time,
) -> str:
    """`/export` — konuşmayı Markdown/JSON dosyasına ya da panoya aktar."""
    if not any(m.role in ("user", "assistant") for m in state.history):
        return messages.EXPORT_EMPTY
    words = argument.split()
    as_json = any(word.lower() in _JSON_FLAGS for word in words)
    to_clipboard = any(word.lower() in _CLIPBOARD_FLAGS for word in words)
    paths = [word for word in words if word.lower() not in _JSON_FLAGS | _CLIPBOARD_FLAGS]
    title = _title(state)
    text = (
        export_json(state.history, title=title)
        if as_json
        else export_markdown(state.history, title=title)
    )
    if to_clipboard:
        result = copier(text)
        if not result.ok:
            return messages.CLIPBOARD_FAILED.format(error=result.error)
        return messages.EXPORT_COPIED.format(chars=len(text))
    raw = paths[0] if paths else default_export_name(as_json=as_json, now=now)
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = state.root / target
    if not _inside_roots(state, target):
        return messages.EXPORT_OUTSIDE_ROOT.format(path=target, root=state.root)
    if target.is_dir():
        target = target / default_export_name(as_json=as_json, now=now)
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
