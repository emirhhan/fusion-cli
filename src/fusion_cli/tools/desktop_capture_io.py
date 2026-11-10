"""Arka plan gözlemi için sınırlandırılmış, köke bağlı PNG alışverişi."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import secrets
import stat
import struct
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from ..core.desktop_frame import (
    MAX_BACKGROUND_IMAGE_BYTES,
    BackgroundCapture,
    capture_file_generation,
)
from ..core.desktop_ref_handles import Scope
from ..core.file_lease import FileLease

BACKGROUND_IMAGE_PATH = Path(".fusion/tmp/arka-plan-ekrani.png")
BACKGROUND_LOCK_NAME = ".arka-plan-ekrani.lock"
BACKGROUND_STAGING_NAME = ".arka-plan-ekrani.tmp"
MAX_BACKGROUND_BYTES = MAX_BACKGROUND_IMAGE_BYTES
MAX_BACKGROUND_PIXELS = 32_000_000
PNG_MARKER_KEY = b"FusionBackgroundCapture\x00"
PNG_MARKER_VERSION = b"1:"
PNG_PREFIX = "data:image/png;base64,"
UNAVAILABLE = "Gözlem dosyası yayımlanamadı; image_path yok. Satır içi görsel korunuyor."


def _png_marker(payload: bytes) -> tuple[int, bytes | None]:
    """Tüm parça CRC'lerini, tek işareti ve son IEND konumunu doğrula."""
    offset, marker = 8, None
    while offset + 12 <= len(payload):
        length = int.from_bytes(payload[offset : offset + 4], "big")
        end = offset + 12 + length
        if end > len(payload):
            raise ValueError(UNAVAILABLE)
        chunk = payload[offset + 4 : end - 4]
        if zlib.crc32(chunk) != int.from_bytes(payload[end - 4 : end], "big"):
            raise ValueError(UNAVAILABLE)
        if chunk[:4] == b"tEXt" and chunk[4:].startswith(PNG_MARKER_KEY):
            value = chunk[4 + len(PNG_MARKER_KEY) :]
            if (
                marker is not None
                or not value.startswith(PNG_MARKER_VERSION)
                or len(value) != 34
                or any(char not in b"0123456789abcdef" for char in value[2:])
            ):
                raise ValueError(UNAVAILABLE)
            marker = value
        if chunk[:4] == b"IEND":
            if length or end != len(payload):
                raise ValueError(UNAVAILABLE)
            return offset, marker
        offset = end
    raise ValueError(UNAVAILABLE)


def _validate_png(payload: bytes) -> tuple[int, int]:
    if not 24 <= len(payload) <= MAX_BACKGROUND_BYTES or payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(UNAVAILABLE)
    width, height = struct.unpack(">II", payload[16:24])
    if not width or not height or width * height > MAX_BACKGROUND_PIXELS:
        raise ValueError(UNAVAILABLE)
    from PIL import Image

    with Image.open(io.BytesIO(payload)) as parsed:
        if parsed.format != "PNG" or parsed.size != (width, height):
            raise ValueError(UNAVAILABLE)
        parsed.verify()
    with Image.open(io.BytesIO(payload)) as parsed:
        parsed.load()
    return width, height


def decode_png(image: str) -> tuple[bytes, int, int]:
    """Base64 tahsisinden ve PNG çözümlemesinden önce bütçeyi denetle."""
    if not image.startswith(PNG_PREFIX) or len(image) > len(PNG_PREFIX) + 4 * (
        (MAX_BACKGROUND_BYTES + 2) // 3
    ):
        raise ValueError(UNAVAILABLE)
    payload = base64.b64decode(image[len(PNG_PREFIX) :], validate=True)
    width, height = _validate_png(payload)
    end, marker = _png_marker(payload)
    if marker is not None:
        raise ValueError(UNAVAILABLE)
    chunk = b"tEXt" + PNG_MARKER_KEY + PNG_MARKER_VERSION + secrets.token_hex(16).encode("ascii")
    encoded = struct.pack(">I", len(chunk) - 4) + chunk + struct.pack(">I", zlib.crc32(chunk))
    payload = payload[:end] + encoded + payload[end:]
    if len(payload) > MAX_BACKGROUND_BYTES:
        raise ValueError(UNAVAILABLE)
    return payload, width, height


