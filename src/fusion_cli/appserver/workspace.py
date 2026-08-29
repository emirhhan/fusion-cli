"""Masaüstü uygulaması için proje-kökü sınırlı salt-okunur çalışma alanı.

Bu katman UI'ın dosya sistemine doğrudan erişmesini engeller. Bütün yollar tek
bir sınır fonksiyonundan geçer; sembolik bağlar dahil gerçek hedef proje
kökünün dışına çıkamaz.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path, PurePath
from typing import Any

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 200
_DEFAULT_MAX_BYTES = 256 * 1024
_MAX_READ_BYTES = 2 * 1024 * 1024
_OUTSIDE = "Proje klasörünün dışına çıkılamaz."


class WorkspacePathError(ValueError):
    """Kullanıcı yolu proje sınırını ihlal etti."""


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "metin": message}


def _integer(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _resolve_inside(root: Path, raw: object) -> Path:
    """`raw` yolunu çözer; sözcüksel ve symlink kaçışlarını reddeder."""
    root = root.resolve()
    text = str(raw or "")
    relative = PurePath(text)
    if relative.is_absolute() or ".." in relative.parts:
        raise WorkspacePathError(_OUTSIDE)
    candidate = (root / text).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise WorkspacePathError(_OUTSIDE)
    return candidate


def _relative(root: Path, path: Path) -> str:
    value = path.relative_to(root.resolve()).as_posix()
    return "" if value == "." else value


def workspace_status(root: Path) -> dict[str, Any]:
    resolved = root.resolve()
    return {
        "ok": True,
        "kok": str(resolved),
        "git": (resolved / ".git").exists(),
        "okunabilir": os.access(resolved, os.R_OK),
        "yazilabilir": os.access(resolved, os.W_OK),
    }


def list_entries(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    try:
        directory = _resolve_inside(root, data.get("yol", ""))
    except WorkspacePathError as error:
        return _error(str(error))
    if not directory.exists():
        return _error("Klasör bulunamadı.")
    if not directory.is_dir():
        return _error("Seçilen yol bir klasör değil.")

    limit = _integer(data.get("limit"), default=_DEFAULT_LIMIT, minimum=1, maximum=_MAX_LIMIT)
    cursor = _integer(data.get("cursor"), default=0, minimum=0, maximum=2**31 - 1)
    try:
        entries = sorted(
            directory.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.casefold(), item.name),
        )
    except OSError:
        return _error("Klasör okunamadı.")

    page = entries[cursor : cursor + limit]
    payload: list[dict[str, Any]] = []
    for entry in page:
        try:
            stat = entry.stat()
            kind = "klasor" if entry.is_dir() else "dosya"
            payload.append(
                {
                    "ad": entry.name,
                    "yol": _relative(root, entry),
                    "tur": kind,
                    "boyut": 0 if kind == "klasor" else stat.st_size,
                    "degistirilme": stat.st_mtime,
                }
            )
        except OSError:
            continue
    next_cursor = cursor + len(page)
    has_more = next_cursor < len(entries)
    return {
        "ok": True,
        "yol": _relative(root, directory),
        "girdiler": payload,
        "next_cursor": next_cursor if has_more else None,
        "has_more": has_more,
    }


def _mime(path: Path, *, binary: bool) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed:
        return guessed
    return "application/octet-stream" if binary else "text/plain"


def read_entry(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    try:
        path = _resolve_inside(root, data.get("yol", ""))
    except WorkspacePathError as error:
        return _error(str(error))
    if not path.exists():
        return _error("Dosya bulunamadı.")
    if not path.is_file():
        return _error("Seçilen yol bir dosya değil.")

    max_bytes = _integer(
        data.get("max_bytes"),
        default=_DEFAULT_MAX_BYTES,
        minimum=1,
        maximum=_MAX_READ_BYTES,
    )
    try:
        raw = path.read_bytes()
    except OSError:
        return _error("Dosya okunamadı.")
    digest = hashlib.sha256(raw).hexdigest()
    sample = raw[:max_bytes]
    binary = b"\x00" in sample
    text: str | None = None
    if not binary:
        try:
            text = sample.decode("utf-8")
        except UnicodeDecodeError:
            binary = True
    return {
        "ok": True,
        "yol": _relative(root, path),
        "tur": "binary" if binary else "metin",
        "mime": _mime(path, binary=binary),
        "boyut": len(raw),
        "sha256": digest,
        "icerik": None if binary else text,
        "kesildi": len(raw) > max_bytes,
    }
