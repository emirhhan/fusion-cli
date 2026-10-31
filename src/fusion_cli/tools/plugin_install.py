"""Eklenti kurma, kaldırma, açma/kapatma ve pazar yerleri (P-059).

Kaynaklar (Claude Code `claude plugin install` karşılığı):

- yerel klasör: `fusion eklenti kur ./benim-eklentim`
- git: `fusion eklenti kur https://github.com/sahip/repo` ya da `sahip/repo`
- pazar: `fusion eklenti kur ad@pazar` (ya da tek pazarda bulunan `ad`)

Kurulum adımları: kaynak geçici klasöre alınır (git `--depth 1`, betik ÇALIŞTIRILMAZ) →
`validate_plugin` → kanca/MCP varsa `approve` geri çağrısı açık onay ister → klasör
`<veri>/eklentiler/<ad>`'a taşınır → içerik karması ve commit kaydedilir. Pazar girdisi
`sha` bildiriyorsa klonun commit'i ona eşit olmalıdır. Kaldırma kalıcı değildir (çöp).
"""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from ..config.paths import trash_dir
from ..config.plugin_layout import ValidationReport, context_cost, tree_digest, validate_plugin
from ..config.plugin_store import (
    InstalledPlugin,
    MarketplaceRecord,
    PluginRecord,
    PluginState,
    inspect_plugin,
    load_state,
    plugins_dir,
    save_state,
)
from ..core.constants import GIT_TIMEOUT_S
from ..core.network_address import is_public_ip
from ..core.plugins import (
    MARKETPLACE_PATHS,
    Marketplace,
    MarketplaceEntry,
    PluginError,
    parse_marketplace,
)
from . import capability_install
from .safe_delete import DeleteRefusedError, move_to_trash

#: Resmi Claude Code pazarı için kısa ad (`fusion eklenti pazar ekle resmi`).
OFFICIAL_ALIAS = "resmi"
OFFICIAL_MARKETPLACE = "https://github.com/anthropics/claude-plugins-official"
_TEMP_DIRNAME = ".gecici"
_MARKETS_DIRNAME = ".pazarlar"

ERR_EXISTS = "'{name}' zaten kurulu. Güncellemek için önce kaldır: fusion eklenti kaldir {name}"
ERR_NOT_INSTALLED = "Kurulu değil: {name}"
ERR_INVALID = "Eklenti geçersiz:\n  - {errors}"
ERR_DECLINED = "Kurulum onaylanmadı; hiçbir şey yazılmadı."
ERR_SOURCE = (
    "Kaynak anlaşılamadı: {spec}. Yerel klasör, https://… git adresi, sahip/repo ya da "
    "ad@pazar ver."
)
ERR_URL = "Yalnız genel https adresleri klonlanır: {url}"
ERR_NO_ENTRY = "'{name}' hiçbir kayıtlı pazarda yok. Pazarlar: fusion eklenti pazar liste"
ERR_AMBIGUOUS = "'{name}' birden çok pazarda var: {markets}. ad@pazar biçimini kullan."
ERR_SHA = "Commit uyuşmuyor: pazar {expected} bekliyor, klon {actual}. Kurulmadı."
ERR_NO_MARKET = "Pazar yok: {name}"
ERR_MARKET_FILE = "Pazar bildirimi bulunamadı (.claude-plugin/marketplace.json): {path}"


@dataclass(frozen=True, slots=True)
class PluginPreview:
    """Onay ekranının gösterdiği özet."""

    report: ValidationReport
    source: str
    context_tokens: int

    @property
    def name(self) -> str:
        return self.report.layout.name if self.report.layout else ""

    @property
    def is_executable(self) -> bool:
        return bool(self.report.layout and self.report.layout.is_executable)


ApprovalCallback = Callable[[PluginPreview], bool]


@dataclass(frozen=True, slots=True)
class _Resolved:
    kind: str
    location: str
    marketplace: str = ""
    ref: str = ""
    sha: str = ""


# --- Kaynak çözümleme ----------------------------------------------------------- #


def _resolve(spec: str, state: PluginState) -> _Resolved:
    text = spec.strip()
    local = Path(text).expanduser()
    if text and local.is_dir():
        return _Resolved("yerel", str(local.resolve()))
    if text.startswith("https://"):
        return _Resolved("git", text)
    parts = text.split("/")
    if len(parts) == 2 and all(parts) and "@" not in text:
        return _Resolved("git", f"https://github.com/{text}")
    name, _, market = text.partition("@")
    if name:
        return _from_marketplace(name, market, state)
    raise PluginError(ERR_SOURCE.format(spec=spec))


