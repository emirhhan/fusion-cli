"""Pazar girdisinin bildirim alanlarını çekilen eklentiye uygula (Claude Code, #398).

Belge (code.claude.com/docs/en/plugins/marketplace-reference.md, "How an entry combines with
plugin.json", "Strict mode"):
- plugin.json yoksa girdi bildirimdir (strict ne olursa olsun).
- plugin.json varsa o otoritedir. strict:true (varsayılan) iken girdinin bileşen alanları
  (`commands`, `agents`, `skills`, `hooks`, `outputStyles`, `themes`) ona eklenir; `hooks`'un
  eşleyicileri bildirimdekileri olay başına değiştirir. strict:false iken bileşen alanı taşıyan
  girdi çakışmadır ve eklenti yüklenmez. Girdinin `defaultEnabled`'ı ve görünen alanları
  (`displayName`, `description`, `author`, …) bildirimdekinin önüne geçer; `version`'da plugin.json
  kazanır; girdinin `mcpServers`/`lspServers`/`userConfig`/`channels`'ı uygulanmaz.
- Girdide `hooks` dosya yolu ya da dizi ise "not yet supported in a marketplace entry" hatası.

Fusion bunu kopyalanan eklentinin önbellek kopyasındaki `.claude-plugin/plugin.json`'a yazarak
uygular; yerinde yüklenen (#403) eklentinin kaynak klasörüne yazılmaz.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.plugins import PluginError

COMPONENT_KEYS = ("commands", "agents", "skills", "hooks", "outputStyles", "themes")
DISPLAY_KEYS = (
    "displayName",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "defaultEnabled",
)
ERR_CONFLICT = (
    "Plugin {name} has conflicting manifests: both plugin.json and marketplace entry specify "
    "components"
)
ERR_ENTRY_HOOKS = (
    "Plugin {name}: hooks as a file path or array are not yet supported in a marketplace entry; "
    "girdide kancaları satır içi nesne olarak yaz"
)
ERR_MANIFEST = "Plugin {name}: plugin.json okunamadı: {error}"
_MANIFEST = Path(".claude-plugin") / "plugin.json"


def apply_entry(folder: Path, fields_json: str, strict: bool, name: str) -> None:
    """Girdi alanlarını `folder` içindeki bildirime uygula (yukarıdaki kurallar)."""
    if not fields_json:
        return
    fields = json.loads(fields_json)
    if not isinstance(fields, Mapping) or not fields:
        return
    if "hooks" in fields and not isinstance(fields["hooks"], Mapping):
        raise PluginError(ERR_ENTRY_HOOKS.format(name=name))
    path = folder / _MANIFEST
    if not path.is_file():
        _write(path, {"name": name, **fields})
        return
    manifest = _read(path, name)
    components = {k: fields[k] for k in COMPONENT_KEYS if k in fields}
    if components and not strict:
        raise PluginError(ERR_CONFLICT.format(name=name))
    merged = dict(manifest)
    for key, value in components.items():
        merged[key] = (
            _merge_hooks(manifest.get(key), value, name)
            if key == "hooks"
            else (_append(manifest.get(key), value))
        )
    merged.update({k: fields[k] for k in DISPLAY_KEYS if k in fields})
    if merged != manifest:
        _write(path, merged)


def _read(path: Path, name: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PluginError(ERR_MANIFEST.format(name=name, error=error)) from error
    if not isinstance(raw, Mapping):
        raise PluginError(ERR_MANIFEST.format(name=name, error="JSON nesnesi değil"))
    return dict(raw)


def _write(path: Path, data: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_replace_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def _append(current: object, extra: object) -> object:
    """Bildirimde alan yoksa girdininki; varsa bildirimin değerlerine girdininkiler eklenir."""
    if current is None:
        return extra
    return [*_as_list(current), *(v for v in _as_list(extra) if v not in _as_list(current))]


def _merge_hooks(current: object, extra: object, name: str) -> object:
    """Girdi kancaları (olay → eşleyici dizisi) bildirimdekileri olay başına değiştirir."""
    if not isinstance(extra, Mapping):
        raise PluginError(ERR_ENTRY_HOOKS.format(name=name))
    events = (
        dict(extra.get("hooks", extra)) if isinstance(extra.get("hooks"), Mapping) else dict(extra)
    )
    if isinstance(current, Mapping):
        inner = current.get("hooks")
        base = dict(inner) if isinstance(inner, Mapping) else dict(current)
        return {"hooks": {**base, **events}}
    if current is None:
        return {"hooks": events}
    # Bildirimde dosya yolu/dizi: girdinin satır içi bloğu karışık diziye eklenir (#385).
    return [*_as_list(current), {"hooks": events}]
