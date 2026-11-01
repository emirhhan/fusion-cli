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

import ipaddress
import json
import os
import re
import shutil
import socket
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from ..config import plugin_layout, plugin_store
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
_TEMP_DIRNAME = ".gecici"
_MARKETS_DIRNAME = ".pazarlar"

#: Claude: 'Plugin "x@m" is already installed (scope: …)', çıkış kodu 0 (#407).
ERR_EXISTS = (
    'Eklenti "{name}" zaten kurulu (kapsam: user). Güncellemek için: fusion plugin update {name}'
)
#: Claude: 'Plugin "x" is already enabled/disabled', çıkış kodu 1 (#417).
ERR_ALREADY = 'Eklenti "{name}" zaten {state}'
ERR_NOT_INSTALLED = "Kurulu değil: {name}"
ERR_INVALID = "Eklenti geçersiz:\n  - {errors}"
ERR_DECLINED = "Kurulum onaylanmadı; hiçbir şey yazılmadı."
ERR_RENAMED = "Eklentinin adı değişti ({old} → {new}); yeniden onaylanmaz. Kaldırıp yeniden kur."
ERR_SOURCE = (
    "Kaynak anlaşılamadı: {spec}. Yerel klasör, https://… git adresi, sahip/repo ya da "
    "ad@pazar ver."
)
ERR_URL = "Yalnız genel https adresleri klonlanır: {url}"
ERR_NO_ENTRY = "'{name}' hiçbir kayıtlı pazarda yok. Pazarlar: fusion eklenti pazar liste"
ERR_AMBIGUOUS = "'{name}' birden çok pazarda var: {markets}. ad@pazar biçimini kullan."
ERR_CHANGED = (
    "Eklenti önizlemeden sonra değişti (karma {expected} → {actual}); hiçbir şey yazılmadı. "
    "Güncel içeriği yeniden önizleyip onayla."
)
ERR_SHA = "Commit uyuşmuyor: pazar {expected} bekliyor, klon {actual}. Kurulmadı."
ERR_SHA_FORMAT = "Pazar sha pini en az 7 onaltılık karakter olmalı: {sha!r}. Kurulmadı."
ERR_NO_MARKET = "Pazar yok: {name}"
ERR_MARKET_TAKEN = (
    "'{name}' adlı pazar zaten kayıtlı ({source}); kaynak değişmedi. Değiştirmek için önce "
    "kaldır: fusion eklenti pazar kaldir {name}"
)
ERR_MARKET_FILE = "Pazar bildirimi bulunamadı (.claude-plugin/marketplace.json): {path}"


@dataclass(frozen=True, slots=True)
class PluginPreview:
    """Onay ekranının gösterdiği özet."""

    report: ValidationReport
    source: str
    context_tokens: int
    #: Gösterilen içeriğin karması: kur/güven isteği bunu `expected_digest` olarak geri yollar.
    digest: str = ""
    commit: str = ""

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
    #: Pazar girdisinin adı (bildirimsiz eklentinin adı buradan gelir, #390).
    entry: str = ""

    @property
    def fallback_name(self) -> str:
        """Claude: bildirim yoksa ad pazar girdisinden, yoksa özgün klasör adından gelir."""
        if self.entry:
            return self.entry
        tail = self.location.rstrip("/").rsplit("/", 1)[-1]
        return tail.removesuffix(".git")


#: Klonda git'in kendi başına iç ağa ya da başka protokole gitmesini engelleyen ayarlar.
#
# Ölçüldü (31 Ekim): `_check_url` yalnız ilk DNS çözümlemesini denetliyordu; `git clone` kendi
# çözümlemesini yapıp HTTP yönlendirmesini izliyordu (`http.followRedirects=initial`): genel bir
# sunucu `302 → http://127.0.0.1/…` ile kör SSRF açabiliyordu. Yönlendirme kapalı, yalnız https,
# ve (git ≥ 2.37) bağlantı denetlenen IP'ye sabitlenir (`http.curloptResolve`, DNS rebinding).
_SAFE_GIT_CONFIG: tuple[str, ...] = (
    "http.followRedirects=false",
    "protocol.allow=never",
    "protocol.https.allow=always",
)
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_FULL_SHA_LENGTH = 40


def _git_options(url: str, address: str | None) -> list[str]:
    options = [item for pair in (("-c", c) for c in _SAFE_GIT_CONFIG) for item in pair]
    host = urlsplit(url).hostname
    if address and host:
        shown = f"[{address}]" if ipaddress.ip_address(address).version == 6 else address
        options += ["-c", f"http.curloptResolve={host}:443:{shown}"]
    return options


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
        from .plugin_market_source import market_root

        base_dir = market_root(record.kind, Path(record.path))
        location = str((base_dir / source.location).resolve())
        if not Path(location).is_relative_to(base_dir.resolve()):
            raise PluginError(ERR_SOURCE.format(spec=f"{name}@{record.name}"))
        return _Resolved("yerel", location, record.name, entry=entry.name)
    return _Resolved("git", source.location, record.name, source.ref, source.sha, entry.name)