def _from_marketplace(name: str, market: str, state: PluginState) -> _Resolved:
    hits = [(record, entry) for record, entry in _entries(state) if entry.name == name]
    if market:
        hits = [(record, entry) for record, entry in hits if record.name == market]
    if not hits:
        raise PluginError(ERR_NO_ENTRY.format(name=name))
    if len(hits) > 1:
        raise PluginError(
            ERR_AMBIGUOUS.format(name=name, markets=", ".join(r.name for r, _ in hits))
        )
    record, entry = hits[0]
    source = entry.source
    if source.kind == "path":
        location = str((Path(record.path) / source.location).resolve())
        if not Path(location).is_relative_to(Path(record.path).resolve()):
            raise PluginError(ERR_SOURCE.format(spec=f"{name}@{record.name}"))
        return _Resolved("yerel", location, record.name)
    return _Resolved("git", source.location, record.name, source.ref, source.sha)


def _check_url(url: str) -> None:
    """Klon adresi genel bir https sunucusu mu (iç ağ, kimlik bilgisi, sorgu yok)?"""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise PluginError(ERR_URL.format(url=url))
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, 443)}
    except OSError as error:
        raise PluginError(f"{ERR_URL.format(url=url)} ({error})") from error
    if not addresses or not all(is_public_ip(str(address)) for address in addresses):
        raise PluginError(ERR_URL.format(url=url))


@contextmanager
def _workspace(base: Path) -> Iterator[Path]:
    temp_root = base / _TEMP_DIRNAME
    temp_root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(dir=temp_root))
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def _clone(url: str, target: Path, *, ref: str = "", sha: str = "") -> str:
    _check_url(url)
    args = ["clone", "--depth", "1", "--quiet"]
    if ref:
        args += ["--branch", ref]
    try:
        capability_install._git(
            [*args, url, str(target)], cwd=target.parent, timeout=capability_install.CLONE_TIMEOUT_S
        )
        commit = capability_install._git(["rev-parse", "HEAD"], cwd=target, timeout=GIT_TIMEOUT_S)
    except capability_install.CapabilityInstallError as error:
        raise PluginError(str(error)) from error
    commit = commit.strip()
    if sha and not commit.startswith(sha.strip().lower()):
        raise PluginError(ERR_SHA.format(expected=sha, actual=commit[:12]))
    shutil.rmtree(target / ".git", ignore_errors=True)
    return commit


def _fetch(resolved: _Resolved, workspace: Path) -> tuple[Path, str]:
    """Kaynağı `workspace/eklenti` altına al; (klasör, commit)."""
    target = workspace / "eklenti"
    if resolved.kind == "yerel":
        shutil.copytree(
            resolved.location, target, symlinks=True, ignore=shutil.ignore_patterns(".git")
        )
        return target, ""
    return target, _clone(resolved.location, target, ref=resolved.ref, sha=resolved.sha)


# --- Kur / önizle ------------------------------------------------------------- #


def preview_plugin(spec: str, *, base: Path | None = None) -> PluginPreview:
    """Kurmadan doğrula (masaüstü onay kartı ve `--dry-run`)."""
    root = base or plugins_dir()
    resolved = _resolve(spec, load_state(root))
    with _workspace(root) as workspace:
        folder, _commit = _fetch(resolved, workspace)
        report = validate_plugin(folder)
        tokens = context_cost(report.layout) if report.layout else 0
        # Geçici klasör silinir; özet yalnız sayı/ad/uyarı olarak gösterilir.
        return PluginPreview(report, spec, tokens)


def install_plugin(
    spec: str, *, approve: ApprovalCallback, base: Path | None = None
) -> InstalledPlugin:
    root = base or plugins_dir()
    state = load_state(root)
    resolved = _resolve(spec, state)
    with _workspace(root) as workspace:
        folder, commit = _fetch(resolved, workspace)
        report = validate_plugin(folder)
        if not report.ok or report.layout is None:
            raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
        name = report.layout.name
        if state.plugin(name) is not None or (root / name).exists():
            raise PluginError(ERR_EXISTS.format(name=name))
        preview = PluginPreview(report, spec, context_cost(report.layout))
        executable = report.layout.is_executable
        if not approve(preview):
            raise PluginError(ERR_DECLINED)
        destination = root / name
        shutil.move(str(folder), destination)
    record = PluginRecord(
        name=name,
        version=report.layout.manifest.version,
        source=f"{name}@{resolved.marketplace}" if resolved.marketplace else resolved.location,
        kind="pazar" if resolved.marketplace else resolved.kind,
        marketplace=resolved.marketplace,
        commit=commit,
        digest=tree_digest(destination),
        enabled=True,
        exec_approved=executable,
        installed_at=time.time(),
    )
    save_state(load_state(root).with_plugin(record), root)
    return inspect_plugin(record, root)


