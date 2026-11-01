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
from ..core.plugin_marketplace import MarketplaceSource
from ..core.plugins import (
    MARKETPLACE_PATHS,
    Marketplace,
    MarketplaceEntry,
    PluginError,
    parse_marketplace,
)
from . import capability_install
from .plugin_source_fetch import CommandConsent
from .plugin_version import orphan, resolve_version, sweep_orphans

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
ERR_SUBDIR = "git-subdir: depoda '{path}' klasörü yok; kurulmadı."
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
ERR_URL_RELATIVE = (
    "'{name}@{market}': adresten (url türü) eklenen pazarda göreli yollu eklenti kurulamaz; "
    "pazarı git deposu olarak ekle"
)
ERR_MARKET_PARTIAL = (
    "'{name}' pazarı kaldırılmadı; şu eklentiler kaldırılamadı: {errors}. "
    "Sorunu giderip yeniden deneyin (kaldırılanlar geri gelmez)."
)
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
    #: `git-subdir` kaynağında depodaki eklenti klasörü (#399).
    subdir: str = ""
    #: Pazar girdisinin `version`'ı ve git pazarının klonu (göreli eklentinin commit'i, #393).
    entry_version: str = ""
    commit_dir: str = ""
    #: Girdinin plugin.json alanları ve strict modu (#398).
    entry_fields: str = ""
    strict: bool = True
    #: `archive`/`npm`/`command` kaynağı ve katalog sürümü (komut onay özeti, #399).
    source: MarketplaceSource | None = None
    revision: str = ""
    #: command `mode: link` çıktısı yerinde yüklenir.
    link: bool = False

    @property
    def plugin_id(self) -> str:
        return f"{self.entry}@{self.marketplace}" if self.marketplace else self.location

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
    if source.kind == "path" and record.kind == "url":
        raise PluginError(ERR_URL_RELATIVE.format(name=name, market=record.name))
    if source.kind == "path":
        from .plugin_market_source import market_root

        base_dir = market_root(record.kind, Path(record.path))
        location = str((base_dir / source.location).resolve())
        if not Path(location).is_relative_to(base_dir.resolve()):
            raise PluginError(ERR_SOURCE.format(spec=f"{name}@{record.name}"))
        commit_dir = record.path if record.kind == "git" else ""
        return _Resolved(
            "yerel",
            location,
            record.name,
            entry=entry.name,
            entry_version=entry.version,
            commit_dir=commit_dir,
            entry_fields=entry.fields,
            strict=entry.strict,
        )
    if source.kind in EXTRA_KINDS:
        return _Resolved(
            source.kind,
            source.location,
            record.name,
            entry=entry.name,
            entry_version=entry.version,
            entry_fields=entry.fields,
            strict=entry.strict,
            source=source,
            revision=_revision(record),
        )
    return _Resolved(
        "git",
        source.location,
        record.name,
        source.ref,
        source.sha,
        entry.name,
        source.subdir,
        entry_version=entry.version,
        entry_fields=entry.fields,
        strict=entry.strict,
    )


EXTRA_KINDS = frozenset({"archive", "npm", "command"})


def _revision(record: MarketplaceRecord) -> str:
    from .plugin_source_fetch import catalog_revision

    path = Path(record.path)
    return catalog_revision(
        path if path.is_file() else path / ".claude-plugin" / "marketplace.json"
    )


class PrivateUrlError(PluginError):
    """Adres genel https değil (iç ağ, kimlik bilgili ya da başka şema)."""


def _check_url(url: str) -> str | None:
    """Klon adresi genel bir https sunucusu mu (iç ağ, kimlik bilgisi yok)? Denetlenen IP."""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise PrivateUrlError(ERR_URL.format(url=url))
    try:
        addresses = sorted({str(info[4][0]) for info in socket.getaddrinfo(parts.hostname, 443)})
    except OSError as error:
        raise PluginError(f"{ERR_URL.format(url=url)} ({error})") from error
    if not addresses or not all(is_public_ip(address) for address in addresses):
        raise PrivateUrlError(ERR_URL.format(url=url))
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


def _fetch(
    resolved: _Resolved, workspace: Path, consent: CommandConsent | None = None
) -> tuple[Path, str]:
    """Kaynağı `workspace/eklenti` altına al, girdi alanlarını uygula (#398); (klasör, commit)."""
    if resolved.source is not None and resolved.kind in EXTRA_KINDS:
        folder, commit = _fetch_extra(resolved, resolved.source, workspace, consent)
    else:
        folder, commit = _fetch_raw(resolved, workspace)
    if resolved.entry_fields:
        from .plugin_entry import apply_entry

        apply_entry(folder, resolved.entry_fields, resolved.strict, resolved.fallback_name)
    return folder, commit


