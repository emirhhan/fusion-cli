"""Görsel işinin çıktı makbuzunu gerçek ve galeriye bağlı dosyadan üret."""

from __future__ import annotations

import hashlib
import os
import stat
from contextlib import ExitStack
from pathlib import Path

from ..core.image_jobs import ImageJobConflictError, ImageOutputReceipt
from ..providers.image_payload import ValidatedImage, validate_image_bytes

MAX_IMAGE_JOB_BYTES = 32 * 1024 * 1024
_MAX_OUTPUTS = 16


def receipt_reads_supported() -> bool:
    """Güvenli dir-fd okuması yoksa yeni iş yeteneği ilan edilmez."""
    return os.name == "posix" and all(
        hasattr(os, flag) for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")
    )


def _read_scoped_image(
    raw: str, directory: Path, *, max_bytes: int | None = None
) -> tuple[Path, bytes]:
    max_bytes = MAX_IMAGE_JOB_BYTES if max_bytes is None else max_bytes
    if not receipt_reads_supported():
        raise ImageJobConflictError("Bu platformda güvenli görsel makbuzu okuması desteklenmiyor.")
    original = Path(raw)
    if not original.is_absolute() or original.is_symlink():
        raise ValueError
    base, path = directory.resolve(strict=True), original.resolve(strict=True)
    relative = path.relative_to(base)
    if not relative.parts:
        raise ValueError
    # Kök dir-fd'sinden her bileşeni no-follow aç: kontrol/okuma arasında
    # alt dizin veya son dosya bağa çevrilse bile başka alandan bayt okuma.
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as cleanup:
        parent = os.open(base, directory_flags)
        cleanup.callback(os.close, parent)
        for part in relative.parts[:-1]:
            parent = os.open(part, directory_flags, dir_fd=parent)
            cleanup.callback(os.close, parent)
        descriptor = os.open(
            relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
                raise ValueError
            data = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
            if len(data) > max_bytes or (
                before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise ValueError
        current = os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError
        if original.resolve(strict=True) != path:
            raise ValueError
    return path, data


def collect_outputs(result: dict[str, object], directory: Path) -> tuple[ImageOutputReceipt, ...]:
    """İstek ölçülerini değil gerçek dosya ölçüsü ve SHA'yı makbuza yaz."""
    try:
        files = result.get("dosyalar")
        if (
            result.get("ok") is not True
            or not isinstance(files, list)
            or not 1 <= len(files) <= _MAX_OUTPUTS
        ):
            raise ValueError
        provider = result.get("saglayici", "")
        if not isinstance(provider, str):
            raise ValueError
        outputs: list[ImageOutputReceipt] = []
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get("yol"), str):
                raise ValueError
            path, data = _read_scoped_image(item["yol"], directory)
            observed = validate_image_bytes(data)
            if observed is None:
                raise ValueError
            allowed = {".jpg", ".jpeg"} if observed.suffix == ".jpg" else {".png"}
            if path.suffix.lower() not in allowed:
                raise ValueError
            outputs.append(
                ImageOutputReceipt(
                    str(path),
                    observed.width,
                    observed.height,
                    hashlib.sha256(data).hexdigest(),
                    provider,
                )
            )
        if len({output.path for output in outputs}) != len(outputs):
            raise ValueError
        return tuple(outputs)
    except (OSError, ValueError, RuntimeError, NotImplementedError):
        raise ImageJobConflictError(
            "Görsel çıktı dosyaları doğrulanamadı; başarı kaydedilmedi."
        ) from None


def outputs_current(outputs: tuple[ImageOutputReceipt, ...], directory: Path) -> bool:
    """Geçmiş başarı, silinmiş/değişmiş dosyaya güncel başarı otoritesi vermez."""
    if not outputs:
        return False
    try:
        current = collect_outputs(
            {"ok": True, "dosyalar": [{"yol": output.path} for output in outputs]}, directory
        )
    except ImageJobConflictError:
        return False
    return all(
        (actual.path, actual.width, actual.height, actual.digest)
        == (expected.path, expected.width, expected.height, expected.digest)
        for actual, expected in zip(current, outputs, strict=True)
    )


def capture_reference(raw: str, directory: Path) -> ValidatedImage:
    """Parmak izi ve sağlayıcının kullanacağı referansı aynı baytlardan sabitle."""
    try:
        path, data = _read_scoped_image(raw, directory)
        observed = validate_image_bytes(data)
        if observed is None or path.suffix.lower() not in (
            {".jpg", ".jpeg"} if observed.suffix == ".jpg" else {".png"}
        ):
            raise ValueError
        return observed
    except (OSError, ValueError, RuntimeError, NotImplementedError):
        raise ImageJobConflictError("Referans görsel doğrulanamadı.") from None
