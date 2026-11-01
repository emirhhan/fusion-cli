"""Oturumluk eklenti arşivleri: `--plugin-dir <x.zip>` ve `--plugin-url <adres>` (#401).

Claude Code (`claude --help`, 2.1.287): `--plugin-dir` "Load a plugin from a directory or .zip
for this session only"; `--plugin-url` "Fetch a plugin .zip from a URL for this session only"
(ikisi de tekrarlanabilir). Fusion arşivi içerik karmasıyla adlanan önbellek klasörüne açar
(`<veri>/eklentiler/.gecici/oturum/<karma>/`); aynı arşiv yeniden açılmaz.

Güvenli açma: mutlak yol, `..`, sembolik bağ reddedilir; Claude'un kopyalama sınırı (20.000
girdi / 256 MiB) aşılırsa arşiv yüklenmez. URL yalnız http(s); indirme de 256 MiB ile sınırlı.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from ..core.plugins import PluginError
from .paths import user_data_dir

MAX_MEMBERS = 20_000
MAX_BYTES = 256 * 1024 * 1024
FETCH_TIMEOUT_S = 60.0
_MANIFEST = Path(".claude-plugin") / "plugin.json"

ERR_ZIP = "{path}: geçerli bir .zip arşivi değil"
ERR_MEMBER = "{path}: arşivde güvensiz girdi: {name!r}"
ERR_LIMIT = "{path}: arşiv sınırı aşıldı ({members} girdi / {size} bayt)"
ERR_URL = "--plugin-url yalnız http(s) adresi kabul eder: {url}"
ERR_FETCH = "--plugin-url indirilemedi ({url}): {error}"


def cache_root() -> Path:
    return user_data_dir() / "eklentiler" / ".gecici" / "oturum"


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def _check_members(archive: zipfile.ZipFile, path: Path) -> None:
    infos = archive.infolist()
    total = sum(info.file_size for info in infos)
    if len(infos) > MAX_MEMBERS or total > MAX_BYTES:
        raise PluginError(ERR_LIMIT.format(path=path, members=len(infos), size=total))
    for info in infos:
        name = PurePosixPath(info.filename.replace("\\", "/"))
        mode = info.external_attr >> 16
        if name.is_absolute() or ".." in name.parts or stat.S_ISLNK(mode):
            raise PluginError(ERR_MEMBER.format(path=path, name=info.filename))


def _plugin_root(folder: Path) -> Path:
    """Arşiv tek üst klasör içeriyorsa (ör. `rapor/.claude-plugin/…`) o klasör."""
    if (folder / _MANIFEST).is_file():
        return folder
    children = [c for c in folder.iterdir() if not c.name.startswith("__MACOSX")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return folder


def extract_plugin_zip(path: Path) -> Path:
    """Arşivi önbelleğe aç (karma aynıysa yeniden açmadan) ve eklenti kökünü döndür."""
    try:
        destination = cache_root() / _digest(path)[:24]
        if destination.is_dir():
            return _plugin_root(destination)
        with zipfile.ZipFile(path) as archive:
            _check_members(archive, path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".acilan-", dir=destination.parent))
            try:
                archive.extractall(staging)
                staging.replace(destination)
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
    except (OSError, zipfile.BadZipFile) as error:
        raise PluginError(ERR_ZIP.format(path=path)) from error
    return _plugin_root(destination)


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "fusion-cli"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_S) as response:
        read = 0
        with target.open("wb") as handle:
            while block := response.read(1 << 20):
                read += len(block)
                if read > MAX_BYTES:
                    raise PluginError(ERR_LIMIT.format(path=url, members="?", size=read))
                handle.write(block)


def fetch_plugin_url(url: str) -> Path:
    """`--plugin-url`: .zip'i indir, aç ve eklenti kökünü döndür."""
    if urlsplit(url).scheme not in ("http", "https"):
        raise PluginError(ERR_URL.format(url=url))
    cache_root().mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(suffix=".zip", dir=cache_root())
    target = Path(name)
    try:
        os.close(handle)
        try:
            _download(url, target)
        except (OSError, ValueError) as error:
            raise PluginError(ERR_FETCH.format(url=url, error=error)) from error
        return extract_plugin_zip(target)
    finally:
        target.unlink(missing_ok=True)
