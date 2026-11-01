"""Görünüm komutları (P-070): `/theme`, `/tui`, `/search`.

- `/theme [ad]` — terminal paletini ANINDA uygular ve `runtime.terminal_theme`'e yazar.
  Masaüstü temasından (`runtime.theme`, system/light/dark) ayrıdır.
- `/tui [default|fullscreen]` — `runtime.tui`'ye yazar, konuşmayı koruyarak hemen yeniden açar
  (çalışan tam-ekran uygulamayı yerinde değiştirmek konuşmayı kaybettirirdi).
- `/search <metin>` — tam-ekran konuşmasında son eşleşmeye kaydır (yalnız TUI; `tui_loop`
  uygular, burada yalnız satır-içi yüzeyin cevabı vardır).
"""

from __future__ import annotations

from dataclasses import replace

from ...config.settings_access import write_setting
from ...core.errors import ConfigError
from ...ui import messages, theme
from ...ui.picker import Choice
from .state import ReplState

TUI_MODES = ("fullscreen", "inline")
#: Claude Code adları (`/tui [default|fullscreen]`, #232) → ayar değeri. `inline` eski ad.
TUI_NAMES = {"default": "inline", "fullscreen": "fullscreen", "inline": "inline"}
#: Ayar değeri → kullanıcıya gösterilen Claude adı.
TUI_DISPLAY = {"inline": "default", "fullscreen": "fullscreen"}
#: Tema seçicisinde ad → kısa açıklama.
THEME_DESCRIPTIONS = {
    "koyu": "Fusion'ın özgün paleti (koyu zemin)",
    "acik": "Açık zeminli terminaller için koyu tonlar",
    "ansi": "Terminalin kendi 16 rengi",
    "daltonizm": "Kırmızı-yeşil yerine mavi/turuncu (Okabe-Ito)",
}


def theme_choices(state: ReplState) -> list[Choice]:
    current = theme.CURRENT_THEME
    return [
        Choice(
            name,
            name + (messages.OUTPUT_STYLE_CURRENT if name == current else ""),
            THEME_DESCRIPTIONS.get(name, ""),
        )
        for name in theme.THEME_NAMES
    ]


def apply_theme_setting(state: ReplState) -> None:
    """Oturum başında `runtime.terminal_theme`'i uygula; tanınmayan ad koyuda kalır."""
    name = str(getattr(state.config.runtime, "terminal_theme", theme.DEFAULT_THEME) or "")
    try:
        theme.apply_palette(name)
    except ValueError:
        theme.apply_palette(theme.DEFAULT_THEME)


def _persist(state: ReplState, path: str, value: str) -> str:
    """Ayarı yaz; yazılamazsa oturumda uygula ve nedenini döndür (boş = başarılı)."""
    try:
        state.config, _ = write_setting(state.config, path, value)
    except ConfigError as error:
        section, _, key = path.partition(".")
        state.config = replace(
            state.config, runtime=replace(getattr(state.config, section), **{key: value})
        )
        return str(error)
    return ""


def theme_command(state: ReplState, argument: str) -> str:
    wanted = argument.strip().lower()
    if not wanted:
        rows = [messages.THEME_HEADER.format(current=theme.CURRENT_THEME)]
        rows.extend(f"  {choice.label:<14} {choice.description}" for choice in theme_choices(state))
        rows.append(messages.THEME_HINT)
        return "\n".join(rows)
    try:
        theme.apply_palette(wanted)
    except ValueError as error:
        return str(error)
    error_text = _persist(state, "runtime.terminal_theme", wanted)
    if error_text:
        return messages.THEME_SET_UNSAVED.format(name=wanted, error=error_text)
    return messages.THEME_SET.format(name=wanted)


def tui_command(state: ReplState, argument: str) -> str:
    """`/tui [default|fullscreen]` — Claude Code adları; `inline`, `default`'un eski adıdır."""
    wanted = argument.strip().lower()
    current = getattr(state.config.runtime, "tui", "fullscreen")
    options = tuple(TUI_DISPLAY.values())
    if not wanted:
        shown = TUI_DISPLAY.get(current, current)
        return messages.TUI_MODE_CURRENT.format(mode=shown, options=" · ".join(options))
    value = TUI_NAMES.get(wanted)
    if value is None:
        return messages.TUI_MODE_UNKNOWN.format(name=wanted, options=", ".join(options))
    shown = TUI_DISPLAY[value]
    error_text = _persist(state, "runtime.tui", value)
    if error_text:
        return messages.TUI_MODE_SET_UNSAVED.format(mode=shown, error=error_text)
    active = getattr(state, "surface", "")
    if not active:
        return messages.TUI_MODE_SET.format(mode=shown)
    if active == value:
        return messages.TUI_MODE_ALREADY.format(mode=shown)
    # Claude Code (#232): oluşturucu konuşma korunarak hemen yeniden açılır.
    state.surface_switch = value
    state.running = False
    return messages.TUI_MODE_SWITCHING.format(mode=shown)


def search_command(state: ReplState, argument: str) -> str:
    """Satır-içi yüzeyde arama yok (terminal scrollback'i var); TUI kendi dalını çalıştırır."""
    if not argument.strip():
        return messages.SEARCH_USAGE
    return messages.SEARCH_ONLY_TUI
