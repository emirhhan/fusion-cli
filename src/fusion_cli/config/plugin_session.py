"""Oturumluk eklentiler: `--plugin-dir <yol>` ve `CLAUDE_CODE_PLUGIN_DIRS` (Claude Code, #401).

Claude: `--plugin-dir` eklentiyi kurmadan yalnız o oturum için `<ad>@inline` olarak yükler;
`.claude-plugin/plugin.json` içeren klasörü, ya da böyle çocuk klasörleri olan bir eklenti
klasörünü kabul eder. Aynı adlı kurulu eklenti o oturumda atlanır, oturumluk kopya yüklenir.
Kullanıcı yolu açıkça verdiği için kanca/MCP onayı verilmiş sayılır (Claude'daki gibi; güvenlik
davranışı değişti). `.zip` arşivi önbelleğe açılarak yüklenir; `--plugin-url` .zip'i indirir
(`plugin_archive`). `defaultEnabled: false` ya da ayarlardaki `"<ad>@inline": false` oturumluk
eklentiyi kapatır.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from pathlib import Path

from ..core.plugins import PluginError
from .plugin_scan import scan_plugin
from .plugin_store import STATUS_ACTIVE, InstalledPlugin, PluginRecord

_LOG = logging.getLogger(__name__)

SESSION_ENV = "CLAUDE_CODE_PLUGIN_DIRS"
INLINE_MARKETPLACE = "inline"
SESSION_SCOPE = "session"
SESSION_HEADING = "Session-only plugins (--plugin-dir / --plugin-url):"
_MANIFEST = Path(".claude-plugin") / "plugin.json"

WARN_ZIP = "--plugin-dir: arşiv yüklenmedi: {error}"
WARN_URL = "--plugin-url: yüklenmedi: {error}"
WARN_MISSING = "--plugin-dir: klasör bulunamadı, atlandı: {path}"
WARN_BROKEN = "--plugin-dir: '{path}' yüklenmedi: {error}"


def add_session_dirs(paths: Iterable[Path]) -> None:
    """`--plugin-dir` yollarını ortam değişkenine ekle (alt komutlar ve alt süreçler görür)."""
    given = [str(Path(p).expanduser().resolve()) for p in paths]
    if not given:
        return
    current = [p for p in os.environ.get(SESSION_ENV, "").split(os.pathsep) if p]
    merged = [*current, *(p for p in given if p not in current)]
    os.environ[SESSION_ENV] = os.pathsep.join(merged)


def add_session_urls(urls: Iterable[str]) -> None:
    """`--plugin-url`: her .zip'i indirip açar ve oturumluk yollara ekler (hata: uyarı)."""
    from .plugin_archive import fetch_plugin_url

    folders: list[Path] = []
    for url in urls:
        try:
            folders.append(fetch_plugin_url(url))
        except PluginError as error:
            _LOG.warning(WARN_URL.format(error=error))
    add_session_dirs(folders)


def session_dirs() -> tuple[Path, ...]:
    raw = os.environ.get(SESSION_ENV, "")
    return tuple(Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip())


def _plugin_folders(path: Path) -> list[Path]:
    if path.suffix.lower() == ".zip" and path.is_file():
        from .plugin_archive import extract_plugin_zip

        try:
            return _plugin_folders(extract_plugin_zip(path))
        except PluginError as error:
            _LOG.warning(WARN_ZIP.format(error=error))
            return []
    if not path.is_dir():
        _LOG.warning(WARN_MISSING.format(path=path))
        return []
    if (path / _MANIFEST).is_file():
        return [path]
    children = sorted(c for c in path.iterdir() if c.is_dir() and (c / _MANIFEST).is_file())
    return children or [path]


def session_plugins() -> tuple[InstalledPlugin, ...]:
    """Oturumluk eklentiler (sıra: verilen yollar; aynı ad ikinci kez yüklenmez)."""
    found: list[InstalledPlugin] = []
    names: set[str] = set()
    for path in session_dirs():
        for folder in _plugin_folders(path):
            try:
                layout = scan_plugin(folder.resolve())
            except (PluginError, OSError) as error:
                _LOG.warning(WARN_BROKEN.format(path=folder, error=error))
                continue
            if layout.name in names:
                continue
            names.add(layout.name)
            record = PluginRecord(
                name=layout.name,
                version=layout.manifest.version,
                source=str(folder.resolve()),
                kind=INLINE_MARKETPLACE,
                marketplace=INLINE_MARKETPLACE,
                exec_approved=True,
            )
            found.append(InstalledPlugin(record, layout, STATUS_ACTIVE))
    return tuple(found)


def session_enabled(item: InstalledPlugin, root: Path) -> bool:
    """Claude: oturumluk eklenti açıktır; manifest `defaultEnabled: false` ya da bir ayar
    dosyasındaki `"<ad>@inline": false` kapatır (kapalı kopya gölgelemez)."""
    from .claude_plugins import enabled_map
    from .plugin_scopes import resolve_enabled

    if item.layout is None:
        return False
    ident = f"{item.record.name}@{INLINE_MARKETPLACE}"
    user = enabled_map(Path.home()).get(ident, item.layout.manifest.default_enabled)
    return resolve_enabled(ident, ident, user, root).enabled


def session_root_of(path: Path) -> Path | None:
    """`path` bir oturumluk eklentinin içindeyse o eklentinin kökü."""
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for item in session_plugins():
        root = item.layout.root.resolve() if item.layout is not None else None
        if root is not None and resolved.is_relative_to(root):
            return root
    return None