def _fetch_extra(
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
    _check_local_size(printed)
    shutil.copytree(printed, target, symlinks=True, ignore=shutil.ignore_patterns(".git"))
    return target, tree_digest(target)


def _fetch_raw(resolved: _Resolved, workspace: Path) -> tuple[Path, str]:
    target = workspace / "eklenti"
    if resolved.kind == "yerel":
        _check_local_size(Path(resolved.location))
        shutil.copytree(
            resolved.location, target, symlinks=True, ignore=shutil.ignore_patterns(".git")
        )
        return target, ""
    if not resolved.subdir:
        return target, _clone(resolved.location, target, ref=resolved.ref, sha=resolved.sha)
    repo = workspace / "depo"
    commit = _clone(resolved.location, repo, ref=resolved.ref, sha=resolved.sha)
    folder = (repo / resolved.subdir).resolve()
    if not folder.is_dir() or not folder.is_relative_to(repo.resolve()):
        raise PluginError(ERR_SUBDIR.format(path=resolved.subdir))
    shutil.move(str(folder), target)
    return target, commit


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
    accept_command: CommandConsent | None = None,
    pin: tuple[str, str] | None = None,
) -> InstalledPlugin:
    """Kur. `expected_digest` verildiyse çekilen içerik önizlemedekiyle aynı olmalıdır.

    `pin`: (etiket, sha) — bağımlılık sürüm aralığının çözdüğü `<ad>--v<sürüm>` etiketi (#389).

    `accept_command`: pazarın bildirdiği komut (command kaynağı, archive headersHelper) için
    onay; verilmezse böyle bir kaynak `CommandRefusedError` ile reddedilir (#399).
    """
    root = base or plugins_dir()
    sweep_orphans(root)
    state = load_state(root)
    from .plugin_update import refresh_marketplace_for

    if refresh_marketplace_for(spec, state.marketplaces, base=root):  # Claude: ad@pazar (#393)
        state = load_state(root)
    resolved = _resolve(spec, state)
    if pin:
        from .plugin_dependency_versions import pinned_source

        resolved = pinned_source(resolved, pin, state)
    resolved = _linked_command(resolved, accept_command)
    if _loads_in_place(resolved, state):
        from .plugin_in_place import install_in_place

        return install_in_place(resolved, spec, state, root, approve, expected_digest)
    with _workspace(root) as workspace:
        folder, commit = _fetch(resolved, workspace, accept_command)
        report = validate_plugin(folder, resolved.fallback_name)
        if not report.ok or report.layout is None:
            raise PluginError(ERR_INVALID.format(errors="\n  - ".join(report.errors)))
        name = report.layout.name
        key = plugin_store.same_name_key(state, name, resolved.marketplace)
        if key is None or (root / key).exists():
            raise PluginAlreadyInstalledError(ERR_EXISTS.format(name=name))
        digest = tree_digest(folder)
        _check_expected(expected_digest, digest)
        preview = PluginPreview(report, spec, context_cost(report.layout), digest, commit)
        executable = report.layout.is_executable
        if not approve(preview):
            raise PluginError(ERR_DECLINED)
        destination = root / key
        shutil.move(str(folder), destination)
    record = PluginRecord(
        key=key if key != name else "",
        name=name,
        version=version_of(resolved, report.layout.manifest.version, commit),
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
        accepted_command=accepted_command_of(resolved),
    )
    try:
        plugin_store.update_state(lambda current: current.with_plugin(record), root)
    except BaseException:
        # Kayıt yazılamadıysa klasör kayıtsız kalmasın ("zaten kurulu" / "kurulu değil" çelişkisi).
        shutil.rmtree(destination, ignore_errors=True)
        raise
    return inspect_plugin(record, root)


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
    """Onaylanan komut metni (güncellemede değişmediyse yeniden sorulmaz, #399)."""
    source = resolved.source
    if source is None:
        return ""
    if source.kind == "command":
        return f"{source.option('mode', 'copy')} {source.location}"
    return source.option("headersHelper")


