"""Eklenti kancaları (`hooks/hooks.json`, `plugin.json` `hooks`) — Claude Code eklenti katmanı.

Yalnız etkin ve çalıştırma onaylı eklentilerin kancaları okunur (`plugin_hook_blocks`).
`${CLAUDE_PLUGIN_ROOT}` tanımda zaten çözülür; kanca sürecine ayrıca
`CLAUDE_PLUGIN_ROOT` ve kalıcı veri klasörü `CLAUDE_PLUGIN_DATA` verilir (Claude:
eklenti güncellemelerinde korunan klasör, ilk kullanımda oluşturulur).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from ..core.hooks.events import HookCommand, HookSkip
from .hook_parse import parse_hooks_block

_LOG = logging.getLogger(__name__)
#: Eklenti kaynak adının öneki (`eklenti:<ad>`).
PLUGIN_SOURCE_PREFIX = "eklenti:"
#: Kalıcı eklenti verisinin klasörü (eklenti kökünün kardeşi).
PLUGIN_DATA_DIRNAME = "eklenti-verisi"


def plugin_data_dir(name: str, base: Path | None = None) -> Path:
    """Eklentinin güncellemelerde korunan veri klasörü (`CLAUDE_PLUGIN_DATA`)."""
    from .plugin_store import plugins_dir

    return (base or plugins_dir()).parent / PLUGIN_DATA_DIRNAME / name


def plugin_hooks(
    default_timeout_s: float, base: Path | None = None
) -> tuple[tuple[HookCommand, ...], tuple[HookSkip, ...]]:
    """Etkin eklentilerin kancaları; kaynak `eklenti:<ad>`, kök ve veri yolu komutta."""
    from .plugin_store import plugin_hook_blocks, plugins_dir

    commands: list[HookCommand] = []
    skipped: list[HookSkip] = []
    try:
        blocks = plugin_hook_blocks(base)
    except OSError as error:
        _LOG.warning("eklenti kancaları okunamadı: %s", error)
        return (), ()
    root_dir = base or plugins_dir()
    for source, path, block in blocks:
        name = source.removeprefix(PLUGIN_SOURCE_PREFIX)
        found, rejected = parse_hooks_block(
            block.get("hooks", {}), source=source, path=path, default_timeout_s=default_timeout_s
        )
        root = str(root_dir / name)
        data = str(plugin_data_dir(name, base))
        commands.extend(replace(c, plugin_root=root, plugin_data=data) for c in found)
        skipped.extend(rejected)
    return tuple(commands), tuple(skipped)


def plugin_environment(command: HookCommand) -> dict[str, str]:
    """Eklenti kancasının sürecine eklenen değişkenler (veri klasörü oluşturulur)."""
    if not command.plugin_root:
        return {}
    extra = {"CLAUDE_PLUGIN_ROOT": command.plugin_root, "FUSION_PLUGIN_ROOT": command.plugin_root}
    if command.plugin_data:
        try:
            Path(command.plugin_data).mkdir(parents=True, exist_ok=True)
        except OSError as error:
            _LOG.warning("eklenti veri klasörü oluşturulamadı: %s", error)
        extra["CLAUDE_PLUGIN_DATA"] = command.plugin_data
    return extra
