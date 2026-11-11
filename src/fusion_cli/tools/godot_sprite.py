"""Install a bundled CC0 player sprite without an inference or download step."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, suppress
from importlib.resources import files
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from ..config.paths import base_data_dir
from ..core.file_lease import FileLease
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .files import writable_path

_SOURCE_ROOT = (
    "https://github.com/godotengine/godot-demo-projects/blob/"
    "b761b4cd5718a7118f2c95eb55f181d0a5f004f1/2d/dodge_the_creeps"
)
_SOURCE = {
    "source_url": f"{_SOURCE_ROOT}/art/playerGrey_walk1.png",
    "license": "CC0-1.0",
    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
    "license_evidence_url": f"{_SOURCE_ROOT}/README.md#license",
    "author": "Kenney",
}
_SPRITE_SHA256 = "57d14c3d2faf19a53e1e65b1922f5a71d9feae1acb99def6bc1f82a1bfcf2f54"


_MANIFEST = "ASSETS.json"
_MAX_MANIFEST = 1_048_576


def add_godot_sprite(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Add one stock PNG and its provenance to an existing Godot project."""
    root = context.root.resolve()
    raw = args.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return ToolResult.failure("Proje içinde .png uzantılı bir hedef belirt.")
    raw = raw.strip()
    destination = root / raw
    if (
        destination.suffix.casefold() != ".png"
        or not destination.is_relative_to(root)
        or ".." in destination.parts
        or raw.startswith(("-", "$", "~", "'", '"'))
    ):
        return ToolResult.failure("Proje içinde .png uzantılı bir hedef belirt.")
    relative = destination.relative_to(root)
    manifest = destination.with_name(_MANIFEST)
    try:
        writable_path(context, str(destination))
        writable_path(context, str(manifest))
        sprite = files("fusion_cli.tools").joinpath("assets/godot-player.png").read_bytes()
        if hashlib.sha256(sprite).hexdigest() != _SPRITE_SHA256:
            return ToolResult.failure("Paketli Godot görselinin bütünlük denetimi başarısız.")
        with _lease(), _directory(root, relative.parent.parts) as directory:
            _add_locked(context, root, directory, destination, manifest, sprite)
    except (OSError, ValueError) as exc:
        return ToolResult.failure(f"Godot görseli eklenemedi: {exc}")
    return ToolResult(
        f"{relative.as_posix()} hazır. Kaynak ve CC0-1.0 lisansı "
        f"{manifest.relative_to(root).as_posix()} içinde kayıtlı."
    )


@contextmanager
def _lease() -> Iterator[None]:
    lease = FileLease(base_data_dir() / "godot-sprite.lock")
    deadline = monotonic() + 2.0
    while not lease.try_acquire():
        if monotonic() >= deadline:
            raise OSError("Başka bir Godot varlık kaydı yazılıyor.")
        sleep(0.02)
    try:
        yield
    finally:
        lease.close()


@contextmanager
def _directory(root: Path, parts: tuple[str, ...]) -> Iterator[int]:
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        raise OSError("Bu sistem güvenli Godot varlık yazımını desteklemiyor.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    with ExitStack() as cleanup:
        directory = os.open(root, flags)
        cleanup.callback(os.close, directory)
        marker = os.stat("project.godot", dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(marker.st_mode):
            raise ValueError("Proje kökünde gerçek bir project.godot bulunamadı.")
        for part in parts:
            with suppress(FileExistsError):
                os.mkdir(part, dir_fd=directory)
            directory = os.open(part, flags, dir_fd=directory)
            cleanup.callback(os.close, directory)
        yield directory


def _read(directory: int, name: str, max_bytes: int) -> bytes | None:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError(f"Dosya türü veya boyutu uygun değil: {name}")
        value = stream.read(max_bytes + 1)
    if len(value) > max_bytes:
        raise ValueError(f"Dosya boyutu uygun değil: {name}")
    return value


def _publish(
    directory: int,
    name: str,
    content: bytes,
    *,
    previous: bytes | None,
) -> tuple[int, int]:
    staging = f".fusion-sprite-{uuid4().hex}.tmp"
    mode = 0o666
    if previous is not None:
        mode = stat.S_IMODE(os.stat(name, dir_fd=directory, follow_symlinks=False).st_mode)
    descriptor = os.open(
        staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=directory
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if previous is not None:
                os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            identity = os.fstat(stream.fileno())
        if previous is None:
            os.link(
                staging, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False
            )
        else:
            if _read(directory, name, _MAX_MANIFEST) != previous:
                raise ValueError("ASSETS.json değişti. Güncel kayıtla yeniden dene.")
            os.replace(staging, name, src_dir_fd=directory, dst_dir_fd=directory)
        return identity.st_dev, identity.st_ino
    finally:
        with suppress(FileNotFoundError):
            os.unlink(staging, dir_fd=directory)


def _add_locked(
    context: ToolContext,
    root: Path,
    directory: int,
    destination: Path,
    manifest: Path,
    sprite: bytes,
) -> None:
    before = _read(directory, _MANIFEST, _MAX_MANIFEST)
    document = json.loads(before) if before is not None else {"assets": []}
    records = document.get("assets") if isinstance(document, dict) else document
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise ValueError("ASSETS.json bir varlık listesi içermeli.")

    name = destination.name
    entry = {"path": name, **_SOURCE}
    matches = [
        item
        for item in records
        if (item.get("path") or item.get("file"))
        in (name, destination.relative_to(root).as_posix())
    ]
    if matches and matches != [entry]:
        raise ValueError("ASSETS.json içinde bu hedef için farklı bir kayıt var.")
    existing = _read(directory, name, len(sprite))
    if existing is not None and existing != sprite:
        raise ValueError(f"Mevcut PNG korunuyor: {destination.relative_to(root)}")

    created = None
    published_manifest = None
    updated = None
    if not matches:
        records.append(entry)
        updated = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()
        if len(updated) > _MAX_MANIFEST:
            raise ValueError("Yeni ASSETS.json izin verilen boyutu aşar.")
    try:
        if existing is None:
            created = _publish(directory, name, sprite, previous=None)
        if updated is not None:
            published_manifest = _publish(directory, _MANIFEST, updated, previous=before)
        if _read(directory, name, len(sprite)) != sprite or (
            created is not None and not _owned(directory, name, created, sprite)
        ):
            raise ValueError("PNG ekleme sırasında değişti.")
        if (
            updated is not None
            and published_manifest is not None
            and not _owned(directory, _MANIFEST, published_manifest, updated)
        ):
            raise ValueError("ASSETS.json ekleme sırasında değişti.")
    except (OSError, ValueError):
        if updated is not None and published_manifest is not None:
            with suppress(OSError, ValueError):
                if _owned(directory, _MANIFEST, published_manifest, updated):
                    if before is None:
                        os.unlink(_MANIFEST, dir_fd=directory)
                    else:
                        _publish(directory, _MANIFEST, before, previous=updated)
        if created is not None:
            with suppress(OSError, ValueError):
                if _owned(directory, name, created, sprite):
                    os.unlink(name, dir_fd=directory)
        raise

    if created is not None:
        context.changes.record_written(destination, None, sprite)
        context.touched.add(destination)
    if updated is not None:
        context.changes.record_written(manifest, before, updated)
        context.touched.add(manifest)


def _owned(directory: int, name: str, identity: tuple[int, int], expected: bytes) -> bool:
    current = os.stat(name, dir_fd=directory, follow_symlinks=False)
    return (current.st_dev, current.st_ino) == identity and _read(
        directory, name, len(expected)
    ) == expected
