"""Eklentideki `.mcpb`/`.dxt` MCP paketleri (Claude Code plugins-reference "mcpServers", #400).

Claude Code: `mcpServers` `./sunucu.mcpb` (eklenti köküne göreli) ya da `.mcpb`/`.dxt` ile biten
bir adres olabilir; paket açılır, `manifest.json`'daki `server.mcp_config` (`command`, `args`,
`env`) sunucu tanımıdır ve ad paketin `name`'idir. `${__dirname}` açılan klasöre, `${HOME}`,
`${DESKTOP}`, `${DOCUMENTS}`, `${DOWNLOADS}` kullanıcı klasörlerine, `${/}`/`${pathSeparator}`
yol ayırıcısına, `${user_config.KEY}` paketin `user_config` değerine çözülür. Değerler
`plugin install --config <sunucu>.<anahtar>=<değer>` ile verilir (eklenti userConfig'iyle aynı
doğrulama ve depo; hassaslar şifreli depoda). Zorunlu değeri eksik sunucu başlatılmaz.

Fusion'da açılan paket `${CLAUDE_PLUGIN_DATA}/.mcpb-cache/<ad>-<özet8>/` altında tutulur; adres
bir kez indirilir (https; loopback/link-local/meta veri adresi reddedilir). Arşiv güvenli açılır.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections.abc import Mapping
from pathlib import Path

from ..core.plugin_paths import MCPB_SUFFIXES
from ..core.plugins import PluginError
from .plugin_archive import MAX_BYTES, extract_zip_into
from .plugin_data import plugin_data_dir
from .plugin_user_config import UserOption, effective_values, parse_schema, substitute_tree

CACHE_DIRNAME = ".mcpb-cache"
FETCH_TIMEOUT_S = 120.0
ERR_MANIFEST = "{ref}: MCPB manifest.json okunamadı ya da server.mcp_config yok"
ERR_FETCH = "{ref}: MCPB paketi indirilemedi: {error}"
ERR_URL = "{ref}: MCPB adresi https olmalı ve yerel/meta veri adresine gidemez"
ERR_NEEDS_CONFIG = (
    'MCP server "{server}" needs configuration before it can start: set {keys} with '
    "--config KEY=VALUE"
)


def is_mcpb(ref: str) -> bool:
    return ref.lower().endswith(MCPB_SUFFIXES)


def is_url(ref: str) -> bool:
    return ref.startswith(("https://", "http://"))


def config_name(plugin: str, server: str) -> str:
    """Paket seçeneklerinin değer deposundaki anahtarı (eklentinin kendi anahtarından ayrı)."""
    return f"{plugin}/{server}"


def _cache(plugin: str) -> Path:
    return plugin_data_dir(plugin, create=True) / CACHE_DIRNAME


def _download(ref: str, plugin: str) -> Path:
    from ..core.plugin_source_kinds import archive_url_allowed

    if not archive_url_allowed(ref):
        raise PluginError(ERR_URL.format(ref=ref))
    target = _cache(plugin) / f"{hashlib.md5(ref.encode()).hexdigest()[:8]}.mcpb"
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    try:
        request = urllib.request.Request(ref, headers={"User-Agent": "fusion-cli"})
        from .plugin_archive import checked_opener

        with checked_opener().open(request, timeout=FETCH_TIMEOUT_S) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise PluginError(ERR_FETCH.format(ref=ref, error="256 MiB sınırı"))
        partial.write_bytes(data)
        partial.replace(target)
    except (OSError, ValueError) as error:
        partial.unlink(missing_ok=True)
        raise PluginError(ERR_FETCH.format(ref=ref, error=error)) from error
    return target


def unpack(ref: str, plugin: str, root: Path) -> Path:
    """Paketi (yerel ya da adres) önbelleğe aç; açılan klasör."""
    bundle = _download(ref, plugin) if is_url(ref) else root / ref
    digest = hashlib.md5(bundle.read_bytes()).hexdigest()[:8]
    folder = _cache(plugin) / f"{bundle.stem}-{digest}"
    if not (folder / "manifest.json").is_file():
        extract_zip_into(bundle, folder)
    return folder


def _manifest(folder: Path, ref: str) -> Mapping[str, object]:
    try:
        raw = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PluginError(ERR_MANIFEST.format(ref=ref)) from error
    server = raw.get("server") if isinstance(raw, Mapping) else None
    config = server.get("mcp_config") if isinstance(server, Mapping) else None
    if not isinstance(config, Mapping) or not isinstance(raw.get("name"), str):
        raise PluginError(ERR_MANIFEST.format(ref=ref))
    return {str(key): value for key, value in raw.items()}


def _builtins(text: str, folder: Path) -> str:
    home = Path.home()
    for key, value in (
        ("${__dirname}", str(folder)),
        ("${HOME}", str(home)),
        ("${DESKTOP}", str(home / "Desktop")),
        ("${DOCUMENTS}", str(home / "Documents")),
        ("${DOWNLOADS}", str(home / "Downloads")),
        ("${pathSeparator}", os.sep),
        ("${/}", os.sep),
    ):
        text = text.replace(key, value)
    return text


def _tree(raw: object, folder: Path) -> object:
    if isinstance(raw, str):
        return _builtins(raw, folder)
    if isinstance(raw, list):
        return [_tree(item, folder) for item in raw]
    if isinstance(raw, Mapping):
        return {key: _tree(value, folder) for key, value in raw.items()}
    return raw


def bundle_schema(ref: str, plugin: str, root: Path) -> tuple[str, tuple[UserOption, ...]]:
    """(sunucu adı, `user_config` şeması)."""
    folder = unpack(ref, plugin, root)
    raw = _manifest(folder, ref)
    return str(raw["name"]), parse_schema(raw.get("user_config"))


def bundle_server(ref: str, plugin: str, root: Path, base: Path) -> tuple[str, dict[str, object]]:
    """(sunucu adı, `mcpServers` girdisi); zorunlu değeri eksikse `PluginError`."""
    folder = unpack(ref, plugin, root)
    raw = _manifest(folder, ref)
    name = str(raw["name"])
    schema = parse_schema(raw.get("user_config"))
    values = effective_values(config_name(plugin, name), schema, base) if schema else {}
    missing = [o.key for o in schema if o.required and o.key not in values]
    if missing:
        keys = ", ".join(f"{name}.{key}" for key in missing)
        raise PluginError(ERR_NEEDS_CONFIG.format(server=name, keys=keys))
    server = raw["server"]
    assert isinstance(server, Mapping)
    entry = substitute_tree(_tree(server["mcp_config"], folder), schema, values)
    return name, {str(k): v for k, v in entry.items()} if isinstance(entry, Mapping) else {}