def _linked_command(resolved: _Resolved, consent: CommandConsent | None) -> _Resolved:
    """command `mode: link`: basılan klasör kopyalanmadan yerinde yüklenir (Claude)."""
    source = resolved.source
    if resolved.kind != "command" or source is None or source.option("mode") != "link":
        return resolved
    from .plugin_source_fetch import run_command_source

    printed = run_command_source(
        source, plugin_id=resolved.plugin_id, revision=resolved.revision, consent=consent
    )
    return replace(resolved, kind="yerel", location=str(printed), source=None, link=True)


def _loads_in_place(resolved: _Resolved, state: PluginState) -> bool:
    """Yerel klasörden eklenmiş pazarın göreli (path) eklentisi mi? (Claude: yerinde yüklenir)"""
    if resolved.link:
        return True
    market = state.marketplace(resolved.marketplace) if resolved.marketplace else None
    local = market is not None and market.kind in ("yerel", "dosya")
    return local and resolved.kind == "yerel"


def uninstall_plugin(
    name: str,
    *,
    base: Path | None = None,
    keep_data: bool = False,
    scope: str = "",
    everywhere: bool = False,
    root: Path | None = None,
) -> Path:
    """Eklentiyi kapsamdan kaldır; SON kapsamdan kalkınca kopyayı `.orphaned_at` ile eski
    sürümlere taşı (14 gün sonra silinir), kaydı, userConfig değerlerini/sırlarını ve
    `--keep-data` yoksa veri klasörünü sil (Claude `plugin uninstall`, #408/#388).

    `everywhere` (pazar kaldırma/forceRemoveDeletedPlugins) bütün kapsamlardan kaldırır.
    """
    from .plugin_install_scope import default_scope, drop_scope
    from .plugin_toggle import check_uninstall_scope, find_record

    check_uninstall_scope(name, scope)
    store = base or plugins_dir()
    found = find_record(load_state(store), name)
    folder = plugin_store.plugin_folder(found, store)
    target = scope or default_scope(found, root)
    if not everywhere and drop_scope(found, target, store, root).scopes:
        return folder  # başka kapsamlar kullanıyor: paylaşılan kopya ve veri kalır
    remove_installation(found, store, keep_data=keep_data)
    return folder


def remove_installation(record: PluginRecord, root: Path, *, keep_data: bool) -> None:
    """Kopya, kayıt, userConfig değerleri/sırları ve (istenirse) veri klasörü (#408)."""
    from ..config.plugin_storage import storage_key
    from ..config.plugin_user_config import forget_values
    from .plugin_toggle import remove_plugin_data

    folder = plugin_store.plugin_folder(record, root)
    # Yerinde yüklenen eklentinin klasörü kullanıcının pazar kaynağıdır: asla taşınmaz (#403).
    if not record.folder and folder.is_dir() and record.kind != "inline":
        orphan(folder, root)
    plugin_store.update_state(lambda current: current.without_plugin(record.store_key), root)
    from ..config.plugin_scopes import write_user_enabled

    write_user_enabled(plugin_store.plugin_id(record), None)  # #376
    sweep_orphans(root)
    forget_values(storage_key(record), root)  # #391: aynı adlı öteki kurulumunkine dokunmaz
    if not keep_data:
        remove_plugin_data(storage_key(record))


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
    from ..config.plugin_scopes import write_user_enabled

    for record in load_state(root).plugins:  # Claude: her eklenti user ayarında false (#376)
        if record.name in closed:
            write_user_enabled(plugin_store.plugin_id(record), False)
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
    """Kullanımdan kalktı (#392): Claude'da karma kilidi yok; yalnız karma kaydını yeniler."""
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
        version=resolve_version(report.layout.manifest.version, "", record.commit),
        exec_approved=report.layout.is_executable,
    )
    plugin_store.update_state(lambda current: current.with_plugin(updated), root)
    return updated


# --- Pazar yerleri ------------------------------------------------------------ #


