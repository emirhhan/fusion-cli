"""Galeri ve kitaplığın mevcut çalışma alanı yol otoritesini ortak kullanımı."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..memory.asset_catalog import AssetCatalog, AssetCatalogError
from .workspace import resolve_workspace_path


def generated_path(root: Path, raw: str) -> Path:
    """Mutlak proje içi olay yolunu da mevcut göreli resolver üzerinden doğrula."""
    path = Path(raw)
    relative = str(path.resolve().relative_to(root.resolve())) if path.is_absolute() else raw
    return resolve_workspace_path(root, relative)


def scoped_files(directory: Path, suffixes: frozenset[str]) -> list[tuple[Path, float]]:
    """Dışarı kaçan veya tarama sırasında kaybolan dosya listeye giremez."""
    found: list[tuple[Path, float]] = []
    try:
        paths = tuple(directory.iterdir())
    except OSError:
        return found
    for path in paths:
        if path.suffix.lower() not in suffixes:
            continue
        try:
            resolved = resolve_workspace_path(directory, path.name)
            if resolved.is_file():
                found.append((path, resolved.stat().st_mtime))
        except (OSError, ValueError, RuntimeError):
            continue
    return found


def catalog_fields(
    catalog: AssetCatalog | None, root_key: str, path: Path, root: Path
) -> dict[str, Any]:
    """Eski yol alanını koru; kalıcı kimlik arızasını başarı gibi göstermeden ekle."""
    if catalog is None:
        return {}
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        return {"asset": catalog.register(root_key, relative, kind="image")}
    except (AssetCatalogError, OSError, ValueError, RuntimeError, sqlite3.Error):
        return {"asset": None, "asset_error": "Kalıcı dosya kimliği doğrulanamadı."}
