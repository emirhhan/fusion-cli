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
uygular. Yerinde yüklenen (#403) eklentinin kaynak klasörüne yazılmaz: alanlar kayıtta saklanır ve
bildirim her taramada bellekte birleştirilir (`config/plugin_scan.read_manifest`).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from ..core.atomic_file import atomic_replace_text
from ..core.plugin_entry_merge import (  # noqa: F401  (eski içe aktarımlar)
    COMPONENT_KEYS,
    DISPLAY_KEYS,
    ERR_CONFLICT,
    ERR_ENTRY_HOOKS,
    merge_entry,
)
from ..core.plugins import PluginError

ERR_MANIFEST = "Plugin {name}: plugin.json okunamadı: {error}"
_MANIFEST = Path(".claude-plugin") / "plugin.json"


def apply_entry(folder: Path, fields_json: str, strict: bool, name: str) -> None:
    """Girdi alanlarını `folder` içindeki bildirime uygula (yukarıdaki kurallar)."""
    fields = parse_fields(fields_json)
    if not fields:
        return
    path = folder / _MANIFEST
    manifest = _read(path, name) if path.is_file() else None
    merged = merge_entry(manifest, fields, strict, name)
    if merged != manifest:
        _write(path, merged)


def parse_fields(fields_json: str) -> dict[str, object]:
    """Kayıttaki girdi alanları JSON metni → nesne (boş ya da nesne değilse {})."""
    if not fields_json:
        return {}
    fields = json.loads(fields_json)
    return dict(fields) if isinstance(fields, Mapping) else {}


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
