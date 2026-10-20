"""Galeri ve kitaplık için aynı kullanıcı-kapsamlı kimlik kataloğu adaptörü."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import threading
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from ..core.image_jobs import ImageJobConflictError
from ..memory.asset_catalog import AssetCatalog, AssetCatalogError
from ..providers.image_payload import validate_image_bytes
from .asset_paths import scoped_files
from .image_flows import _IMAGE_SUFFIXES, gallery_dir, list_gallery
from .image_job_artifacts import _read_scoped_image
from .library import list_library


def gallery_catalog(memory_dir: Path) -> AssetCatalog:
    return AssetCatalog(
        memory_dir / "assets.sqlite3", str(memory_dir.resolve()), {"gallery": gallery_dir()}
    )


_INDEX_LOCK = threading.Lock()


@lru_cache(maxsize=16)
def _sync_gallery_index(memory_dir: Path, root: Path, fingerprint: tuple[int, ...]) -> None:
    """Dizin değişmediyse sonraki sayfa tüm dosyaları yeniden taramaz."""
    catalog = gallery_catalog(memory_dir)
    for path, _stamp in sorted(
        scoped_files(root, frozenset(_IMAGE_SUFFIXES)), key=lambda item: item[1]
    ):
        try:
            catalog.register("gallery", path.name, kind="image")
        except (OSError, ValueError, RuntimeError):
            # Tarama sırasında kaybolan dosya bir sonraki gözlemde görünmez.
            if path.exists():
                raise


def asset_page(data: dict[str, Any], memory_dir: Path) -> dict[str, Any]:
    """Host'a yalnız kimlik/metadata; yerel mutlak yol asla aktarılmaz."""
    try:
        limit = data.get("sinir", 50)
        raw_cursor = data.get("cursor")
        if raw_cursor is not None and (not isinstance(raw_cursor, list) or len(raw_cursor) != 2):
            raise AssetCatalogError("Asset sayfa işareti geçersiz.")
        cursor = tuple(raw_cursor) if raw_cursor is not None else None
        root = gallery_dir().resolve()
        catalog = gallery_catalog(memory_dir)
        # Girdi doğrulaması tarama/kayıt yan etkisinden önce aynı katalog otoritesindedir.
        catalog.list_page(limit=limit, cursor=cursor, descending=True)
        if root.is_dir():
            stamp = root.stat()
            database = (memory_dir / "assets.sqlite3").stat()
            with _INDEX_LOCK:
                _sync_gallery_index(
                    memory_dir.resolve(),
                    root,
                    (
                        stamp.st_dev,
                        stamp.st_ino,
                        stamp.st_mtime_ns,
                        database.st_dev,
                        database.st_ino,
                    ),
                )
        page = catalog.list_page(limit=limit, cursor=cursor, descending=True)
        return {
            "ok": True,
            "items": [
                {key: value for key, value in item.items() if key != "path"}
                for item in page["items"]
            ],
            "next_cursor": list(page["next_cursor"]) if page["next_cursor"] else None,
        }
    except (AssetCatalogError, OSError, ValueError, RuntimeError, sqlite3.Error):
        return {"ok": False, "metin": "Dosya sayfası bu kapsamda doğrulanamadı."}


def asset_preview(data: dict[str, Any], memory_dir: Path) -> dict[str, Any]:
    """Kimlik kapsamından doğrulanmış PNG/JPEG için sınırlı önizleme; özgün dosya değildir."""
    resolved = resolve_asset(data, memory_dir)
    if resolved.get("ok") is not True:
        return resolved
    try:
        asset = resolved["asset"]
        if asset["available"] is not True or asset["kind"] != "image":
            raise ValueError
        _path, raw = _read_scoped_image(asset["path"], gallery_dir())
        observed = validate_image_bytes(raw)
        if observed is None:
            raise ValueError
        with Image.open(BytesIO(raw)) as image:
            encoded = ""
            for edge in (512, 256):
                image.thumbnail((edge, edge))
                preview = BytesIO()
                image.convert("RGBA").save(preview, format="PNG")
                encoded = base64.b64encode(preview.getvalue()).decode("ascii")
                if len(encoded) <= 700000:
                    break
        if len(encoded) > 700000:
            raise ValueError
        return {
            "ok": True,
            "asset_id": asset["asset_id"],
            "data_url": "data:image/png;base64," + encoded,
            "width": observed.width,
            "height": observed.height,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    except (OSError, ValueError, RuntimeError, ImageJobConflictError):
        return {"ok": False, "metin": "Bu dosya için güvenli görsel önizlemesi kullanılamıyor."}


def gallery_page(data: dict[str, Any], memory_dir: Path) -> dict[str, Any]:
    """Yeni native istemciye yalnız bir sayfa; eski istemci tam galeri RPC'sini korur."""
    page = asset_page(data, memory_dir)
    if page.get("ok") is not True:
        return page
    files = []
    catalog = gallery_catalog(memory_dir)
    for reference in page["items"]:
        try:
            asset = catalog.resolve(reference["asset_id"])
            if not asset["available"]:
                continue
            path = Path(asset["path"])
            metadata: dict[str, Any] = {}
            try:
                _, raw = _read_scoped_image(
                    str(path.with_suffix(path.suffix + ".json")), gallery_dir(), max_bytes=65536
                )
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    metadata = loaded
            except (OSError, ValueError, RuntimeError, ImageJobConflictError):
                pass
            prompt, provider = metadata.get("istem"), metadata.get("saglayici")
            files.append(
                {
                    "yol": str(path),
                    "asset": reference,
                    "istem": prompt[:4000] if isinstance(prompt, str) else "",
                    "saglayici": provider[:120] if isinstance(provider, str) else "",
                }
            )
        except (AssetCatalogError, OSError, ValueError, RuntimeError):
            continue
    return {"ok": True, "dosyalar": files, "next_cursor": page["next_cursor"]}


def catalogued_gallery(memory_dir: Path) -> dict[str, Any]:
    return list_gallery(catalog=gallery_catalog(memory_dir))


def catalogued_library(data: dict[str, Any], memory_dir: Path) -> dict[str, Any]:
    return list_library(data, catalog=gallery_catalog(memory_dir))


def resolve_asset(data: dict[str, Any], memory_dir: Path) -> dict[str, Any]:
    asset_id = data.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id or len(asset_id) > 128:
        return {"ok": False, "metin": "Kalıcı dosya kimliği gerekli."}
    try:
        asset = gallery_catalog(memory_dir).resolve(asset_id)
        return {"ok": True, "asset": asset}
    except AssetCatalogError:
        return {"ok": False, "metin": "Dosya kimliği bu kapsamda doğrulanamadı."}
