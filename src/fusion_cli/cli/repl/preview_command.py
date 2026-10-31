"""`/onizleme [ad]`: launch.json sunucularını listele ya da birini ajana başlattır.

Komut işleyicileri senkrondur (bkz. `commands.Handler`); sunucu başlatma ise ağ ve alt
süreç bekler. Bu yüzden `/onizleme <ad>` sunucuyu kendisi açmaz: isteği bekleyen görev
olarak kuyruğa koyar, ajan `start_preview name=<ad>` ile (onay kapısından geçerek) açar
ve adresi söyler. Listeleme ise yalnız dosya okuduğu için anında yapılır.
"""

from __future__ import annotations

from ...tools import preview_launch, preview_server
from ...tools.preview_launch import LaunchConfigError
from ...ui import messages
from .state import ReplState


def preview_command(state: ReplState, argument: str) -> str:
    name = argument.strip()
    if not name:
        return _listing(state)
    try:
        loaded = preview_launch.load_launch_configs(state.root)
    except LaunchConfigError as error:
        return str(error)
    if loaded.get(name) is None:
        if not loaded.configs:
            return messages.REPL_PREVIEW_NONE.format(file=preview_launch.LAUNCH_FILE)
        names = ", ".join(config.name for config in loaded.configs)
        return messages.REPL_PREVIEW_UNKNOWN.format(name=name, names=names)
    state.pending_task = messages.REPL_PREVIEW_TASK.format(name=name)
    return messages.REPL_PREVIEW_QUEUED.format(name=name)


def _listing(state: ReplState) -> str:
    try:
        loaded = preview_launch.load_launch_configs(state.root)
    except LaunchConfigError as error:
        return str(error)
    root = state.root.resolve()
    detected = [preview for preview in preview_server.all_running() if preview.root == root]
    if not loaded.configs and not detected:
        return messages.REPL_PREVIEW_NONE.format(file=preview_launch.LAUNCH_FILE)
    lines = [messages.REPL_PREVIEW_HEAD.format(source=loaded.source or preview_launch.LAUNCH_FILE)]
    for config in loaded.configs:
        running = preview_launch.running_launch(root, config.name)
        lines.append(
            messages.REPL_PREVIEW_ROW.format(
                name=config.name,
                command=config.command_text or messages.REPL_PREVIEW_ATTACH,
                url=running.url if running is not None else config.address,
                state=(
                    messages.REPL_PREVIEW_RUNNING
                    if running is not None
                    else messages.REPL_PREVIEW_STOPPED
                ),
            )
        )
    lines.extend(
        messages.REPL_PREVIEW_DETECTED.format(kind=preview.kind.value, url=preview.url)
        for preview in detected
    )
    return "\n".join(lines)