def uninstall_plugin(name: str, *, base: Path | None = None) -> Path:
    """Klasörü Fusion çöpüne taşı (`fusion cop geri-al`) ve kaydı sil."""
    root = base or plugins_dir()
    state = load_state(root)
    if state.plugin(name) is None:
        raise PluginError(ERR_NOT_INSTALLED.format(name=name))
    folder = root / name
    if folder.is_dir():
        try:
            move_to_trash((name,), cwd=root, root=root, home=Path.home(), trash_root=trash_dir())
        except DeleteRefusedError as error:
            raise PluginError(str(error)) from error
    save_state(state.without_plugin(name), root)
    return folder


def set_plugin_enabled(name: str, enabled: bool, *, base: Path | None = None) -> PluginRecord:
    root = base or plugins_dir()
    state = load_state(root)
    record = state.plugin(name)
    if record is None:
        raise PluginError(ERR_NOT_INSTALLED.format(name=name))
    updated = replace(record, enabled=enabled)
    save_state(state.with_plugin(updated), root)
    return updated


def set_all_disabled(disabled: bool, *, base: Path | None = None) -> None:
    root = base or plugins_dir()
    save_state(replace(load_state(root), all_disabled=disabled), root)


def trust_plugin(name: str, *, approve: ApprovalCallback, base: Path | None = None) -> PluginRecord:
    """Değişmiş eklentinin güncel içeriğini yeniden onayla (karma ve çalıştırma onayı yenilenir)."""
    root = base or plugins_dir()
    state = load_state(root)
    record = state.plugin(name)
    if record is None:
        raise PluginError(ERR_NOT_INSTALLED.format(name=name))
    report = validate_plugin(root / name)
    if not report.ok or report.layout is None:
        raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
    if not approve(PluginPreview(report, record.source, context_cost(report.layout))):
        raise PluginError(ERR_DECLINED)
    updated = replace(
        record,
        digest=tree_digest(root / name),
        version=report.layout.manifest.version,
        exec_approved=report.layout.is_executable,
    )
    save_state(state.with_plugin(updated), root)
    return updated


# --- Pazar yerleri ------------------------------------------------------------ #


def read_marketplace(folder: Path) -> Marketplace:
    for relative in MARKETPLACE_PATHS:
        path = folder / relative
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise PluginError(f"{relative}: okunamadı: {error}") from error
            return parse_marketplace(raw, where=relative)
    raise PluginError(ERR_MARKET_FILE.format(path=folder))


def add_marketplace(spec: str, *, base: Path | None = None) -> MarketplaceRecord:
    """Yerel klasör ya da git deposunu pazar olarak kaydet (git ise klonlanır)."""
    root = base or plugins_dir()
    text = OFFICIAL_MARKETPLACE if spec.strip().lower() == OFFICIAL_ALIAS else spec.strip()
    local = Path(text).expanduser()
    if local.is_dir():
        market = read_marketplace(local)
        record = MarketplaceRecord(
            market.name, str(local.resolve()), "yerel", str(local.resolve()), time.time()
        )
    else:
        url = text if text.startswith("https://") else f"https://github.com/{text}"
        if not text.startswith("https://") and text.count("/") != 1:
            raise PluginError(ERR_SOURCE.format(spec=spec))
        with _workspace(root) as workspace:
            clone = workspace / "pazar"
            _clone(url, clone)
            market = read_marketplace(clone)
            destination = root / _MARKETS_DIRNAME / market.name
            shutil.rmtree(destination, ignore_errors=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(clone), destination)
        record = MarketplaceRecord(market.name, url, "git", str(destination), time.time())
    save_state(load_state(root).with_marketplace(record), root)
    return record


def remove_marketplace(name: str, *, base: Path | None = None) -> None:
    root = base or plugins_dir()
    state = load_state(root)
    record = state.marketplace(name)
    if record is None:
        raise PluginError(ERR_NO_MARKET.format(name=name))
    if record.kind == "git":
        shutil.rmtree(Path(record.path), ignore_errors=True)
    save_state(state.without_marketplace(name), root)


def _entries(state: PluginState) -> Iterator[tuple[MarketplaceRecord, MarketplaceEntry]]:
    for record in state.marketplaces:
        try:
            market = read_marketplace(Path(record.path))
        except PluginError:
            continue
        for entry in market.entries:
            yield record, entry


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """`fusion eklenti kesfet` satırı."""

    marketplace: str
    entry: MarketplaceEntry
    installed: bool


def browse(marketplace: str = "", *, base: Path | None = None) -> tuple[CatalogEntry, ...]:
    """Kayıtlı pazarlardaki eklentiler (ağ YOK: git pazarları kayıt anındaki klondan okunur)."""
    root = base or plugins_dir()
    state = load_state(root)
    if marketplace and state.marketplace(marketplace) is None:
        raise PluginError(ERR_NO_MARKET.format(name=marketplace))
    installed = {record.name for record in state.plugins}
    return tuple(
        CatalogEntry(record.name, entry, entry.name in installed)
        for record, entry in _entries(state)
        if not marketplace or record.name == marketplace
    )
