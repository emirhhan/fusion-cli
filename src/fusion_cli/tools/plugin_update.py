"""Kurulu eklentiyi ve pazar yerini güncelleme (P-059) — Claude Code `plugin update` /
`marketplace update` karşılığı: `fusion eklenti guncelle <ad>`,
`fusion eklenti pazar guncelle <ad>`.

Eklenti kaydedildiği kaynaktan (yerel klasör, git adresi ya da `ad@pazar`) yeniden çekilir ve
kurulumla AYNI kapılardan geçer: doğrulama, ad eşleşmesi, önizleme karması (`expected_digest`),
kanca/MCP için açık onay. İçerik aynıysa hiçbir şey yazılmaz. Eski kopya Fusion çöpüne gider
(`fusion cop geri-al`); kayıt yazılamazsa geri konur. Açık/kapalı durumu korunur.

Pazar güncellemesi git pazarını yeniden klonlar (yerel pazar zaten diskten okunur); pazarın
adı değişmişse güncellenmez — `ad@pazar` kurulumları başka bir pazara kaymasın.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, replace
from pathlib import Path

from ..config import plugin_store
from ..config.paths import trash_dir
from ..config.plugin_layout import context_cost, tree_digest, validate_plugin
from ..config.plugin_store import MarketplaceRecord, PluginRecord, load_state, plugins_dir
from ..core.plugins import PluginError
from .plugin_install import (
    ERR_DECLINED,
    ERR_INVALID,
    ERR_NO_MARKET,
    ERR_NOT_INSTALLED,
    ERR_RENAMED,
    ApprovalCallback,
    PluginPreview,
    _check_expected,
    _clone,
    _fetch,
    _resolve,
    _workspace,
    markets_dir,
    read_marketplace,
)
from .safe_delete import DeleteRefusedError, move_to_trash

ERR_MARKET_RENAMED = "Pazarın adı değişti ({old} → {new}); güncellenmedi. Kaldırıp yeniden ekle."


@dataclass(frozen=True, slots=True)
class UpdateResult:
    record: PluginRecord
    #: İçerik değişti mi? `False` = zaten güncel, hiçbir şey yazılmadı.
    changed: bool


def update_source(record: PluginRecord) -> str:
    """Kaydın yeniden çekileceği kaynak metni."""
    return f"{record.name}@{record.marketplace}" if record.marketplace else record.source


def update_plugin(
    name: str,
    *,
    approve: ApprovalCallback,
    base: Path | None = None,
    expected_digest: str = "",
) -> UpdateResult:
    root = base or plugins_dir()
    state = load_state(root)
    record = state.plugin(name)
    if record is None:
        raise PluginError(ERR_NOT_INSTALLED.format(name=name))
    resolved = _resolve(update_source(record), state)
    with _workspace(root) as workspace:
        folder, commit = _fetch(resolved, workspace)
        report = validate_plugin(folder)
        if not report.ok or report.layout is None:
            raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
        if report.layout.name != record.name:
            raise PluginError(ERR_RENAMED.format(old=record.name, new=report.layout.name))
        digest = tree_digest(folder)
        _check_expected(expected_digest, digest)
        if digest == record.digest:
            return UpdateResult(record, changed=False)
        preview = PluginPreview(report, update_source(record), context_cost(report.layout))
        preview = replace(preview, digest=digest, commit=commit)
        if not approve(preview):
            raise PluginError(ERR_DECLINED)
        updated = replace(
            record,
            version=report.layout.manifest.version,
            commit=commit,
            digest=digest,
            exec_approved=report.layout.is_executable,
            installed_at=time.time(),
        )
        _swap(root / name, folder, updated, root)
    return UpdateResult(updated, changed=True)


def _swap(destination: Path, folder: Path, record: PluginRecord, root: Path) -> None:
    """Eski kopyayı çöpe, yenisini yerine koy; kayıt yazılamazsa eskisini geri getir."""
    try:
        moved, _missing = move_to_trash(
            (str(destination),), cwd=root, root=root, home=Path.home(), trash_root=trash_dir()
        )
    except DeleteRefusedError as error:
        raise PluginError(str(error)) from error
    shutil.move(str(folder), destination)
    try:
        plugin_store.update_state(lambda current: current.with_plugin(record), root)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        for entry in moved:
            shutil.move(str(entry.stored), destination)
        raise


def update_marketplace(name: str, *, base: Path | None = None) -> MarketplaceRecord:
    root = base or plugins_dir()
    record = load_state(root).marketplace(name)
    if record is None:
        raise PluginError(ERR_NO_MARKET.format(name=name))
    if record.kind != "git":
        market = read_marketplace(Path(record.path))
        if market.name != record.name:
            raise PluginError(ERR_MARKET_RENAMED.format(old=record.name, new=market.name))
        return record
    with _workspace(root) as workspace:
        clone = workspace / "pazar"
        _clone(record.source, clone)
        market = read_marketplace(clone)
        if market.name != record.name:
            raise PluginError(ERR_MARKET_RENAMED.format(old=record.name, new=market.name))
        destination = markets_dir(root) / market.name
        shutil.rmtree(destination, ignore_errors=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(clone), destination)
    updated = replace(record, path=str(destination), added_at=time.time())
    plugin_store.update_state(lambda current: current.with_marketplace(updated), root)
    return updated