@contextmanager
def _slot_directory(root: Path, *, create: bool) -> Iterator[int]:
    """Sembolik bağlantıları izlemeyen açık dizin tanıtıcıları kullan."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise OSError(UNAVAILABLE)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    handles = [os.open(root, flags)]
    try:
        for part in BACKGROUND_IMAGE_PATH.parts[:-1]:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(part, mode=0o700, dir_fd=handles[-1])
            handles.append(os.open(part, flags, dir_fd=handles[-1]))
        yield handles[-1]
    finally:
        for handle in reversed(handles):
            os.close(handle)


def _read_slot(
    directory: int, name: str = BACKGROUND_IMAGE_PATH.name
) -> tuple[bytes, tuple[int, int, int, int]]:
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(before.st_mode)
            or not 0 < before.st_size <= MAX_BACKGROUND_BYTES
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_uid != os.getuid()
        ):
            raise ValueError(UNAVAILABLE)
        payload = handle.read(MAX_BACKGROUND_BYTES + 1)
        generation = capture_file_generation(before)
        if generation != capture_file_generation(
            os.fstat(handle.fileno())
        ) or generation != capture_file_generation(
            os.stat(name, dir_fd=directory, follow_symlinks=False)
        ):
            raise ValueError(UNAVAILABLE)
    return payload, generation


def _existing_generation(directory: int) -> tuple[int, int, int, int] | None:
    try:
        info = os.stat(BACKGROUND_IMAGE_PATH.name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(UNAVAILABLE)
    return capture_file_generation(info)


def _marked_cache_generation(directory: int, name: str) -> tuple[int, int, int, int]:
    payload, generation = _read_slot(directory, name)
    _validate_png(payload)
    _, marker = _png_marker(payload)
    if marker is None:
        raise ValueError(UNAVAILABLE)
    return generation


@contextmanager
def _publication_lease(directory: int) -> Iterator[None]:
    lease = FileLease(Path(BACKGROUND_LOCK_NAME), dir_fd=directory)
    if not lease.try_acquire():
        raise OSError(UNAVAILABLE)
    try:
        try:
            _marked_cache_generation(directory, BACKGROUND_STAGING_NAME)
        except FileNotFoundError:
            pass
        else:
            os.unlink(BACKGROUND_STAGING_NAME, dir_fd=directory)
        yield
    finally:
        lease.close()


def _replace_slot(
    directory: int, payload: bytes, current: Callable[[], bool]
) -> tuple[int, int, int, int]:
    name = BACKGROUND_STAGING_NAME
    descriptor = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            before = _existing_generation(directory)
            if (
                before is not None
                and _marked_cache_generation(directory, BACKGROUND_IMAGE_PATH.name) != before
            ):
                raise ValueError(UNAVAILABLE)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            generation = capture_file_generation(os.fstat(handle.fileno()))
            if not current():
                raise ValueError(UNAVAILABLE)
            if before is None:
                # İlk yayında yeni bir kullanıcı dosyası atomik olarak korunur.
                os.link(
                    name,
                    BACKGROUND_IMAGE_PATH.name,
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                    follow_symlinks=False,
                )
            else:
                if _existing_generation(directory) != before:
                    raise ValueError(UNAVAILABLE)
                os.replace(
                    name, BACKGROUND_IMAGE_PATH.name, src_dir_fd=directory, dst_dir_fd=directory
                )
            if not current():
                raise ValueError(UNAVAILABLE)
            return generation
    finally:
        with suppress(FileNotFoundError):
            os.unlink(name, dir_fd=directory)


def publish_background_image(
    root: Path,
    scope: Scope,
    image: str,
    pid: int,
    window_id: int,
    current: Callable[[], bool],
) -> BackgroundCapture:
    """Atomik değişimden önce sahipliği ve iptal durumunu tekrar doğrula."""
    payload, width, height = decode_png(image)
    with _slot_directory(root, create=True) as directory, _publication_lease(directory):
        generation = _replace_slot(directory, payload, current)
    return BackgroundCapture(
        root,
        scope,
        root / BACKGROUND_IMAGE_PATH,
        hashlib.sha256(payload).hexdigest(),
        len(payload),
        pid,
        window_id,
        width,
        height,
        generation,
    )


def read_background_image(receipt: BackgroundCapture, root: Path, scope: Scope) -> str:
    """Yalnız mevcut sahibin değişmemiş, sınırlı gözlem baytlarını döndür."""
    if receipt.root != root or receipt.scope != scope:
        raise ValueError(UNAVAILABLE)
    payload = receipt.read_bytes()
    return PNG_PREFIX + base64.b64encode(payload).decode("ascii")


def is_background_slot(root: Path, path: Path) -> bool:
    """Yol takma adları da özel slot denetimine girmek zorundadır."""
    slot = root / BACKGROUND_IMAGE_PATH
    return (
        os.path.normpath(str(path)).casefold() == str(slot).casefold()
        or path.resolve() == slot.resolve()
        or (path.exists() and slot.exists() and path.samefile(slot))
    )
