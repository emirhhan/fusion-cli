"""Paket 10: tarayıcı açmadan gerçek kayıt işlevinin bayt doğrulama kabulü."""

from __future__ import annotations

import base64
import struct
import zlib
from datetime import datetime
from pathlib import Path

from fusion_cli.providers.web_image import save_images


def _png() -> bytes:
    """Tek piksellik geçerli RGB PNG örneğini yalnız standart kitaplıkla kur."""

    def chunk(kind: bytes, content: bytes) -> bytes:
        checksum = zlib.crc32(kind + content)
        return struct.pack("!I", len(content)) + kind + content + struct.pack("!I", checksum)

    header = struct.pack("!IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def test_task10_valid_png_bytes_are_saved(tmp_path: Path) -> None:
    image_bytes = _png()
    saved = save_images(
        [{"b64": base64.b64encode(image_bytes).decode("ascii"), "w": 1, "h": 1}],
        tmp_path,
        now=datetime(2026, 1, 1),
    )
    assert len(saved) == 1
    assert saved[0].path.read_bytes() == image_bytes
    assert (saved[0].width, saved[0].height) == (1, 1)


def test_task10_login_html_is_not_published(tmp_path: Path) -> None:
    payload = base64.b64encode(b"<!doctype html><title>Login</title>").decode("ascii")
    assert save_images([{"b64": payload, "w": 1, "h": 1}], tmp_path) == []
    assert list(tmp_path.iterdir()) == []


def test_task10_png_prefix_with_html_is_not_published(tmp_path: Path) -> None:
    payload = base64.b64encode(b"\x89PNG<!doctype html><title>Login</title>").decode("ascii")
    assert save_images([{"b64": payload, "w": 1, "h": 1}], tmp_path) == []
    assert list(tmp_path.iterdir()) == []


def test_task10_decoded_dimensions_override_dom_claim(tmp_path: Path) -> None:
    saved = save_images(
        [{"b64": base64.b64encode(_png()).decode("ascii"), "w": 1024, "h": 768}],
        tmp_path,
    )
    assert len(saved) == 1
    assert (saved[0].width, saved[0].height) == (1, 1)


def test_task10_same_second_generation_preserves_both_assets(tmp_path):
    stamp = datetime(2026, 1, 1)
    payload = {"b64": base64.b64encode(_png()).decode("ascii")}
    first = save_images([payload], tmp_path, now=stamp)
    second = save_images([payload], tmp_path, now=stamp)
    assert first[0].path != second[0].path
    assert first[0].path.read_bytes() == second[0].path.read_bytes() == _png()


def test_task10_parallel_generation_has_unique_complete_assets(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    payload = {"b64": base64.b64encode(_png()).decode("ascii")}
    stamp = datetime(2026, 1, 1)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: save_images([payload], tmp_path, now=stamp), range(4)))
    paths = [result[0].path for result in results]
    assert len(set(paths)) == 4
    assert all(path.read_bytes() == _png() for path in paths)
    assert not list(tmp_path.glob("*.tmp"))
