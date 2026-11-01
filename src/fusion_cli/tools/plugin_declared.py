"""Ayarlarda bildirilen pazarlar: `extraKnownMarketplaces` (`additionalMarketplaces`, #376).

Claude Code (https://code.claude.com/docs/en/settings-reference.md "extraKnownMarketplaces",
https://code.claude.com/docs/en/plugins/loading.md "Plugins and marketplaces that aren't on disk"):
- Girdi `{"ad": {"source": {...}, "autoUpdate": bool}}`; Claude bilmediği her pazarı kaydeder.
- Deponun `.claude/settings.json`/`.claude/settings.local.json` girdileri yalnız klasöre
  güvenildikten sonra uygulanır; güvenilmeyen klasörde sessizce yok sayılır.
- Aynı adlı girdide en yüksek öncelikli dosyanınki (local > project) BÜTÜNÜYLE geçerlidir.
- Aynı dosyada iki yazım da varsa asıl anahtar (`extraKnownMarketplaces`) kazanır.

Fusion'da: kaynak türleri github/git/directory/file `marketplace add` kaynağına çevrilir; `url` ve
`settings` türleri (Fusion'da yok, #395) uyarıyla atlanır. Claude bildirilen pazarı oturum
başladıktan sonra arka planda kaydeder; Fusion bunu REPL açılışında arka planda ve
`plugin install`/`plugin marketplace list`/`plugin list` öncesinde yapar. Kullanıcı kapsamı
(Fusion'ın kendi kaydı) ve managed kapsam bu modülde okunmaz.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..config import plugin_scopes
from ..config.plugin_store import load_state, plugins_dir, plugins_disabled_by_environment
from ..core.plugins import PluginError

_LOG = logging.getLogger(__name__)

DECLARED_KEY = "extraKnownMarketplaces"
ALIAS_KEY = "additionalMarketplaces"
#: Düşükten yükseğe: sonraki dosya aynı adlı girdiyi bütünüyle ezer.
_SCOPES = (plugin_scopes.SCOPE_PROJECT, plugin_scopes.SCOPE_LOCAL)
_GIT_KINDS = frozenset({"github", "git"})
_PATH_KINDS = frozenset({"directory", "file"})


@dataclass(frozen=True, slots=True)
class DeclaredMarket:
    """Ayar dosyasında bildirilen pazar: `spec` `marketplace add` kaynağı biçimindedir."""

    name: str
    spec: str
    scope: str
    auto_update: bool | None = None


def source_spec(source: object, root: Path) -> str | None:
    """Claude kaynak nesnesini Fusion `marketplace add` kaynağına çevir; desteklenmezse None."""
    if not isinstance(source, Mapping):
        return None
    kind = source.get("source")
    if kind in _GIT_KINDS:
        field = "repo" if kind == "github" else "url"
        location = source.get(field)
        if not isinstance(location, str) or not location.strip():
            return None
        ref = source.get("ref")
        return f"{location.strip()}#{ref}" if isinstance(ref, str) and ref else location.strip()
    if kind in _PATH_KINDS:
        path = source.get("path")
        if not isinstance(path, str) or not path.strip():
            return None
        resolved = Path(path).expanduser()
        return str(resolved if resolved.is_absolute() else (root / resolved).resolve())
    return None


def _block(raw: Mapping[str, object]) -> Mapping[str, object]:
    for key in (DECLARED_KEY, ALIAS_KEY):
        value = raw.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _entry(name: str, value: object, scope: str, root: Path) -> DeclaredMarket | None:
    if not isinstance(value, Mapping):
        _LOG.warning("bildirilen pazar '%s' (%s) nesne değil; atlandı", name, scope)
        return None
    spec = source_spec(value.get("source"), root)
    if spec is None:
        _LOG.warning(
            "bildirilen pazar '%s' (%s): kaynak türü desteklenmiyor ya da eksik; atlandı",
            name,
            scope,
        )
        return None
    auto = value.get("autoUpdate")
    return DeclaredMarket(name, spec, scope, auto if isinstance(auto, bool) else None)


def declared_marketplaces(root: Path) -> dict[str, DeclaredMarket]:
    """Güvenilen project/local dosyalarındaki bildirimler (aynı ad: üst kapsam bütünüyle)."""
    found: dict[str, DeclaredMarket] = {}
    for scope in _SCOPES:
        path = plugin_scopes.settings_path(scope, root)
        if not path.is_file() or not plugin_scopes.is_scope_trusted(scope, root):
            continue
        for name, value in _block(plugin_scopes.read_settings(path)).items():
            item = _entry(str(name), value, scope, root)
            if item is not None:
                found[item.name] = item
    return found


def sync_declared(root: Path | None = None, *, base: Path | None = None) -> tuple[str, ...]:
    """Bilinmeyen bildirilmiş pazarları kaydet; eklenenlerin adları. Hata diğerlerini durdurmaz."""
    from .plugin_install import add_marketplace

    project = root or Path.cwd()
    store = base or plugins_dir()
    records = load_state(store).marketplaces
    known = {record.name for record in records}
    # Bildirim adı kaynaktaki pazarın adından farklıysa ad hiç eşleşmez: kaynağa da bakılır,
    # yoksa her açılışta (git'te yeniden klonla) aynı pazar yeniden eklenmeye çalışılırdı.
    sources = {record.source for record in records}
    added: list[str] = []
    for name, item in declared_marketplaces(project).items():
        if name in known or _spec_source(item.spec) in sources:
            continue
        try:
            record = add_marketplace(item.spec, base=store)
        except PluginError as error:
            _LOG.warning("bildirilen pazar '%s' eklenemedi: %s", name, error)
            continue
        if record.name != name:
            _LOG.warning("bildirilen pazar '%s' kaynağındaki pazarın adı '%s'", name, record.name)
        known.add(record.name)
        added.append(record.name)
    return tuple(added)


def _spec_source(spec: str) -> str:
    """Bildirilen kaynağın kayıtta saklanacak biçimi (`add_marketplace` ile aynı); bozuksa boş."""
    from .plugin_market_source import KIND_GIT, parse_market_source

    try:
        source = parse_market_source(spec)
    except PluginError:
        return ""
    return source.record_source if source.kind == KIND_GIT else source.location


def sync_quietly(root: Path | None = None) -> tuple[str, ...]:
    """CLI komutlarından önce: beklenmeyen hata komutu bozmasın (günlüğe yazılır)."""
    try:
        return sync_declared(root)
    except (OSError, PluginError) as error:
        _LOG.warning("bildirilen pazarlar eşitlenemedi: %s", error)
        return ()


def start_background_sync(root: Path) -> threading.Thread | None:
    """Oturum açılışında arka planda eşitle (Claude: oturum başladıktan sonra arka planda)."""
    if plugins_disabled_by_environment() or not declared_marketplaces(root):
        return None
    worker = threading.Thread(
        target=sync_quietly, args=(root,), name="fusion-declared-markets", daemon=True
    )
    worker.start()
    return worker
