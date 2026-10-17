"""Telefondan gelen ekler ve telefona gösterilen görseller: boyut, tür ve konum sınırlı."""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from collections.abc import Iterable
from pathlib import Path

from ..core.protocols import Clock
from .constants import MAX_UPLOAD_BYTES, MEDIA_MAX_BYTES, UPLOAD_RETENTION_SECONDS

IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
#: Görsel gösterimi bu dizinlerin altına asla uzanmaz (anahtar/kimlik dizinleri).
_DENIED_PARTS = frozenset({".ssh", ".gnupg", ".aws", ".kube", ".config"})


class UploadError(ValueError):
    """Kullanıcıya gösterilebilir yükleme/okuma hatası."""


def _safe_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:80].strip(".")
    return base or "ek"


class UploadStore:
    """Ekleri yalnız Fusion'ın kendi yükleme dizinine yazar; ajan yolunu mutlak yol olarak alır."""

    def __init__(self, directory: Path, clock: Clock) -> None:
        self._directory = directory
        self._clock = clock
        self._items: dict[str, dict[str, str]] = {}

    def put(self, name: str, kind: str, data_base64: str) -> dict[str, str | int]:
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise UploadError("Ek verisi geçersiz.") from error
        if not raw:
            raise UploadError("Ek boş.")
        if len(raw) > MAX_UPLOAD_BYTES:
            raise UploadError(f"Ek en fazla {MAX_UPLOAD_BYTES // 1024} KB olabilir.")
        safe = _safe_name(name)
        if kind == "image" and Path(safe).suffix.casefold() not in IMAGE_TYPES:
            raise UploadError("Görsel eki png, jpg, gif veya webp olmalı.")
        self._directory.mkdir(parents=True, exist_ok=True)
        self._cleanup()
        upload_id = uuid.uuid4().hex
        target = self._directory / f"{upload_id}-{safe}"
        target.write_bytes(raw)
        target.chmod(0o600)
        self._items[upload_id] = {
            "path": str(target),
            "name": safe,
            "kind": "image" if kind == "image" else "file",
        }
        return {
            "uploadId": upload_id,
            "name": safe,
            "kind": self._items[upload_id]["kind"],
            "bytes": len(raw),
        }

    def resolve(self, upload_ids: Iterable[object]) -> list[dict[str, str]]:
        """Kimliklerden `tur.calistir` ek kayıtları; bilinmeyen kimlik hata verir."""
        resolved: list[dict[str, str]] = []
        for ident in list(upload_ids)[:8]:
            item = self._items.get(str(ident))
            if item is None or not Path(item["path"]).is_file():
                raise UploadError("Ek bulunamadı; yeniden ekle.")
            resolved.append(dict(item))
        return resolved

    def _cleanup(self) -> None:
        cutoff = self._clock.now() - UPLOAD_RETENTION_SECONDS
        for file in self._directory.glob("*"):
            try:
                if file.is_file() and file.stat().st_mtime < cutoff:
                    file.unlink()
            except OSError:
                continue


class MediaReader:
    """Telefona görsel verir: yalnız izinli köklerin altındaki görsel dosyalar, boyut sınırlı."""

    def __init__(self, roots: Iterable[Path]) -> None:
        self._roots = [root.expanduser().resolve() for root in roots]

    def read(self, path: str) -> tuple[str, bytes]:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            raise UploadError("Görsel yolu mutlak olmalı.")
        resolved = candidate.resolve()
        media_type = IMAGE_TYPES.get(resolved.suffix.casefold())
        if media_type is None:
            raise UploadError("Yalnız görsel dosyalar gösterilir.")
        if not any(resolved.is_relative_to(root) for root in self._roots):
            raise UploadError("Bu görsel uzaktan açılamaz.")
        if _DENIED_PARTS & set(resolved.parts):
            raise UploadError("Bu görsel uzaktan açılamaz.")
        try:
            if resolved.stat().st_size > MEDIA_MAX_BYTES:
                raise UploadError("Görsel çok büyük.")
            return media_type, resolved.read_bytes()
        except OSError as error:
            raise UploadError("Görsel okunamadı.") from error
