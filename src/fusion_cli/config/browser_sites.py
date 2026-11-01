"""Yerleşik Browser'da "Always allow" denen dış siteler (#439; Claude Desktop Browser).

Claude: dış sitede "Always allow" o siteyi kalıcı izinli yapar. Liste kullanıcı yapılandırma
dizinindedir (`browser-sites.json`); bozuk ya da okunamayan dosya boş liste sayılır (gevşeme
yok). Yazım atomiktir.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .paths import user_config_dir

STORE_NAME = "browser-sites.json"
_MAX_SITES = 500


def sites_file() -> Path:
    return user_config_dir() / STORE_NAME


def load_allowed(path: Path | None = None) -> frozenset[str]:
    target = path or sites_file()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    raw = data.get("always_allow") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(item for item in raw if isinstance(item, str) and item)


def _save(hosts: frozenset[str], path: Path | None = None) -> None:
    target = path or sites_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=target.parent, prefix=".browser-sites-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"always_allow": sorted(hosts)[:_MAX_SITES]}, stream, indent=2)
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def add_allowed(host: str, path: Path | None = None) -> None:
    _save(load_allowed(path) | {host.lower()}, path)


def remove_allowed(host: str, path: Path | None = None) -> bool:
    current = load_allowed(path)
    if host.lower() not in current:
        return False
    _save(current - {host.lower()}, path)
    return True
