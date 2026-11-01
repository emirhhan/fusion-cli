"""`plugin marketplace add --scope project|local` bildirimi ve kaldırmada temizlik (#381, #376).

Claude Code 2.1.287'de ölçüldü: `marketplace add <kaynak> --scope project` pazarı o kapsamın
ayar dosyasına `extraKnownMarketplaces[<ad>] = {"source": {...}}` olarak yazar ("declared in
project settings"); `marketplace remove` bildirimi kapsam dosyalarından da siler. Kaynak nesnesi:
klasör `directory`/`path`, `.json` `file`/`path`, GitHub kısaltması `github`/`repo`(+`ref`),
başka git `git`/`url`(+`ref`), marketplace.json adresi `url`/`url`.

`user` kapsamı (varsayılan) Claude gibi `~/.claude/settings.json`'a yazılır ("declared in user
settings", Claude 2.1.287'de ölçüldü); pazarın kendisi ayrıca Fusion kaydında tutulur.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

from ..config import plugin_scopes
from ..config.plugin_scopes import (
    SCOPE_LOCAL,
    SCOPE_PROJECT,
    SCOPE_USER,
    check_scope,
    read_settings,
    settings_path,
    update_settings,
    update_user_settings,
)
from ..config.plugin_store import MarketplaceRecord
from ..core.plugins import PluginError
from .plugin_declared import ALIAS_KEY, DECLARED_KEY
from .plugin_market_source import split_ref

_LOG = logging.getLogger(__name__)
_GITHUB = "https://github.com/"


def claude_source(record: MarketplaceRecord) -> dict[str, str]:
    """Kayıttaki pazarın Claude `extraKnownMarketplaces` kaynak nesnesi."""
    if record.kind == "yerel":
        return {"source": "directory", "path": record.source}
    if record.kind == "dosya":
        return {"source": "file", "path": record.source}
    url, ref = split_ref(record.source)
    if record.kind == "url":
        return {"source": "url", "url": url}
    tail = url.removeprefix(_GITHUB).removesuffix(".git")
    if url.startswith(_GITHUB) and tail.count("/") == 1:
        found = {"source": "github", "repo": tail}
    else:
        found = {"source": "git", "url": url}
    return {**found, **({"ref": ref} if ref else {})}


def declare(scope: str, record: MarketplaceRecord, root: Path | None = None) -> str:
    """Kapsam dosyasına bildir; yazılan kapsam (user: `~/.claude/settings.json`)."""
    target = check_scope(scope) if scope else SCOPE_USER
    value = {"source": claude_source(record)}

    def change(raw: dict[str, object]) -> dict[str, object]:
        current = raw.get(DECLARED_KEY)
        block = dict(current) if isinstance(current, dict) else {}
        return {**raw, DECLARED_KEY: {**block, record.name: value}}

    if target == SCOPE_USER:
        update_user_settings(change)
    else:
        update_settings(target, root or Path.cwd(), change)
    return target


def undeclare(name: str, root: Path | None = None) -> tuple[str, ...]:
    """Pazarın bildirimini user/project/local dosyalarından sil; silinen kapsamlar."""
    project = root or Path.cwd()
    removed: list[str] = []
    for scope in (SCOPE_USER, SCOPE_PROJECT, SCOPE_LOCAL):
        user = scope == SCOPE_USER
        path = plugin_scopes.user_settings_file() if user else settings_path(scope, project)
        raw = read_settings(path) if path.is_file() else {}
        keys = [k for k in (DECLARED_KEY, ALIAS_KEY) if _has(raw.get(k), name)]
        if not keys:
            continue

        def change(current: dict[str, object], keys: list[str] = keys) -> dict[str, object]:
            updated = dict(current)
            for key in keys:
                block = current.get(key)
                if isinstance(block, dict):
                    updated[key] = {k: v for k, v in block.items() if k != name}
            return updated

        try:
            if scope == SCOPE_USER:
                update_user_settings(change)
            else:
                update_settings(scope, project, change)
        except PluginError as error:  # bozuk ayar dosyası pazar kaldırmayı durdurmaz
            _LOG.warning("pazar bildirimi silinemedi (%s): %s", path, error)
            continue
        removed.append(scope)
    return tuple(removed)


def _has(block: object, name: str) -> bool:
    return isinstance(block, Mapping) and name in block
