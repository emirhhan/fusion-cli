"""Pazar girdisinin bildirim alanlarını bildirimle birleştir — saf işlev (Claude Code, #398).

Kurallar `tools/plugin_entry.py` başında; bu modül dosyaya yazmaz (yalnız stdlib + core).
"""

from __future__ import annotations

from collections.abc import Mapping

from .plugins import PluginError

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


def merge_entry(
    manifest: Mapping[str, object] | None, fields: Mapping[str, object], strict: bool, name: str
) -> dict[str, object]:
    """Bildirim (yoksa None) + girdi alanları → etkin bildirim. Çakışmada `PluginError`."""
    if "hooks" in fields and not isinstance(fields["hooks"], Mapping):
        raise PluginError(ERR_ENTRY_HOOKS.format(name=name))
    if manifest is None:
        return {"name": name, **fields}
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
    return merged


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
