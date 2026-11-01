"""Yerel pazarın göreli eklentileri yerinde yüklenir, kopyalanmaz (Claude Code, #403).

Claude: yerel yoldan eklenmiş pazardaki göreli yollu eklenti kaynak klasöründen okunur;
kaynaktaki düzenlemeler sürüm artırmadan sonraki oturumda ya da /reload-plugins'te geçerli olur,
`CLAUDE_PLUGIN_ROOT` kaynak klasörü gösterir. Karma kilidi bu eklentilere uygulanmaz (güvenlik
davranışı değişti); kanca/MCP içeren eklenti kurulumda yine önizlenir ve onay ister.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import plugin_store
from ..config.plugin_layout import context_cost, tree_digest, validate_plugin
from ..config.plugin_scan import entry_overlay, scan_plugin
from ..config.plugin_store import InstalledPlugin, PluginRecord, PluginState, inspect_plugin
from ..core.plugins import PluginError
from .plugin_version import resolve_version

if TYPE_CHECKING:
    from .plugin_install import ApprovalCallback, _Resolved


def install_in_place(
    resolved: _Resolved,
    spec: str,
    state: PluginState,
    root: Path,
    approve: ApprovalCallback,
    expected_digest: str,
) -> InstalledPlugin:
    """Kaynağı doğrula, önizle ve onaylat; kopyalamadan kaydet."""
    from .plugin_install import (
        ERR_DECLINED,
        ERR_EXISTS,
        ERR_INVALID,
        PluginAlreadyInstalledError,
        PluginPreview,
    )
    from .plugin_install_extra import check_local_size

    folder = Path(resolved.location)
    check_local_size(folder)
    report = validate_plugin(folder, resolved.fallback_name)
    if not report.ok or report.layout is None:
        raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
    overlay = entry_overlay(resolved.entry_fields, resolved.strict)
    # #398: girdi alanları kaynağa yazılmadan bellekte birleştirilir (çakışma burada hata verir).
    layout = scan_plugin(folder, resolved.fallback_name, overlay) if overlay else report.layout
    name = layout.name
    key = plugin_store.same_name_key(state, name, resolved.marketplace)  # #391
    if key is None:
        raise PluginAlreadyInstalledError(ERR_EXISTS.format(name=name))
    if expected_digest:
        from .plugin_install import _check_expected

        _check_expected(expected_digest, tree_digest(folder))
    preview = PluginPreview(report, spec, context_cost(report.layout), "", "")
    if not approve(preview):
        raise PluginError(ERR_DECLINED)
    record = PluginRecord(
        key=key if key != name else "",
        name=name,
        version=resolve_version(layout.manifest.version, resolved.entry_version, ""),
        source=f"{resolved.entry or name}@{resolved.marketplace}",
        kind="pazar",
        marketplace=resolved.marketplace,
        enabled=layout.manifest.default_enabled,
        exec_approved=layout.is_executable,
        installed_at=time.time(),
        folder=str(folder),
        entry_fields=resolved.entry_fields if overlay else "",
        entry_strict=resolved.strict,
    )
    plugin_store.update_state(lambda current: current.with_plugin(record), root)
    return inspect_plugin(record, root)
