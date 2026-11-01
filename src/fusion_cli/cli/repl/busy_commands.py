"""Tur sürerken kuyruğa girmeden çalışan komutlar (#209).

Claude Code: yanıt sürerken `/status`, `/tasks`, `/usage`, `/model`, `/effort` ve `/fast`
hemen çalışır; `/add-dir` ve `/permissions` anında açılıp aynı turda etkili olur. Diğer
komutlar ve düz mesajlar kuyruğa girer. Takma adlar (`/cost`, `/stats`) kanonik adla çözülür.
"""

from __future__ import annotations

from .commands import CommandRegistry, is_command_line, parse

#: Belgelenen anlık komutların kanonik adları.
IMMEDIATE_COMMANDS = frozenset(
    {"status", "tasks", "usage", "model", "effort", "fast", "add-dir", "permissions"}
)


def runs_while_busy(registry: CommandRegistry, line: str) -> bool:
    """Satır tur sürerken hemen çalışacak bir komut mu?"""
    if not is_command_line(line):
        return False
    name, _argument = parse(line)
    command = registry.get(name)
    return command is not None and command.name in IMMEDIATE_COMMANDS
