"""Eklenti `bin/` klasörü Bash aracının PATH'ine (Claude Code plugins-reference, #389).

Claude: "bin/: Executables added to the Bash tool's PATH while the plugin is enabled" — etkin
eklentinin kökündeki `bin/` klasörü kabuk komutlarının PATH'ine eklenir. Fusion'da yalnız ajanın
`run_shell` aracına (ön plan ve arka plan) uygulanır; kanca ve MCP süreçleri etkilenmez.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from ..core.plugins import PluginError

_LOG = logging.getLogger(__name__)


def plugin_bin_dirs(root: Path | None = None) -> tuple[Path, ...]:
    """Etkin eklentilerin var olan `bin/` klasörleri (yükleme sırasıyla)."""
    from .plugin_store import active_plugins

    try:
        active = active_plugins(root=root)
    except (OSError, PluginError) as error:
        _LOG.warning("eklenti bin/ klasörleri okunamadı: %s", error)
        return ()
    found: list[Path] = []
    for item in active:
        if item.layout is None:
            continue
        folder = item.layout.root / "bin"
        if folder.is_dir() and folder not in found:
            found.append(folder)
    return tuple(found)


def with_plugin_bin(env: Mapping[str, str], root: Path | None = None) -> dict[str, str]:
    """`PATH`'in sonuna etkin eklentilerin `bin/` klasörlerini ekle (yeni sözlük)."""
    extra = [str(path) for path in plugin_bin_dirs(root)]
    if not extra:
        return dict(env)
    current = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    merged = [*current, *(p for p in extra if p not in current)]
    return {**env, "PATH": os.pathsep.join(merged)}
