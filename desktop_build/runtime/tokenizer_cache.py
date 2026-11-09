"""Stage hash-verified public tiktoken data in the owned build directory.

Origins and SHA256 values are from installed official tiktoken_ext.openai_public.
The cache filenames follow tiktoken.load.read_file_cached's URL-SHA1 convention.
Unlike that downloader, this helper never removes or rewrites the user's cache.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import BinaryIO

MAX_RESOURCE_BYTES = 8 * 1024 * 1024
RESOURCE_TIMEOUT_S = 20
RESOURCE_DEADLINE_S = 60
RESOURCES = (
    (
        "https://openaipublic.blob.core.windows.net/gpt-2/encodings/main/vocab.bpe",
        "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5",
    ),
    (
        "https://openaipublic.blob.core.windows.net/gpt-2/encodings/main/encoder.json",
        "196139668be63f3b5d6574427317ae82f612a97c5d1cdaf36ed2256dbf636783",
    ),
    (
        "https://openaipublic.blob.core.windows.net/encodings/r50k_base.tiktoken",
        "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930",
    ),
    (
        "https://openaipublic.blob.core.windows.net/encodings/p50k_base.tiktoken",
        "94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069",
    ),
    (
        "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
        "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    ),
    (
        "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken",
        "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
    ),
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: object, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        # Reject before urllib opens a second origin, not after reading it.
        return None


def _bounded_read(stream: BinaryIO) -> bytes:
    deadline = time.monotonic() + RESOURCE_DEADLINE_S
    chunks: list[bytes] = []
    total = 0
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError("Public tokenizer build resource deadline exceeded.")
        chunk = stream.read(min(64 * 1024, MAX_RESOURCE_BYTES + 1 - total))
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > MAX_RESOURCE_BYTES:
            raise ValueError("Public tokenizer resource exceeds size limit.")
        chunks.append(chunk)


def _cache_dirs() -> tuple[Path, ...]:
    for name in ("TIKTOKEN_CACHE_DIR", "DATA_GYM_CACHE_DIR"):
        if name in os.environ:
            return (Path(os.environ[name]),) if os.environ[name] else ()
    return (Path(tempfile.gettempdir()) / "data-gym-cache",)


def stage_tokenizer_cache(
    work_directory: str, *, cache_dirs: tuple[Path, ...] | None = None
) -> str:
    """Return staged cache; fail closed before publication on invalid data."""
    work = Path(work_directory)
    work.mkdir(parents=True, exist_ok=True)
    destination = work / "fusion-tokenizer-cache"
    if destination.exists() or destination.is_symlink():
        expected_files = {
            hashlib.sha1(url.encode()).hexdigest(): digest for url, digest in RESOURCES
        }
        if destination.is_symlink() or not destination.is_dir():
            raise ValueError("Invalid tokenizer staging directory.")
        if {path.name for path in destination.iterdir()} != set(expected_files):
            raise ValueError("Staged tokenizer resource coverage mismatch.")
        for name, expected in expected_files.items():
            path = destination / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Invalid staged tokenizer resource.")
            with path.open("rb") as stream:
                if hashlib.sha256(_bounded_read(stream)).hexdigest() != expected:
                    raise ValueError("Staged tokenizer resource hash mismatch.")
        return str(destination)
    caches = _cache_dirs() if cache_dirs is None else cache_dirs
    with tempfile.TemporaryDirectory(prefix="tokenizer-staging-", dir=work) as temporary:
        stage = Path(temporary) / "cache"
        stage.mkdir()
        for url, expected in RESOURCES:
            key = hashlib.sha1(url.encode()).hexdigest()
            data = None
            for directory in caches:
                path = directory / key
                if path.is_file():
                    with path.open("rb") as stream:
                        data = _bounded_read(stream)
                    break
            if data is None:
                opener = urllib.request.build_opener(_NoRedirect())
                with opener.open(url, timeout=RESOURCE_TIMEOUT_S) as response:
                    if response.geturl() != url:
                        raise ValueError("Public tokenizer origin redirect rejected.")
                    data = _bounded_read(response)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("Public tokenizer resource hash mismatch.")
            (stage / key).write_bytes(data)
        stage.rename(destination)
    return str(destination)
