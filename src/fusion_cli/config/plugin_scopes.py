r"""Eklenti kapsamları: `enabledPlugins` user/project/local katmanları (#376).

Claude Code (https://code.claude.com/docs/en/plugins/cli-reference.md "plugin enable",
https://code.claude.com/docs/en/plugins/loading.md): açık/kapalı bilgisi settings dosyalarındaki
`enabledPlugins` (`{"ad@pazar": true|false}`) anahtarında durur; öncelik local > project > user.
`enable`/`disable` `--scope` almazsa local, project, user sırasıyla eklentiyi anan İLK kapsamı
kullanır; daha düşük öncelikli bir kapsam verilirse "installed at … scope" hatası, daha yüksek
öncelikli bir kapsam verilirse o kapsamda geçersiz kılma yazılır.

Fusion'da:
- managed = kuruluşun `managed-settings.json`'ı (macOS `/Library/Application Support/ClaudeCode`,
  Linux `/etc/claude-code`, Windows `C:\Program Files\ClaudeCode`); en yüksek önceliktir,
  oradaki değer başka kapsamda değiştirilemez (`managed_settings_override`/`plugin_policy_blocked`).
- user = Claude gibi `~/.claude/settings.json` `enabledPlugins`; kurulum/aç/kapat/kaldır oraya
  yazar (Claude 2.1.287'de ölçüldü). Anahtar yoksa Fusion kaydının `etkin` değeri geçerlidir
  (eski kurulumlar bozulmaz).
- project = `<kök>/.claude/settings.json`, local = `<kök>/.claude/settings.local.json`.
- Güvenlik: güvenilmeyen (`fusion trust` sonrası değişmiş) proje dosyasındaki `true` eklenti
  AÇMAZ; `false` her zaman uygulanır (kapatmak hiçbir şey çalıştırmaz).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.plugins import PluginError
from . import trust

_LOG = logging.getLogger(__name__)

SCOPE_MANAGED = "managed"
SCOPE_USER = "user"
SCOPE_PROJECT = "project"
SCOPE_LOCAL = "local"
#: Öncelik sırası (yüksekten düşüğe) — otomatik algılama da bu sırayla arar.
SCOPES_BY_PRECEDENCE = (SCOPE_LOCAL, SCOPE_PROJECT, SCOPE_USER)
SCOPES = (SCOPE_USER, SCOPE_PROJECT, SCOPE_LOCAL)
ENABLED_KEY = "enabledPlugins"

ERR_SCOPE = "Geçersiz kapsam: {scope}. Kullan: user, project, local"
ERR_LOWER_SCOPE = (
    'Eklenti "{name}" {declared} kapsamında kurulu, {scope} değil. '
    "--scope {declared} kullan ya da --scope'u kaldırıp otomatik algılat."
)
ERR_UNREADABLE = "Ayar dosyası okunamadı ({path}): {error}"


ERR_MANAGED_ON = 'Eklenti "{name}" kuruluşunuzun managed ayarlarıyla açık; burada kapatılamaz'
ERR_MANAGED_OFF = (
    'Eklenti "{name}" kuruluşunuzun managed ayarlarıyla kapalı; açmak için yöneticinize başvurun'
)
_MANAGED_DIRS = {
    "darwin": "/Library/Application Support/ClaudeCode",
    "win32": r"C:\Program Files\ClaudeCode",
}


class ManagedScopeError(PluginError):
    """Managed ayardaki eklenti değeri değiştirilemez (Claude `failureCode`)."""

    def __init__(self, message: str, failure_code: str) -> None:
        super().__init__(message)
        self.failure_code = failure_code


def managed_settings_file() -> Path:
    return Path(_MANAGED_DIRS.get(sys.platform, "/etc/claude-code")) / "managed-settings.json"


def user_settings_file() -> Path:
    """Kullanıcı kapsamı: `~/.claude/settings.json` (Claude ile ortak)."""
    return Path.home() / ".claude" / "settings.json"


def _bool_map(raw: object) -> dict[str, bool]:
    if not isinstance(raw, Mapping):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, bool)}


def managed_values() -> dict[str, bool]:
    return _bool_map(_read(managed_settings_file()).get(ENABLED_KEY))


def user_values() -> dict[str, bool]:
    return _bool_map(_read(user_settings_file()).get(ENABLED_KEY))


def check_managed(plugin_id: str, name: str, enabled: bool) -> None:
    """Managed değeri istenenin tersiyse hata (Claude: kapsam fark etmeksizin)."""
    value = _lookup(managed_values(), plugin_id, name)
    if value is None or value == enabled:
        return
    if value:
        raise ManagedScopeError(ERR_MANAGED_ON.format(name=name), "managed_settings_override")
    raise ManagedScopeError(ERR_MANAGED_OFF.format(name=name), "plugin_policy_blocked")


def check_scope(scope: str) -> str:
    if scope not in SCOPES:
        raise PluginError(ERR_SCOPE.format(scope=scope))
    return scope


def settings_path(scope: str, root: Path) -> Path:
    name = "settings.local.json" if scope == SCOPE_LOCAL else "settings.json"
    return root / ".claude" / name


def _is_trusted(scope: str, root: Path) -> bool:
    if scope == SCOPE_LOCAL:
        return trust.is_permissions_trusted(root)
    return trust.is_project_settings_trusted(root)


def _read(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        _LOG.warning("ayar dosyası okunamadı (%s): %s", path, error)
        return {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def is_scope_trusted(scope: str, root: Path) -> bool:
    """project/local dosyası güvenilir mi (local izin, project ayar karmasıyla)."""
    return _is_trusted(scope, root)


def read_settings(path: Path) -> dict[str, object]:
    """Ayar dosyası nesnesi; yoksa ya da bozuksa boş (uyarı günlüğe)."""
    return _read(path)


def scope_values(scope: str, root: Path) -> dict[str, bool]:
    """Kapsam dosyasındaki `enabledPlugins` (yalnız bool değerler)."""
    raw = _read(settings_path(scope, root)).get(ENABLED_KEY)
    if not isinstance(raw, Mapping):
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, bool)}


def _lookup(values: Mapping[str, bool], plugin_id: str, name: str) -> bool | None:
    if plugin_id in values:
        return values[plugin_id]
    return values.get(name)


@dataclass(frozen=True, slots=True)
class ScopeDecision:
    """Eklentinin etkin değeri ve onu belirleyen kapsam."""

    enabled: bool
    scope: str


def resolve_enabled(
    plugin_id: str, name: str, user_value: bool, root: Path, *, upto: str = SCOPE_LOCAL
) -> ScopeDecision:
    """managed > local > project > user; `upto` daha üst kapsamları yok sayar (managed hariç)."""
    managed = _lookup(managed_values(), plugin_id, name)
    if managed is not None:
        return ScopeDecision(managed, SCOPE_MANAGED)
    order = SCOPES_BY_PRECEDENCE[SCOPES_BY_PRECEDENCE.index(upto) :]
    for scope in order:
        if scope == SCOPE_USER:
            break
        value = _lookup(scope_values(scope, root), plugin_id, name)
        if value is None:
            continue
        if value and not _is_trusted(scope, root):
            _LOG.warning(
                "'%s' %s kapsamında açık ama dosya güvenilmiyor (fusion trust); yok sayıldı",
                plugin_id,
                scope,
            )
            continue
        return ScopeDecision(value, scope)
    if "@" in plugin_id:
        stored = user_values().get(plugin_id)
        if stored is not None:
            return ScopeDecision(stored, SCOPE_USER)
    return ScopeDecision(user_value, SCOPE_USER)


def write_user_enabled(plugin_id: str, value: bool | None) -> Path | None:
    """`~/.claude/settings.json` `enabledPlugins[ad@pazar]` (None: sil); pazarsız yazılmaz."""
    if "@" not in plugin_id:
        return None

    def change(raw: dict[str, object]) -> dict[str, object]:
        current = _bool_map(raw.get(ENABLED_KEY))
        if value is None:
            return {**raw, ENABLED_KEY: {k: v for k, v in current.items() if k != plugin_id}}
        return {**raw, ENABLED_KEY: {**current, plugin_id: value}}

    if value is None and plugin_id not in user_values():
        return None
    return update_user_settings(change)


def update_user_settings(change: Callable[[dict[str, object]], dict[str, object]]) -> Path:
    """Kullanıcı ayar dosyasını kilit altında yeniden yaz (diğer anahtarlar korunur)."""
    from .writer import config_lock

    path = user_settings_file()
    with config_lock(path):
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError) as error:
            raise PluginError(ERR_UNREADABLE.format(path=path, error=error)) from error
        if not isinstance(raw, Mapping):
            raise PluginError(ERR_UNREADABLE.format(path=path, error="nesne değil"))
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace_text(
            path, json.dumps(change(dict(raw)), ensure_ascii=False, indent=2) + "\n"
        )
    return path


def declared_scope(plugin_id: str, name: str, root: Path) -> str:
    """`--scope` verilmezse: local, project, user sırasıyla eklentiyi anan ilk kapsam."""
    for scope in (SCOPE_LOCAL, SCOPE_PROJECT):
        if _lookup(scope_values(scope, root), plugin_id, name) is not None:
            return scope
    return SCOPE_USER


def target_scope(plugin_id: str, name: str, root: Path, requested: str) -> str:
    """Hedef kapsam: verilmediyse algılanır; ilan edilenden düşük öncelikliyse hata."""
    declared = declared_scope(plugin_id, name, root)
    if not requested:
        return declared
    check_scope(requested)
    rank = SCOPES_BY_PRECEDENCE.index
    if rank(requested) > rank(declared):
        raise PluginError(ERR_LOWER_SCOPE.format(name=name, declared=declared, scope=requested))
    return requested


def write_enabled(scope: str, plugin_id: str, name: str, value: bool | None, root: Path) -> Path:
    """project/local dosyasına `enabledPlugins[ad@pazar] = value` yaz (diğer anahtarlar korunur);
    `value=None` anahtarı siler.

    Dosya yazılmadan önce güvenilirse (ya da yoksa) yeni içeriğin karması tazelenir; güvensiz
    dosya bu yazımla güvenilir OLMAZ.
    """
    from .writer import config_lock

    path = settings_path(scope, root)
    with config_lock(path):
        trusted_before = _is_trusted(scope, root)
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError) as error:
            raise PluginError(ERR_UNREADABLE.format(path=path, error=error)) from error
        if not isinstance(raw, Mapping):
            raise PluginError(ERR_UNREADABLE.format(path=path, error="nesne değil"))
        current = raw.get(ENABLED_KEY)
        enabled = dict(current) if isinstance(current, Mapping) else {}
        key = plugin_id if plugin_id in enabled or name not in enabled else name
        if value is None:  # `uninstall --scope` (#408): anahtar kapsamdan silinir
            changed = {k: v for k, v in enabled.items() if k not in (plugin_id, name)}
        else:
            changed = {**enabled, key: value}
        updated = {**raw, ENABLED_KEY: changed}
        atomic_replace_text(path, json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
        if trusted_before:
            _refresh_digest(scope, root)
    return path


def update_settings(
    scope: str, root: Path, change: Callable[[dict[str, object]], dict[str, object]]
) -> Path:
    """project/local dosyasının üst düzey nesnesini `change` ile yeniden yaz (kilit + güven
    karması `write_enabled` ile aynı kurallarla); `extraKnownMarketplaces` için (#381)."""
    from .writer import config_lock

    path = settings_path(scope, root)
    with config_lock(path):
        trusted_before = _is_trusted(scope, root)
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError) as error:
            raise PluginError(ERR_UNREADABLE.format(path=path, error=error)) from error
        if not isinstance(raw, Mapping):
            raise PluginError(ERR_UNREADABLE.format(path=path, error="nesne değil"))
        updated = change(dict(raw))
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace_text(path, json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
        if trusted_before:
            _refresh_digest(scope, root)
    return path


def _refresh_digest(scope: str, root: Path) -> None:
    if scope == SCOPE_LOCAL:
        trust.record_permissions_digest(root)
    else:
        trust.record_project_settings_digest(root)


def settings_signature(root: Path) -> tuple[int, ...]:
    """project/local/user/managed dosyalarının mtime_ns'leri: değişince katalog yenilenir."""
    found: list[int] = []
    paths = [settings_path(scope, root) for scope in (SCOPE_PROJECT, SCOPE_LOCAL)]
    for path in (*paths, user_settings_file(), managed_settings_file()):
        try:
            found.append(path.stat().st_mtime_ns)
        except OSError:
            found.append(0)
    return tuple(found)
