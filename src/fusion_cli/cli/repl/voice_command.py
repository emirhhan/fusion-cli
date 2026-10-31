"""`/voice` — terminalde tek seferlik yerel dikte (P-072; Claude Code `/voice` karşılığı).

    /voice           dinle; tanınan metin bir sonraki isteme yazılır (düzenle, Enter)
    /voice gonder    dinle ve metni doğrudan tur olarak gönder
    /voice durum     hangi tanıyıcının kullanılacağını göster

Tanıma cihaz üstüdür (`tools/stt.py`); tanıyıcı yoksa açık bir hata verilir. Basılı
tutarak konuş yerine tek dokunuş kipi vardır: bir konuşma bölümü bitince dinleme
kapanır. Bir tuşa bağlamak için `keybindings.json` içinde `"komut:voice"` eylemi kullanılır.
Masaüstünde `/voice` sohbet kutusunun mikrofonunu açar (arayüz yakalar).
"""

from __future__ import annotations

from collections.abc import Callable

from rich.console import Console
from rich.markup import escape

from ...tools.stt import SpeechToTextError, find_listener, listen_once, missing_listener_message
from ...ui import messages, theme
from .state import ReplState

_SEND_WORDS = frozenset({"gonder", "gönder", "send"})
_STATUS_WORDS = frozenset({"durum", "status"})


def desktop_handler(state: ReplState, argument: str) -> str:
    """Eşzamanlı yol (masaüstü/uzak istemci): terminal mikrofonu yerine arayüzü öner."""
    del state, argument
    return messages.VOICE_DESKTOP_HINT


async def run(
    state: ReplState,
    argument: str,
    console: Console,
    on_partial: Callable[[str], None] = lambda _text: None,
) -> None:
    """Dinle ve sonucu bekleyen girişe (ya da `gonder` ile bekleyen göreve) yaz."""
    word = argument.strip().casefold()
    configured = state.config.runtime.voice_listener
    listener = find_listener(configured)
    if word in _STATUS_WORDS:
        _say(console, theme.DIM, _status(listener, state.config.runtime.voice_language))
        return
    if word and word not in _SEND_WORDS:
        _say(console, theme.WARN, messages.VOICE_USAGE)
        return
    if listener is None:
        _say(console, theme.WARN, missing_listener_message(configured))
        return
    _say(console, theme.DIM, messages.VOICE_LISTENING)
    try:
        dictation = await listen_once(
            (str(listener), state.config.runtime.voice_language), on_partial=on_partial
        )
    except SpeechToTextError as error:
        _say(console, theme.WARN, str(error))
        return
    if not dictation.text:
        _say(console, theme.WARN, messages.VOICE_NOTHING_HEARD)
        return
    if word in _SEND_WORDS:
        _say(console, theme.ACCENT, messages.VOICE_HEARD.format(text=dictation.text))
        state.pending_task = dictation.text
        return
    state.pending_input = dictation.text
    _say(console, theme.DIM, messages.VOICE_PREFILLED.format(text=dictation.text))


def _status(listener: object, language: str) -> str:
    if listener is None:
        return messages.VOICE_STATUS_MISSING
    return messages.VOICE_STATUS.format(path=listener, language=language)


def _say(console: Console, color: str, text: str) -> None:
    console.print(f"[{color}]{escape(text)}[/{color}]", highlight=False)
