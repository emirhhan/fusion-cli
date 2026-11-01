"""Eklenti kapsamları: `enabledPlugins` user/project/local katmanları (#376).

Claude Code (https://code.claude.com/docs/en/plugins/cli-reference.md "plugin enable",
https://code.claude.com/docs/en/plugins/loading.md): açık/kapalı bilgisi settings dosyalarındaki
`enabledPlugins` (`{"ad@pazar": true|false}`) anahtarında durur; öncelik local > project > user.
`enable`/`disable` `--scope` almazsa local, project, user sırasıyla eklentiyi anan İLK kapsamı
kullanır; daha düşük öncelikli bir kapsam verilirse "installed at … scope" hatası, daha yüksek
öncelikli bir kapsam verilirse o kapsamda geçersiz kılma yazılır.

Fusion'da:
- user kapsamı Fusion'ın kendi kaydıdır (`<veri>/eklentiler/kayit.json` → `etkin`); Claude'un
  `~/.claude/settings.json`'ına Fusion'ın kurduğu eklentiler yazılmaz (Claude orada bilmediği
  kimlik görür).
- project = `<kök>/.claude/settings.json`, local = `<kök>/.claude/settings.local.json`.
- Güvenlik: güvenilmeyen (`fusion trust` sonrası değişmiş) proje dosyasındaki `true` eklenti
  AÇMAZ; `false` her zaman uygulanır (kapatmak hiçbir şey çalıştırmaz).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.plugins import PluginError
from . import trust

_LOG = logging.getLogger(__name__)

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
    """local > project > user; `upto` daha üst kapsamları yok sayar (hedef kapsam denetimi)."""
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
    return ScopeDecision(user_value, SCOPE_USER)


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


def write_enabled(
    scope: str, plugin_id: str, name: str, value: bool | None, root: Path
) -> Path:
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


def _refresh_digest(scope: str, root: Path) -> None:
    if scope == SCOPE_LOCAL:
        trust.record_permissions_digest(root)
    else:
        trust.record_project_settings_digest(root)


def settings_signature(root: Path) -> tuple[int, ...]:
    """project/local dosyalarının mtime_ns'leri: değişince katalog önbelleği yenilenir."""
    found: list[int] = []
    for scope in (SCOPE_PROJECT, SCOPE_LOCAL):
        try:
            found.append(settings_path(scope, root).stat().st_mtime_ns)
        except OSError:
            found.append(0)
    return tuple(found)
