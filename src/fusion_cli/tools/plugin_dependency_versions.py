"""Bağımlılık `version` aralıklarının `<ad>--v<sürüm>` git etiketlerinden çözümü (#389).

Claude Code 2.1.287 (`installResolvedPlugin`/`resolveVersionRange`): bir bağımlılığı isteyen tüm
kurulu eklentilerin aralıkları VE'lenir; çelişirse "conflicting version requirements". Kurulu
bağımlılık aralığı karşılamıyorsa "is installed at <sürüm>, which does not satisfy". Kurulu
değilse kaynağın git deposunda (`git ls-remote --tags`; pazar içi göreli eklentide pazarın deposu)
`<ad>--v*` etiketlerinden aralığı karşılayan en yüksek sürüm seçilir ve o etiketten kurulur. Etiket
yoksa: dış git kaynağında "has no git tag satisfying" hatası; pazar içi göreli eklentide pazarın
güncel kopyası kurulur. Git dışı kaynakta kurulan sürüm aralığı karşılamazsa kurulum geri alınır.
Hatalar `failureCode: dependency_version_conflict` taşır ve bağımlı eklentinin kurulumunu geri alır.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..config.plugin_store import PluginRecord, PluginState, load_state, plugins_dir
from ..core.plugins import PluginError
from ..core.semver_range import intersect, is_valid_range, max_satisfying, parse_version, satisfies

if TYPE_CHECKING:
    from .plugin_install import _Resolved

TAG_SEPARATOR = "--v"
CODE = "dependency_version_conflict"
ERR_CONFLICT = (
    "Dependency {dep} has conflicting version requirements (no version satisfies all of: {ranges})"
)
ERR_INVALID = "Dependency {dep} has an invalid version requirement among: {ranges}"
ERR_INSTALLED = (
    "Dependency {dep} is installed at {version}, which does not satisfy: {ranges}. To look for a "
    "version in range, run `fusion plugin update {ident}`"
)
ERR_NO_TAG = "Dependency {dep} has no git tag satisfying {range}"
ERR_PINNED = (
    '"{name}" from the {market} marketplace is pinned to its listed commit ({version}), which '
    "does not satisfy {ranges} required by {dependents}."
)
LS_REMOTE_TIMEOUT_S = 60


class DependencyVersionError(PluginError):
    """Bağımlılık sürüm aralığı karşılanamadı (Claude `dependency_version_conflict`)."""

    failure_code = CODE


@dataclass(frozen=True, slots=True)
class TagPin:
    tag: str
    sha: str
    version: str


def quoted(ident: str) -> str:
    return f'"{ident}"'


def combined(ident: str, ranges: tuple[str, ...]) -> str:
    """Aralıkların kesişimi; geçersiz ya da çelişkiliyse `DependencyVersionError`."""
    shown = ", ".join(ranges)
    if not all(is_valid_range(r) for r in ranges):
        raise DependencyVersionError(ERR_INVALID.format(dep=quoted(ident), ranges=shown))
    found = intersect(ranges)
    if found is None:
        raise DependencyVersionError(ERR_CONFLICT.format(dep=quoted(ident), ranges=shown))
    return found


def check_installed(ident: str, version: str, ranges: tuple[str, ...], wanted: str) -> None:
    if wanted == "*" or satisfies(version or "0.0.0", wanted):
        return
    raise DependencyVersionError(
        ERR_INSTALLED.format(
            dep=quoted(ident),
            version=version or "an unknown version",
            ranges=", ".join(ranges),
            ident=ident,
        )
    )


def check_pinned(
    record: PluginRecord, ranges: tuple[str, ...], dependents: tuple[str, ...]
) -> None:
    """Git etiketi olmadan kurulan sürüm aralığı karşılamalı (Claude directory-pin-unsatisfied)."""
    wanted = intersect(ranges) or ""
    if wanted == "*" or satisfies(record.version or "0.0.0", wanted):
        return
    raise DependencyVersionError(
        ERR_PINNED.format(
            name=record.name,
            market=record.marketplace,
            version=f"version {record.version}" if record.version else "no version",
            ranges=", ".join(ranges),
            dependents=", ".join(quoted(d) for d in dependents),
        )
    )


def parse_tags(output: str, name: str, wanted: str) -> TagPin | None:
    """`git ls-remote --tags` çıktısından `<ad>--v<sürüm>` etiketinin aralığa uyan en yükseği."""
    prefix = f"{name}{TAG_SEPARATOR}"
    found: dict[str, TagPin] = {}
    for line in output.splitlines():
        sha, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/"):
            continue
        tag = ref.removeprefix("refs/tags/")
        peeled = tag.endswith("^{}")
        tag = tag.removesuffix("^{}")
        if not tag.startswith(prefix):
            continue
        parsed = parse_version(tag[len(prefix) :])
        if parsed is None or (not peeled and tag in found):
            continue
        found[tag] = TagPin(tag, sha.strip(), str(parsed))
    best = max_satisfying([pin.version for pin in found.values()], wanted)
    return next((pin for pin in found.values() if pin.version == best), None)


def list_remote_tags(url: str) -> str:
    """Genel https deposunun etiketleri (klon ile aynı adres denetimi)."""
    from . import plugin_install

    plugin_install._check_url(url)
    done = subprocess.run(
        ["git", "ls-remote", "--tags", url],
        capture_output=True,
        text=True,
        timeout=LS_REMOTE_TIMEOUT_S,
        check=False,
        stdin=subprocess.DEVNULL,
        env={"GIT_TERMINAL_PROMPT": "0", "PATH": _path()},
    )
    if done.returncode != 0:
        raise PluginError(f"git ls-remote {url}: {done.stderr.strip()[:200]}")
    return done.stdout


def _path() -> str:
    import os

    return os.environ.get("PATH", "")


def resolve_pin(name: str, url: str, wanted: str, *, relative: bool) -> TagPin | None:
    """Aralığa uyan etiket; yoksa göreli eklentide `None` (güncel kopya), dışta hata."""
    try:
        pin = parse_tags(list_remote_tags(url), name, wanted)
    except PluginError:
        pin = None
    if pin is None and not relative:
        raise DependencyVersionError(ERR_NO_TAG.format(dep=quoted(name), range=wanted))
    return pin


def pin_target(spec: str, base: Path | None = None) -> tuple[str, str, bool] | None:
    """Bağımlılığın etiketlerinin arandığı depo: (girdi adı, git adresi, pazar içi göreli mi).

    Git dışı kaynakta (yerel/directory pazar, archive, npm, command) `None` (#389).
    """
    from .plugin_install import _resolve

    state = load_state(base or plugins_dir())
    resolved = _resolve(spec, state)
    name = resolved.entry or spec.partition("@")[0]
    if resolved.kind == "git":
        return name, resolved.location, False
    record = state.marketplace(resolved.marketplace) if resolved.marketplace else None
    if resolved.kind == "yerel" and resolved.commit_dir and record is not None:
        return name, record.source, True
    return None


def pinned_source(resolved: _Resolved, pin: tuple[str, str], state: PluginState) -> _Resolved:
    """Kaynağı etiketle sabitle; pazar içi göreli eklenti pazar deposunun alt klasörü olur."""
    tag, sha = pin
    if resolved.kind == "git":
        return replace(resolved, ref=tag, sha=sha)
    record = state.marketplace(resolved.marketplace)
    if resolved.kind != "yerel" or not resolved.commit_dir or record is None:
        return resolved
    subdir = Path(resolved.location).resolve().relative_to(Path(record.path).resolve())
    return replace(
        resolved, kind="git", location=record.source, ref=tag, sha=sha, subdir=str(subdir)
    )


__all__ = [
    "DependencyVersionError",
    "TagPin",
    "check_installed",
    "check_pinned",
    "combined",
    "parse_tags",
    "resolve_pin",
]
