"""`/keybindings` ve `/vim` (P-067)."""

from __future__ import annotations

from dataclasses import replace

from ...config import keybindings
from ...config.settings_access import write_setting
from ...core.errors import ConfigError
from ...ui import messages
from .state import ReplState

#: Kalıcı ayar yolu.
VIM_SETTING_PATH = "runtime.vim_mode"


def keybindings_command(state: ReplState, argument: str) -> str:
    """Dosya yolunu (yoksa örnek dosyayı yazarak), etkin tabloyu ve uyarıları göster."""
    path = keybindings.write_default_file()
    keymap = keybindings.load_keymap(path)
    lines = [messages.KEYBINDINGS_HEADER.format(path=path), *keybindings.describe(keymap)]
    lines.append(messages.KEYBINDINGS_HINT)
    return "\n".join(lines)


def vim_command(state: ReplState, argument: str) -> str:
    """`/vim` kullanımdan kalkmış takma ad (#217): Claude Code'da `/config editorMode=vim`.

    Bir sürüm boyunca çalışır ve oturumda bir kez uyarır.
    """
    result = _toggle_vim(state, argument)
    if getattr(state, "vim_command_warned", False):
        return result
    state.vim_command_warned = True
    return f"{messages.VIM_DEPRECATED}\n{result}"


def _toggle_vim(state: ReplState, argument: str) -> str:
    """Vim kipini aç/kapa (argümansız: tersle; `on|off` ile açık seç); kalıcı yazılır."""
    wanted = argument.strip().lower()
    current = bool(getattr(state.config.runtime, "vim_mode", False))
    if wanted in ("on", "ac", "aç", "1", "true"):
        enabled = True
    elif wanted in ("off", "kapat", "0", "false"):
        enabled = False
    elif not wanted:
        enabled = not current
    else:
        return messages.VIM_USAGE
    try:
        state.config, _ = write_setting(
            state.config, VIM_SETTING_PATH, "true" if enabled else "false"
        )
    except ConfigError as error:
        state.config = replace(
            state.config, runtime=replace(state.config.runtime, vim_mode=enabled)
        )
        return messages.VIM_SET_UNSAVED.format(state=_label(enabled), error=error)
    return messages.VIM_SET.format(state=_label(enabled))


def _label(enabled: bool) -> str:
    return messages.REPL_ON if enabled else messages.REPL_OFF
