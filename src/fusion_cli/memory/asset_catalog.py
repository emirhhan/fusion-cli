"""Dosya kimliği ve soy bağı; iş başarısı veya dosya içeriği otoritesi değildir."""

from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import closing
from pathlib import Path
from typing import Any


class AssetCatalogError(ValueError):
    """Kayıt veya çağıranın dosya kapsamı doğrulanamadı."""


class AssetCatalog:
    """Her işlem kendi bağlantısını kapatır; kayıt tek SQLite transaction'dır."""

    def __init__(
        self,
        path: Path,
        profile_id: str,
        roots: Mapping[str, Path],
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not profile_id:
            raise AssetCatalogError("Asset kullanıcı kapsamı gerekli.")
        self._path, self._profile, self._clock = path, profile_id, clock
        self._roots = {key: root.resolve() for key, root in roots.items()}
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise AssetCatalogError("Asset kataloğu sürümü desteklenmiyor.")
            db.execute("""CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY, profile TEXT NOT NULL,
                root_key TEXT NOT NULL, root_path TEXT NOT NULL,
                relative_path TEXT NOT NULL, created_at REAL NOT NULL,
                metadata TEXT NOT NULL,
                UNIQUE(profile,root_key,root_path,relative_path))""")
            db.execute("PRAGMA user_version=1")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self._path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def _path_for(self, root_key: str, relative_path: str) -> Path:
        if (
            not isinstance(root_key, str)
            or not isinstance(relative_path, str)
            or len(relative_path) > 4096
        ):
            raise AssetCatalogError("Asset kökü ve göreli yolu geçersiz.")
        root = self._roots.get(root_key)
        raw = Path(relative_path)
        if root is None or raw.is_absolute() or ".." in raw.parts or not raw.parts:
            raise AssetCatalogError("Asset yolu izinli kökte olmalı.")
        try:
            path = (root / raw).resolve()
            path.relative_to(root)
        except (OSError, ValueError, RuntimeError):
            raise AssetCatalogError("Asset yolu izinli kökün dışına çıkıyor.") from None
        return path

    def _decode(self, row: sqlite3.Row) -> dict[str, Any]:
        root = self._roots.get(row["root_key"])
        if root is None or str(root) != row["root_path"]:
            raise AssetCatalogError("Asset kökü bu çağrıda yetkili değil.")
        try:
            metadata = json.loads(row["metadata"])
            fields = {
                "asset_id",
                "metadata_version",
                "kind",
                "mime",
                "relative_path",
                "created_at",
                "created_by_task_id",
                "parent_asset_ids",
                "width",
                "height",
                "alpha",
                "model",
                "seed",
            }
            if not isinstance(metadata, dict) or set(metadata) != fields:
                raise ValueError
            if type(metadata["metadata_version"]) is not int or metadata["metadata_version"] != 1:
                raise ValueError
            if (
                metadata["asset_id"] != row["asset_id"]
                or metadata["relative_path"] != row["relative_path"]
            ):
                raise ValueError
            uuid.UUID(metadata["asset_id"])
            if not isinstance(metadata["kind"], str) or metadata["kind"] not in {
                "image",
                "video",
                "document",
                "code",
                "other",
            }:
                raise ValueError
            stamp = metadata["created_at"]
            if (
                type(stamp) not in (int, float)
                or not math.isfinite(stamp)
                or stamp != row["created_at"]
            ):
                raise ValueError
            for field in ("mime", "created_by_task_id", "model"):
                value = metadata[field]
                if value is not None and (
                    not isinstance(value, str) or not value or len(value) > 256
                ):
                    raise ValueError
            for field in ("width", "height"):
                value = metadata[field]
                if value is not None and (type(value) is not int or value < 1):
                    raise ValueError
            if metadata["alpha"] is not None and type(metadata["alpha"]) is not bool:
                raise ValueError
            if metadata["seed"] is not None and type(metadata["seed"]) is not int:
                raise ValueError
            parents = metadata["parent_asset_ids"]
            if (
                not isinstance(parents, list)
                or len(parents) > 32
                or any(not isinstance(item, str) for item in parents)
            ):
                raise ValueError
            if len(set(parents)) != len(parents) or metadata["asset_id"] in parents:
                raise ValueError
            for parent in parents:
                uuid.UUID(parent)
            path = self._path_for(row["root_key"], row["relative_path"])
            return {**metadata, "available": path.is_file(), "path": str(path)}
        except (OSError, ValueError, TypeError, RuntimeError):
            raise AssetCatalogError("Asset kaydı veya dosya kapsamı doğrulanamadı.") from None

    def register(
        self,
        root_key: str,
        relative_path: str,
        *,
        kind: str,
        mime: str | None = None,
        created_by_task_id: str | None = None,
        parent_asset_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        path = self._path_for(root_key, relative_path)
        root = self._roots[root_key]
        if (
            not path.is_file()
            or not isinstance(kind, str)
            or kind not in {"image", "video", "document", "code", "other"}
        ):
            raise AssetCatalogError("Asset dosyası veya türü geçersiz.")
        relative = path.relative_to(root).as_posix()
        if not isinstance(parent_asset_ids, tuple) or any(
            not isinstance(parent, str) or not parent for parent in parent_asset_ids
        ):
            raise AssetCatalogError("Asset ebeveyn kimliği gerekli.")
        if len(parent_asset_ids) > 32 or len(set(parent_asset_ids)) != len(parent_asset_ids):
            raise AssetCatalogError("Asset ebeveynleri geçersiz.")
        if any(not isinstance(parent, str) or not parent for parent in parent_asset_ids):
            raise AssetCatalogError("Asset ebeveyn kimliği gerekli.")
        for value in (mime, created_by_task_id):
            if value is not None and (not isinstance(value, str) or not value or len(value) > 256):
                raise AssetCatalogError("Asset künyesi geçersiz.")
        stamp = self._clock()
        if not math.isfinite(stamp):
            raise AssetCatalogError("Asset kayıt zamanı geçersiz.")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM assets WHERE profile=? AND root_key=? "
                "AND root_path=? AND relative_path=?",
                (self._profile, root_key, str(root), relative),
            ).fetchone()
            if row is not None:
                result = self._decode(row)
                if (
                    result["kind"] != kind
                    or (mime is not None and result["mime"] != mime)
                    or (parent_asset_ids and result["parent_asset_ids"] != list(parent_asset_ids))
                    or (
                        created_by_task_id is not None
                        and result["created_by_task_id"] != created_by_task_id
                    )
                ):
                    raise AssetCatalogError("Asset kimliği farklı künyeyle yeniden kaydedilemez.")
                return result
            for parent in parent_asset_ids:
                parent_row = db.execute(
                    "SELECT * FROM assets WHERE profile=? AND asset_id=?", (self._profile, parent)
                ).fetchone()
                if parent_row is None:
                    raise AssetCatalogError("Asset ebeveyni bu kapsamda bulunamadı.")
                self._decode(parent_row)
            asset_id = str(uuid.uuid4())
            metadata = {
                "asset_id": asset_id,
                "metadata_version": 1,
                "kind": kind,
                "mime": mime,
                "relative_path": relative,
                "created_at": stamp,
                "created_by_task_id": created_by_task_id,
                "parent_asset_ids": list(parent_asset_ids),
                "width": None,
                "height": None,
                "alpha": None,
                "model": None,
                "seed": None,
            }
            db.execute(
                "INSERT INTO assets VALUES(?,?,?,?,?,?,?)",
                (
                    asset_id,
                    self._profile,
                    root_key,
                    str(root),
                    relative,
                    stamp,
                    json.dumps(metadata),
                ),
            )
            return {**metadata, "available": True, "path": str(path)}

    def resolve(self, asset_id: str) -> dict[str, Any]:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT * FROM assets WHERE profile=? AND asset_id=?", (self._profile, asset_id)
            ).fetchone()
            if row is None:
                raise AssetCatalogError("Asset bu kullanıcı kapsamında bulunamadı.")
            return self._decode(row)

    def list_page(
        self, *, limit: int = 50, cursor: tuple[float, str] | None = None, descending: bool = False
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise AssetCatalogError("Asset sayfa boyutu 1–100 olmalı.")
        if cursor is not None and (
            not isinstance(cursor, tuple)
            or len(cursor) != 2
            or not isinstance(cursor[0], (int, float))
            or isinstance(cursor[0], bool)
            or not math.isfinite(cursor[0])
            or not isinstance(cursor[1], str)
        ):
            raise AssetCatalogError("Asset sayfa işareti geçersiz.")
        if not self._roots:
            return {"items": [], "next_cursor": None}
        allowed = " OR ".join("(root_key=? AND root_path=?)" for _ in self._roots)
        clause = " AND (" + allowed + ")"
        parameters: list[str | float | int] = [self._profile]
        for root_key, root_path in self._roots.items():
            parameters.extend([root_key, str(root_path)])
        if cursor is not None:
            comparison = "<" if descending else ">"
            clause += f" AND (created_at{comparison}? OR (created_at=? AND asset_id{comparison}?))"
            parameters.extend([cursor[0], cursor[0], cursor[1]])
        parameters.append(limit + 1)
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT * FROM assets WHERE profile=?"
                + clause
                + (
                    " ORDER BY created_at DESC,asset_id DESC LIMIT ?"
                    if descending
                    else " ORDER BY created_at,asset_id LIMIT ?"
                ),
                parameters,
            ).fetchall()
            items = [self._decode(row) for row in rows[:limit]]
        next_cursor = (
            (rows[limit - 1]["created_at"], rows[limit - 1]["asset_id"])
            if len(rows) > limit
            else None
        )
        return {"items": items, "next_cursor": next_cursor}
