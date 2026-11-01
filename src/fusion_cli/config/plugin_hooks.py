"""Etkin eklentilerin kancalarını kanca kümesine katma (#375).

Claude Code (https://code.claude.com/docs/en/plugins/components.md "Hooks"): eklenti
açıkken `hooks/hooks.json` ve `plugin.json` `hooks` girdileri kaydedilir ve olaylarında
tetiklenir; süreçlere `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_PROJECT_DIR` ve
`CLAUDE_PLUGIN_OPTION_<KEY>` verilir. `CLAUDE_PROJECT_DIR` bütün kancaların ortak ortamından
(`hook_environment`) gelir; kök ve veri klasörü burada komut başına eklenir.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..core.hooks.events import HookCommand, HookSkip
from .plugin_data import plugin_data_dir
from .plugin_store import plugin_hook_blocks, plugins_dir

PLUGIN_SOURCE_PREFIX = "eklenti:"


def plugin_hooks(
    *, default_timeout_s: float, base: Path | None = None
) -> tuple[tuple[HookCommand, ...], tuple[HookSkip, ...]]:
    """Etkin (ve çalıştırma onaylı) eklentilerin kanca komutları ve atlananlar."""
    from .hooks import parse_hooks_block

    commands: list[HookCommand] = []
    skipped: list[HookSkip] = []
    for source, path, block in plugin_hook_blocks(base):
        name = source.removeprefix(PLUGIN_SOURCE_PREFIX)
        env = (
            ("CLAUDE_PLUGIN_ROOT", str((base or plugins_dir()) / name)),
            ("CLAUDE_PLUGIN_DATA", str(plugin_data_dir(name, create=True))),
        )
        found, skips = parse_hooks_block(
            block.get("hooks", {}), source=source, path=path, default_timeout_s=default_timeout_s
        )
        commands.extend(replace(command, env=env) for command in found)
        skipped.extend(skips)
    return tuple(commands), tuple(skipped)
