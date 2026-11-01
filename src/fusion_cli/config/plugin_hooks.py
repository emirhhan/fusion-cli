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

import logging
from collections.abc import Iterator, Mapping

from ..core.hooks.events import HookCommand, HookSkip
from ..core.plugins import PluginError
from .plugin_data import plugin_data_dir
from .plugin_layout import hook_blocks
from .plugin_store import active_plugins, plugin_root_of
from .plugin_user_config import option_env, plugin_values

PLUGIN_SOURCE_PREFIX = "eklenti:"
_LOG = logging.getLogger(__name__)


def _blocks(
    base: Path | None, project: Path | None
) -> Iterator[tuple[str, Path, Mapping[str, object], Path]]:
    """`(kaynak, dosya, blok, eklenti kökü)`; kök kayıt yazılmayan proje eklentisinde de doğru."""
    for item in active_plugins(base, project):
        if item.layout is None:
            continue
        try:
            found = hook_blocks(item.layout)
        except PluginError as error:
            _LOG.warning("eklenti '%s' kancaları yüklenmedi: %s", item.record.name, error)
            continue
        source = f"{PLUGIN_SOURCE_PREFIX}{item.record.name}"
        for path, block in found:
            yield source, path, block, plugin_root_of(path, base) or item.layout.root


def plugin_hooks(
    *, default_timeout_s: float, base: Path | None = None, root: Path | None = None
) -> tuple[tuple[HookCommand, ...], tuple[HookSkip, ...]]:
    """Etkin eklentilerin kanca komutları ve atlananlar.

    `root`: oturumun proje kökü; project/local `enabledPlugins` ve güven ona göre çözülür
    (verilmezse süreç cwd'si). Masaüstü oturumunda süreç cwd'si oturum kökü olmayabilir.
    """
    from .hooks import parse_hooks_block

    commands: list[HookCommand] = []
    skipped: list[HookSkip] = []
    for source, path, block, plugin_root in _blocks(base, root):
        name = source.removeprefix(PLUGIN_SOURCE_PREFIX)
        _schema, values = plugin_values(plugin_root, name)
        env = (
            ("CLAUDE_PLUGIN_ROOT", str(plugin_root)),
            ("CLAUDE_PLUGIN_DATA", str(plugin_data_dir(name, create=True))),
            *option_env(values),  # #388: CLAUDE_PLUGIN_OPTION_<KEY>
        )
        found, skips = parse_hooks_block(
            block.get("hooks", {}), source=source, path=path, default_timeout_s=default_timeout_s
        )
        commands.extend(replace(command, env=env) for command in found)
        skipped.extend(skips)
    return tuple(commands), tuple(skipped)
