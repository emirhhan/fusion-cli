"""Kurulu eklentiyi ve pazar yerini güncelleme (P-059) — Claude Code `plugin update` /
`marketplace update` karşılığı: `fusion eklenti guncelle <ad>`,
`fusion eklenti pazar guncelle <ad>`.

Claude gibi (#393): `ad@pazar` kaydında önce git pazarı yenilenir (son 30 sn'de yenilendiyse
ya da yerel pazarsa atlanır; yenileme başarısızsa önbellekteki katalogla sürer), sonra eklenti
çekilir ve sürüm Claude sırasıyla hesaplanır. Sürüm kayıttakiyle aynıysa hiçbir şey yazılmaz
("already at the latest version"). Doğrulama, ad eşleşmesi ve önizleme karması
(`expected_digest`) kurulumla aynıdır. Eski kopya `.orphaned_at` ile 14 gün kalır (#408);
kayıt yazılamazsa geri konur. Açık/kapalı durumu korunur.

Pazar güncellemesi git pazarını yeniden klonlar (yerel pazar zaten diskten okunur); pazarın
adı değişmişse güncellenmez — `ad@pazar` kurulumları başka bir pazara kaymasın.
"""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from ..config import plugin_store
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
    _clone,  # noqa: F401  (testler bu adı yamar)
    _fetch,
    _resolve,
    _workspace,
    accepted_command_of,
    read_marketplace,
    version_of,
)
from .plugin_market_source import split_ref
from .plugin_source_fetch import CommandConsent, ShownCommand
from .plugin_version import orphan, sweep_orphans

_LOG = logging.getLogger(__name__)
#: Claude: son 30 saniyede yenilenen pazar kurulum/güncelleme öncesi yeniden yenilenmez.
REFRESH_GRACE_S = 30.0

ERR_MARKET_RENAMED = "Pazarın adı değişti ({old} → {new}); güncellenmedi. Kaldırıp yeniden ekle."


@dataclass(frozen=True, slots=True)
class UpdateResult:
    record: PluginRecord
    #: İçerik değişti mi? `False` = zaten güncel, hiçbir şey yazılmadı.
    changed: bool


def update_source(record: PluginRecord) -> str:
    """Kaydın yeniden çekileceği kaynak metni: pazar girdisinin adı (bildirim adı değil, #391)."""
    if record.marketplace and record.source.endswith(f"@{record.marketplace}"):
        return record.source
    return f"{record.name}@{record.marketplace}" if record.marketplace else record.source


def update_plugin(
    name: str,
    *,
    approve: ApprovalCallback,
    base: Path | None = None,
    expected_digest: str = "",
    accept_command: CommandConsent | None = None,
) -> UpdateResult:
    """`accept_command`: değişen pazar komutu için onay; değişmeyen komut yeniden sorulmaz."""
    root = base or plugins_dir()
    sweep_orphans(root)
    state = load_state(root)
    record = state.plugin(name)
    if record is None:
        raise PluginError(ERR_NOT_INSTALLED.format(name=name))
    if record.folder:
        return _refresh_in_place(record, root)
    if refresh_marketplace_for(update_source(record), state.marketplaces, base=root):
        state = load_state(root)
    resolved = _resolve(update_source(record), state)
    with _workspace(root) as workspace:
        folder, commit = _fetch(resolved, workspace, _update_consent(record, accept_command))
        report = validate_plugin(folder, record.name)
        if not report.ok or report.layout is None:
            raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
        if report.layout.name != record.name:
            raise PluginError(ERR_RENAMED.format(old=record.name, new=report.layout.name))
        digest = tree_digest(folder)
        _check_expected(expected_digest, digest)
        version = version_of(resolved, report.layout.manifest.version, commit)
        if version == record.version:
            return UpdateResult(record, changed=False)
        preview = PluginPreview(report, update_source(record), context_cost(report.layout))
        preview = replace(preview, digest=digest, commit=commit)
        if not approve(preview):
            raise PluginError(ERR_DECLINED)
        updated = replace(
            record,
            version=version,
            commit=commit,
            digest=digest,
            exec_approved=report.layout.is_executable,
            installed_at=time.time(),
            accepted_command=accepted_command_of(resolved),
        )
        _swap(root / record.store_key, folder, updated, root)
    return UpdateResult(updated, changed=True)