def read_marketplace(folder: Path, *, source: str = "") -> Marketplace:
    """Pazar klasörünün bildirimini ya da doğrudan verilen `.json` dosyasını (#395) oku.

    `source` kayıtlı kaynaktır: resmî pazar adları yalnız Anthropic deposundan kabul (#411).
    """
    if folder.is_file():
        try:
            raw = json.loads(folder.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise PluginError(f"{folder.name}: okunamadı: {error}") from error
        return parse_marketplace(raw, where=folder.name, source=source)
    for relative in MARKETPLACE_PATHS:
        path = folder / relative
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise PluginError(f"{relative}: okunamadı: {error}") from error
            return parse_marketplace(raw, where=relative, source=source)
    raise PluginError(ERR_MARKET_FILE.format(path=folder))


def add_marketplace(
    spec: str, *, base: Path | None = None, sparse: tuple[str, ...] = ()
) -> MarketplaceRecord:
    """Yerel klasör/.json dosyası, git deposu (`--sparse` ile seyrek) ya da marketplace.json
    adresini (url türü) pazar olarak kaydet (#395, #381)."""
    from .plugin_market_fetch import ERR_SPARSE
    from .plugin_market_source import KIND_GIT, KIND_URL, parse_market_source

    root = base or plugins_dir()
    source = parse_market_source(spec)
    if sparse and source.kind != KIND_GIT:
        raise PluginError(ERR_SPARSE)
    if source.kind not in (KIND_GIT, KIND_URL):
        market = read_marketplace(Path(source.location))
        _check_market_name(market.name, source.location, root)
        record = MarketplaceRecord(
            market.name, source.location, source.kind, source.location, time.time()
        )
    else:
        destination = fetch_market(source.kind, source.location, source.ref, sparse, root)
        record = MarketplaceRecord(
            destination.name,
            source.record_source,
            source.kind,
            str(destination),
            time.time(),
            sparse,
        )
    plugin_store.update_state(lambda current: current.with_marketplace(record), root)
    return record


def fetch_market(
    kind: str, url: str, ref: str, sparse: tuple[str, ...], root: Path, *, expected: str = ""
) -> Path:
    """Git ya da url pazarını çalışma alanına çek, adını doğrula ve `.pazarlar/<ad>`'a taşı."""
    from .plugin_market_fetch import clone_user_source, download_marketplace
    from .plugin_market_source import KIND_URL

    with _workspace(root) as workspace:
        clone = workspace / "pazar"
        if kind == KIND_URL:
            download_marketplace(url, clone)
        elif sparse or not url.startswith("https://"):
            clone_user_source(url, clone, ref=ref, sparse=sparse)  # SSH/http/seyrek (#395)
        else:
            try:
                _clone(url, clone, ref=ref)
            except PrivateUrlError:
                # Kullanıcının verdiği iç ağ/kimlikli adres: Claude gibi yerel git ile (#395).
                shutil.rmtree(clone, ignore_errors=True)
                clone_user_source(url, clone, ref=ref)
        market = read_marketplace(clone, source=url)
        if expected and market.name != expected:
            from .plugin_update import ERR_MARKET_RENAMED

            raise PluginError(ERR_MARKET_RENAMED.format(old=expected, new=market.name))
        if not expected:
            _check_market_name(market.name, f"{url}#{ref}" if ref else url, root)
        destination = markets_dir(root) / market.name
        shutil.rmtree(destination, ignore_errors=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(clone), destination)
    return destination


def _check_market_name(name: str, source: str, root: Path) -> None:
    """Ölçüldü (31 Ekim): aynı adlı başka kaynaklı pazar eskisinin yerine sessizce geçiyor,
    `ad@pazar` kurulumları yeni (belki saldırgan) depoya gidiyordu. Aynı kaynak = yenileme."""
    existing = load_state(root).marketplace(name)
    if existing is not None and existing.source != source:
        raise PluginError(ERR_MARKET_TAKEN.format(name=name, source=existing.source))


def remove_marketplace(name: str, *, base: Path | None = None) -> tuple[str, ...]:
    """Pazarı ve ondan kurulan BÜTÜN eklentileri (verileriyle) kaldır (Claude, #396).

    Bir eklenti kaldırılamazsa ötekiler yine kaldırılır, pazar kaydı kalır ve hata verilir.
    """
    from .plugin_toggle import plugins_from_marketplace

    root = base or plugins_dir()
    state = load_state(root)
    record = state.marketplace(name)
    if record is None:
        raise PluginError(ERR_NO_MARKET.format(name=name))
    removed = plugins_from_marketplace(name, root)
    failed: list[str] = []
    for plugin in removed:
        try:
            uninstall_plugin(f"{plugin}@{name}", base=root, everywhere=True)
        except PluginError as error:
            failed.append(f"{plugin}: {error}")
    if failed:
        # Pazar kaydı kalır: yeniden denendiğinde yalnız kalan eklentiler kaldırılır.
        raise PluginError(ERR_MARKET_PARTIAL.format(name=name, errors="; ".join(failed)))
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
            market = read_marketplace(Path(record.path), source=record.source)
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
