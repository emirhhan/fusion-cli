"""Eklenti kurulumunun kaynak türü yardımcıları: archive/npm/command, sürüm, onay özeti.

`plugin_install`'dan ayrıldı (800 satır sınırı); adlar oradan da içe aktarılır.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import plugin_layout
from ..config.plugin_layout import tree_digest
from ..core.constants import GIT_TIMEOUT_S
from ..core.plugin_marketplace import MarketplaceSource
from ..core.plugins import PluginError
from . import capability_install
from .plugin_source_fetch import CommandConsent
from .plugin_version import resolve_version

if TYPE_CHECKING:
    from .plugin_install import _Resolved


def check_local_size(folder: Path) -> None:
    """Kopyalamadan ÖNCE dosya/boyut sınırı (ölçüldü 31 Ekim: `kur ~` GB'larca kopyalıyordu)."""
    files = size = 0
    for current, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            files += 1
            try:
                size += (Path(current) / name).lstat().st_size
            except OSError:
                continue
            if files > plugin_layout.MAX_PLUGIN_FILES or size > plugin_layout.MAX_PLUGIN_BYTES:
                raise PluginError(
                    plugin_layout.ERR_TOO_BIG.format(
                        files=plugin_layout.MAX_PLUGIN_FILES,
                        mb=plugin_layout.MAX_PLUGIN_BYTES // 2**20,
                    )
                )


def fetch_extra(
    resolved: _Resolved,
    source: MarketplaceSource,
    workspace: Path,
    consent: CommandConsent | None,
) -> tuple[Path, str]:
    """archive (sürüm: sha256), npm (sürüm: unknown), command copy (sürüm: içerik karması)."""
    from . import plugin_source_fetch as extra

    target = workspace / "eklenti"
    if resolved.kind == "archive":
        root, digest = extra.fetch_archive(
            source,
            workspace,
            plugin_id=resolved.plugin_id,
            revision=resolved.revision,
            consent=consent,
        )
        shutil.move(str(root), target)
        return target, digest
    if resolved.kind == "npm":
        shutil.move(str(extra.fetch_npm(source, workspace)), target)
        return target, ""
    printed = extra.run_command_source(
        source, plugin_id=resolved.plugin_id, revision=resolved.revision, consent=consent
    )
    check_local_size(printed)
    shutil.copytree(printed, target, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    return target, tree_digest(target)


def version_of(resolved: _Resolved, manifest_version: str, commit: str) -> str:
    """Claude sürüm sırası (#393); göreli eklentide git pazarının commit'i kullanılır."""
    if not commit and resolved.commit_dir:
        commit = directory_commit(Path(resolved.commit_dir))
    return resolve_version(manifest_version, resolved.entry_version, commit, subdir=resolved.subdir)


def directory_commit(folder: Path) -> str:
    try:
        return capability_install._git(["rev-parse", "HEAD"], cwd=folder, timeout=GIT_TIMEOUT_S)
    except capability_install.CapabilityInstallError:
        return ""


def accepted_command_of(resolved: _Resolved) -> str:
    """Onaylanan komutun `ShownCommand.sha256` özeti (#399).

    Özet Claude'un `--accept-command` değeriyle aynıdır: komut/helper metni, kip ya da archive
    adresi ve katalog sürümü. Güncellemede bunlardan biri değişirse yeniden sorulur; yalnız
    metni karşılaştırmak, adresi değişen archive'ın helper belirtecini yeni sunucuya
    gönderiyordu.
    """
    from .plugin_source_fetch import KIND_COMMAND, KIND_HELPER, ShownCommand

    source = resolved.source
    if source is None:
        return ""
    if source.kind == "command":
        mode = source.option("mode", "copy")
        shown = ShownCommand(
            KIND_COMMAND,
            resolved.plugin_id,
            source.location,
            mode,
            catalog_revision=resolved.revision,
        )
        return shown.sha256
    helper = source.option("headersHelper")
    if not helper:
        return ""
    shown = ShownCommand(
        KIND_HELPER,
        resolved.plugin_id,
        helper,
        archive_url=source.location,
        catalog_revision=resolved.revision,
    )
    return shown.sha256


def linked_command(resolved: _Resolved, consent: CommandConsent | None) -> _Resolved:
    """command `mode: link`: basılan klasör kopyalanmadan yerinde yüklenir (Claude)."""
    source = resolved.source
    if resolved.kind != "command" or source is None or source.option("mode") != "link":
        return resolved
    from .plugin_source_fetch import run_command_source

    printed = run_command_source(
        source, plugin_id=resolved.plugin_id, revision=resolved.revision, consent=consent
    )
    return replace(resolved, kind="yerel", location=str(printed), source=None, link=True)