def _update_consent(record: PluginRecord, given: CommandConsent | None) -> CommandConsent:
    """Kayıttaki onay özeti aynıysa kendiliğinden kabul; değişmişse `given` karar verir (#399).

    Özet adres/kip ve katalog sürümünü de kapsar (`ShownCommand.sha256`). Eski sürümün metin
    kaydı hiçbir özetle eşleşmez: bir kez yeniden sorulur, arka plan yolu reddeder.
    """

    def consent(shown: ShownCommand) -> bool:
        if record.accepted_command and shown.sha256 == record.accepted_command:
            return True
        return given is not None and given(shown)

    return consent


def _refresh_in_place(record: PluginRecord, root: Path) -> UpdateResult:
    """Yerinde yüklenen eklenti kaynağından okunur (#403): sürüm ve girdi alanları (#398)
    kaydı tazelenir."""
    from ..config.plugin_scan import entry_overlay, scan_plugin

    report = validate_plugin(Path(record.folder), record.name)
    if not report.ok or report.layout is None:
        raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
    try:
        resolved = _resolve(update_source(record), load_state(root))
        fields, strict = resolved.entry_fields, resolved.strict
    except PluginError:  # pazar/girdi artık yok: kayıttaki alanlarla sürer
        fields, strict = record.entry_fields, record.entry_strict
    overlay = entry_overlay(fields, strict)
    layout = scan_plugin(Path(record.folder), record.name, overlay) if overlay else report.layout
    version = layout.manifest.version or record.version
    updated = replace(record, version=version, entry_fields=fields, entry_strict=strict)
    if updated == record:
        return UpdateResult(record, changed=False)
    plugin_store.update_state(lambda current: current.with_plugin(updated), root)
    return UpdateResult(updated, changed=True)


def refresh_marketplace_for(
    source: str, marketplaces: Iterable[MarketplaceRecord], *, base: Path | None = None
) -> bool:
    """`ad@pazar` için git pazarını yenile (Claude, #393); yenilendiyse True.

    Yerel pazar, son 30 sn'de yenilenen pazar ve `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`
    atlanır. Yenileme başarısızsa önbellekteki katalogla sürer ("marketplace not refreshed").
    """
    import os

    name, sep, market = source.partition("@")
    if not sep or not name or "/" in market or os.environ.get(_NO_TRAFFIC_ENV):
        return False
    record = next((m for m in marketplaces if m.name == market), None)
    if record is None or record.kind != "git":
        return False
    if time.time() - record.added_at < REFRESH_GRACE_S:
        return False
    try:
        update_marketplace(market, base=base)
    except PluginError as error:
        _LOG.warning("marketplace not refreshed (%s): %s", market, error)
        return False
    return True


_NO_TRAFFIC_ENV = "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"


def _swap(destination: Path, folder: Path, record: PluginRecord, root: Path) -> None:
    """Eski kopyayı `.orphaned_at` ile ayır, yenisini koy; kayıt yazılamazsa eskisini geri getir."""
    previous = orphan(destination, root) if destination.is_dir() else None
    shutil.move(str(folder), destination)
    try:
        plugin_store.update_state(lambda current: current.with_plugin(record), root)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        if previous is not None:
            (previous / ".orphaned_at").unlink(missing_ok=True)
            shutil.move(str(previous), destination)
        raise


def update_all_marketplaces(*, base: Path | None = None) -> tuple[MarketplaceRecord, ...]:
    """`marketplace update` adsız: bütün kayıtlı pazarları sırayla yenile (#410)."""
    names = [record.name for record in load_state(base or plugins_dir()).marketplaces]
    return tuple(update_marketplace(name, base=base) for name in names)


def update_marketplace(name: str, *, base: Path | None = None) -> MarketplaceRecord:
    root = base or plugins_dir()
    record = load_state(root).marketplace(name)
    if record is None:
        raise PluginError(ERR_NO_MARKET.format(name=name))
    if record.kind not in ("git", "url"):
        market = read_marketplace(Path(record.path))
        if market.name != record.name:
            raise PluginError(ERR_MARKET_RENAMED.format(old=record.name, new=market.name))
        return record
    from .plugin_install import fetch_market

    url, ref = split_ref(record.source)
    destination = fetch_market(record.kind, url, ref, record.sparse, root, expected=record.name)
    updated = replace(record, path=str(destination), added_at=time.time())
    plugin_store.update_state(lambda current: current.with_marketplace(updated), root)
    return updated