def _check_url(url: str) -> str | None:
    """Klon adresi genel bir https sunucusu mu (iç ağ, kimlik bilgisi yok)? Denetlenen IP."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise PluginError(ERR_URL.format(url=url))
    try:
        addresses = sorted({str(info[4][0]) for info in socket.getaddrinfo(parts.hostname, 443)})
    except OSError as error:
        raise PluginError(f"{ERR_URL.format(url=url)} ({error})") from error
    if not addresses or not all(is_public_ip(address) for address in addresses):
        raise PluginError(ERR_URL.format(url=url))
    return addresses[0]


def markets_dir(root: Path) -> Path:
    """Git pazarlarının klon klasörü (`<eklentiler>/.pazarlar`)."""
    return root / _MARKETS_DIRNAME


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
    """Sığ klon; commit döner. Tam (40 karakter) sha pini o commit'i doğrudan çeker.

    Ölçüldü (31 Ekim): pin yalnız `--depth 1` klonunun HEAD'iyle karşılaştırılıyordu; dal ucu
    ilerleyen depoda pinli eklenti hiç kurulamıyordu. Tek karakterlik pin de kabul ediliyordu.
    Kısa pin (7-39) dal ucuna eşitse kurulur; değilse tam sha istenir (git kısa sha çekemez).
    """
    pin = sha.strip().lower()
    if pin and not _SHA.match(pin):
        raise PluginError(ERR_SHA_FORMAT.format(sha=sha))
    options = _git_options(url, _check_url(url))
    timeout = capability_install.CLONE_TIMEOUT_S
    try:
        if len(pin) == _FULL_SHA_LENGTH:
            capability_install._git(
                [*options, "init", "--quiet", str(target)], cwd=target.parent, timeout=timeout
            )
            capability_install._git(
                [*options, "fetch", "--depth", "1", "--quiet", url, pin],
                cwd=target,
                timeout=timeout,
            )
            capability_install._git(
                ["checkout", "--quiet", "FETCH_HEAD"], cwd=target, timeout=timeout
            )
        else:
            args = [*options, "clone", "--depth", "1", "--quiet"]
            if ref:
                args += ["--branch", ref]
            capability_install._git([*args, url, str(target)], cwd=target.parent, timeout=timeout)
        commit = capability_install._git(["rev-parse", "HEAD"], cwd=target, timeout=GIT_TIMEOUT_S)
    except capability_install.CapabilityInstallError as error:
        raise PluginError(str(error)) from error
    commit = commit.strip().lower()
    if pin and not commit.startswith(pin):
        raise PluginError(ERR_SHA.format(expected=sha, actual=commit[:12]))
    shutil.rmtree(target / ".git", ignore_errors=True)
    return commit


def _check_local_size(folder: Path) -> None:
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


def _fetch(resolved: _Resolved, workspace: Path) -> tuple[Path, str]:
    """Kaynağı `workspace/eklenti` altına al; (klasör, commit)."""
    target = workspace / "eklenti"
    if resolved.kind == "yerel":
        _check_local_size(Path(resolved.location))
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
        folder, commit = _fetch(resolved, workspace)
        report = validate_plugin(folder, resolved.fallback_name)
        tokens = context_cost(report.layout) if report.layout else 0
        # Geçici klasör silinir; özet yalnız sayı/ad/uyarı olarak gösterilir.
        return PluginPreview(report, spec, tokens, _safe_digest(folder, report), commit)


def _safe_digest(folder: Path, report: ValidationReport) -> str:
    """Boyut sınırını aşan klasörde karma yok (rapor zaten hata taşır)."""
    try:
        return tree_digest(folder) if report.layout is not None else ""
    except PluginError:
        return ""


def _check_expected(expected: str, actual: str) -> None:
    """Ölçüldü (31 Ekim): önizleme ve kurulum iki ayrı çekişti; kullanıcının onayladığı
    içerik ile kurulan içerik farklı olabiliyordu (pinsiz git HEAD'i, yerel klasör)."""
    if expected and expected.strip().lower() != actual:
        raise PluginError(ERR_CHANGED.format(expected=expected[:12], actual=actual[:12]))


def install_plugin(
    spec: str,
    *,
    approve: ApprovalCallback,
    base: Path | None = None,
    expected_digest: str = "",
) -> InstalledPlugin:
    """Kur. `expected_digest` verildiyse çekilen içerik önizlemedekiyle aynı olmalıdır."""
    root = base or plugins_dir()
    state = load_state(root)
    resolved = _resolve(spec, state)
    if _loads_in_place(resolved, state):
        from .plugin_in_place import install_in_place

        return install_in_place(resolved, spec, state, root, approve, expected_digest)
    with _workspace(root) as workspace:
        folder, commit = _fetch(resolved, workspace)
        report = validate_plugin(folder, resolved.fallback_name)
        if not report.ok or report.layout is None:
            raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
        name = report.layout.name
        if state.plugin(name) is not None or (root / name).exists():
            raise PluginAlreadyInstalledError(ERR_EXISTS.format(name=name))
        digest = tree_digest(folder)
        _check_expected(expected_digest, digest)
        preview = PluginPreview(report, spec, context_cost(report.layout), digest, commit)
        executable = report.layout.is_executable
        if not approve(preview):
            raise PluginError(ERR_DECLINED)
        destination = root / name
        shutil.move(str(folder), destination)
    record = PluginRecord(
        name=name,
        version=report.layout.manifest.version,
        source=f"{resolved.entry or name}@{resolved.marketplace}"
        if resolved.marketplace
        else resolved.location,
        kind="pazar" if resolved.marketplace else resolved.kind,
        marketplace=resolved.marketplace,
        commit=commit,
        digest=tree_digest(destination),
        # Claude: `defaultEnabled: false` eklenti kapalı başlar (#389).
        enabled=report.layout.manifest.default_enabled,
        exec_approved=executable,
        installed_at=time.time(),
    )
    try:
        plugin_store.update_state(lambda current: current.with_plugin(record), root)
    except BaseException:
        # Kayıt yazılamadıysa klasör kayıtsız kalmasın ("zaten kurulu" / "kurulu değil" çelişkisi).
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return inspect_plugin(record, root)


def _loads_in_place(resolved: _Resolved, state: PluginState) -> bool:
    """Yerel klasörden eklenmiş pazarın göreli (path) eklentisi mi? (Claude: yerinde yüklenir)"""
    market = state.marketplace(resolved.marketplace) if resolved.marketplace else None
    local = market is not None and market.kind in ("yerel", "dosya")
    return local and resolved.kind == "yerel"


def uninstall_plugin(
    name: str, *, base: Path | None = None, keep_data: bool = False, scope: str = ""
) -> Path:
    """Klasörü Fusion çöpüne taşı (`fusion cop geri-al`), kaydı ve veri klasörünü sil (#408).

    Claude gibi `ad@pazar` kabul eder; `--keep-data` verilmezse `${CLAUDE_PLUGIN_DATA}` silinir.
    """
    from .plugin_toggle import check_uninstall_scope, find_record, remove_plugin_data

    check_uninstall_scope(name, scope)
    root = base or plugins_dir()
    found = find_record(load_state(root), name)
    name = found.name
    folder = plugin_store.plugin_folder(found, root)
    # Yerinde yüklenen eklentinin klasörü kullanıcının pazar kaynağıdır: asla taşınmaz (#403).
    if not found.folder and folder.is_dir():
        try:
            move_to_trash((name,), cwd=root, root=root, home=Path.home(), trash_root=trash_dir())
        except DeleteRefusedError as error:
            raise PluginError(str(error)) from error
    plugin_store.update_state(lambda current: current.without_plugin(name), root)
    if not keep_data:
        remove_plugin_data(name)
    return folder


def set_plugin_enabled(
    name: str,
    enabled: bool,
    *,
    base: Path | None = None,
    scope: str = "",
    root: Path | None = None,
) -> str:
    """Aç/kapat; yazılan kapsamı döndürür (`--scope` yoksa local/project/user algılanır, #376)."""
    from .plugin_toggle import toggle_plugin

    return toggle_plugin(name, enabled, scope=scope, base=base, root=root).scope


class PluginAlreadyInstalledError(PluginError):
    """Eklenti zaten kurulu: Claude bunu bilgi olarak basar ve 0 ile çıkar."""


def disable_all_plugins(*, base: Path | None = None) -> tuple[str, ...]:
    """`disable --all` (#409): her etkin eklentiyi AYRI ayrı kapat; kapatılanların adları."""
    root = base or plugins_dir()
    closed: list[str] = []

    def change(current: PluginState) -> PluginState:
        closed.clear()
        updated = current
        for record in current.plugins:
            if record.enabled:
                closed.append(record.name)
                updated = updated.with_plugin(replace(record, enabled=False))
        return replace(updated, all_disabled=False)

    plugin_store.update_state(change, root)
    return tuple(closed)


def set_all_disabled(disabled: bool, *, base: Path | None = None) -> None:
    root = base or plugins_dir()
    plugin_store.update_state(lambda current: replace(current, all_disabled=disabled), root)


def trust_plugin(
    name: str,
    *,
    approve: ApprovalCallback,
    base: Path | None = None,
    expected_digest: str = "",
) -> PluginRecord:
    """Değişmiş eklentinin güncel içeriğini yeniden onayla (karma ve çalıştırma onayı yenilenir)."""
    root = base or plugins_dir()
    state = load_state(root)
    record = state.plugin(name)
    if record is None:
        raise PluginError(ERR_NOT_INSTALLED.format(name=name))
    folder = plugin_store.plugin_folder(record, root)
    report = validate_plugin(folder)
    if not report.ok or report.layout is None:
        raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
    if report.layout.name != record.name:
        # Önekler ve MCP adları kayıt adına bağlıdır; ad değişimi gölgeleme kapısı olurdu.
        raise PluginError(ERR_RENAMED.format(old=record.name, new=report.layout.name))
    digest = "" if record.folder else tree_digest(folder)
    _check_expected(expected_digest, digest)
    preview = PluginPreview(
        report, record.source, context_cost(report.layout), digest, record.commit
    )
    if not approve(preview):
        raise PluginError(ERR_DECLINED)
    updated = replace(
        record,
        digest=digest,
        version=report.layout.manifest.version,
        exec_approved=report.layout.is_executable,
    )
    plugin_store.update_state(lambda current: current.with_plugin(updated), root)
    return updated


# --- Pazar yerleri ------------------------------------------------------------ #


def read_marketplace(folder: Path) -> Marketplace:
    """Pazar klasörünün bildirimini ya da doğrudan verilen `.json` dosyasını (#395) oku."""
    if folder.is_file():
        try:
            raw = json.loads(folder.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise PluginError(f"{folder.name}: okunamadı: {error}") from error
        return parse_marketplace(raw, where=folder.name)
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
    """Yerel klasör/.json dosyası ya da git deposunu pazar olarak kaydet (git ise klonlanır)."""
    from .plugin_market_source import KIND_GIT, parse_market_source

    root = base or plugins_dir()
    source = parse_market_source(spec)
    if source.kind != KIND_GIT:
        market = read_marketplace(Path(source.location))
        _check_market_name(market.name, source.location, root)
        record = MarketplaceRecord(
            market.name, source.location, source.kind, source.location, time.time()
        )
    else:
        with _workspace(root) as workspace:
            clone = workspace / "pazar"
            _clone(source.location, clone, ref=source.ref)
            market = read_marketplace(clone)
            _check_market_name(market.name, source.record_source, root)
            destination = markets_dir(root) / market.name
            shutil.rmtree(destination, ignore_errors=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(clone), destination)
        record = MarketplaceRecord(
            market.name, source.record_source, "git", str(destination), time.time()
        )
    plugin_store.update_state(lambda current: current.with_marketplace(record), root)
    return record


def _check_market_name(name: str, source: str, root: Path) -> None:
    """Ölçüldü (31 Ekim): aynı adlı başka kaynaklı pazar eskisinin yerine sessizce geçiyor,
    `ad@pazar` kurulumları yeni (belki saldırgan) depoya gidiyordu. Aynı kaynak = yenileme."""
    existing = load_state(root).marketplace(name)
    if existing is not None and existing.source != source:
        raise PluginError(ERR_MARKET_TAKEN.format(name=name, source=existing.source))


def remove_marketplace(name: str, *, base: Path | None = None) -> tuple[str, ...]:
    """Pazarı ve ondan kurulan BÜTÜN eklentileri kaldır (Claude, #396); kaldırılan eklentiler."""
    from .plugin_toggle import plugins_from_marketplace

    root = base or plugins_dir()
    state = load_state(root)
    record = state.marketplace(name)
    if record is None:
        raise PluginError(ERR_NO_MARKET.format(name=name))
    removed = plugins_from_marketplace(name, root)
    for plugin in removed:
        uninstall_plugin(f"{plugin}@{name}", base=root)
    clones = markets_dir(root).resolve()
    folder = Path(record.path).resolve()
    # Yalnız Fusion'ın kendi klonu silinir: elle bozulmuş kayıttaki `~/Belgeler` silinmez.
    if record.kind == "git" and folder.is_relative_to(clones) and folder != clones:
        shutil.rmtree(folder, ignore_errors=True)
    plugin_store.update_state(lambda current: current.without_marketplace(name), root)
    return removed


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
