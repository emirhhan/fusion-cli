"""İnteraktif giriş — prompt_toolkit sarmalayıcısı.

Terminal TTY değilse (boru hattı, CI, test) prompt_toolkit hiç kurulmaz ve düz
`input()`'a düşülür; otomasyon kırılmaz.

Tasarım kararı: giriş satırı ve çalışan tur ASLA aynı anda ekranda olmaz. Eski
projede kalıcı bir giriş satırı ile Rich çıktısı aynı anda imleci yönetiyor,
satırlar birbirini bozuyordu. Burada tur çalışırken prompt kapalıdır; çalışan
turu Ctrl-C keser.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from ...engines.agent.approval import ApprovalMode
from ...ui import messages, theme

#: Yapıştırılan metin bu satırdan uzunsa katlanarak tek satırda özetlenir.
FOLD_PASTE_LINES = 10


class ReplInput:
    """Komut geçmişi, tamamlama ve shift-tab ile mod döngüsü sunan giriş."""

    def __init__(self, history_path: Path, words: list[str], *, mode: ApprovalMode) -> None:
        self.mode = mode
        self._session: Any = None
        self._fold_paste = True
        if sys.stdin.isatty():
            self._session = _build_session(self, history_path, words)

    @property
    def interactive(self) -> bool:
        return self._session is not None

    def cycle_mode(self) -> ApprovalMode:
        modes = tuple(ApprovalMode)
        self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
        return self.mode

    def toggle_fold(self) -> None:
        self._fold_paste = not self._fold_paste

    @property
    def fold_paste(self) -> bool:
        return self._fold_paste

    async def prompt(self) -> str:
        if self._session is None:
            # Düz `input()` bloklar; ayrı bir thread'e alınmazsa arka plandaki
            # öğrenme işleri kullanıcı yazarken ilerleyemez.
            return await asyncio.to_thread(input, "fusion ❯ ")
        from prompt_toolkit.formatted_text import HTML

        line = await self._session.prompt_async(HTML("<b><ansimagenta>fusion</ansimagenta></b> ❯ "))
        return str(line)

    def toolbar(self) -> Any:
        from prompt_toolkit.formatted_text import HTML

        return HTML(
            f" onay: <b>{self.mode.value}</b>  "
            f"<style fg='{theme.DIM}'>{messages.REPL_ON_OFF_HINT}</style>"
        )


def _build_session(owner: ReplInput, history_path: Path, words: list[str]) -> Any:
    """prompt_toolkit oturumunu kur. Kurulamazsa None → düz girişe düşülür."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.key_binding import KeyBindings

        history_path.parent.mkdir(parents=True, exist_ok=True)
        bindings = KeyBindings()

        @bindings.add("s-tab")
        def _cycle(event: Any) -> None:
            owner.cycle_mode()
            event.app.invalidate()

        @bindings.add("c-v")
        def _fold(event: Any) -> None:
            owner.toggle_fold()
            event.app.invalidate()

        return PromptSession(
            history=FileHistory(str(history_path)),
            completer=WordCompleter(words, sentence=True),
            complete_while_typing=True,
            key_bindings=bindings,
            bottom_toolbar=owner.toolbar,
            input_processors=[_paste_fold_processor(owner)],
        )
    except Exception:
        # prompt_toolkit kurulamadı (terminal desteklemiyor, ortam kısıtlı…).
        # Düz girişe düşmek kabul edilebilir; REPL çalışmaya devam etmelidir.
        return None


def _paste_fold_processor(owner: ReplInput) -> Any:
    """Uzun yapıştırmaları tek satırlık özete katlayan işleyici.

    Sınıf çalışma anında kurulur: `prompt_toolkit.Processor` taban sınıfı ancak
    kütüphane yüklendiğinde erişilebilirdir ve bu modül TTY olmayan ortamlarda
    kütüphaneyi hiç yüklememelidir.
    """
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.layout.processors import Processor, Transformation

    class PasteFold(Processor):
        def apply_transformation(self, transformation_input: Any) -> Any:
            lines = transformation_input.document.lines
            if not owner.fold_paste or len(lines) <= FOLD_PASTE_LINES:
                return Transformation(transformation_input.fragments)
            if transformation_input.lineno == 0:
                summary = messages.REPL_PASTE_FOLDED.format(count=len(lines))
                return Transformation(FormattedText([("class:dim italic", summary)]))
            return Transformation(FormattedText([]))

    return PasteFold()
