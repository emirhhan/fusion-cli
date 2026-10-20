"""Pencereye bağlı Swift yardımcısını derlenmiş özel önbellekten çalıştır."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

NATIVE_TIMEOUT_S = 30
NATIVE_COMPILE_TIMEOUT_S = 60
NATIVE_OUTPUT_LIMIT = 17_000_000
BUNDLED_HELPER_NAME = "fusion-desktop-host"


def unavailable(message: str) -> dict[str, object]:
    """Desteklenmeyen yerel işlemi açık sonuçla döndür."""
    return {"ok": False, "status": "unavailable", "metin": message}


async def _process(arguments: list[str], wait_seconds: int, payload: bytes = b"") -> bytes:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(payload), wait_seconds)
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    if process.returncode or len(stdout) > NATIVE_OUTPUT_LIMIT:
        raise OSError("Yerel yardımcı çalışmadı veya çıktı sınırı aşıldı.")
    return stdout


def _data_directory() -> Path:
    return Path(__file__).parent / "data"


def _bundled_executable(directory: Path) -> Path | None:
    binary = directory / BUNDLED_HELPER_NAME
    try:
        metadata = binary.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or not metadata.st_mode & stat.S_IXUSR:
        raise OSError("Paketli masaüstü yardımcısı geçerli bir çalıştırılabilir dosya değil.")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise OSError("Paketli masaüstü yardımcısının yazma izinleri güvenli değil.")
    return binary


async def _executable() -> Path:
    directory = _data_directory()
    bundled = _bundled_executable(directory)
    if bundled is not None:
        return bundled
    if getattr(sys, "frozen", False):
        raise OSError("Paketli masaüstü yardımcısı eksik; Fusion paketini yeniden kur.")
    source = directory / "desktop_host.swift"
    fingerprint = hashlib.sha256(await asyncio.to_thread(source.read_bytes)).hexdigest()
    cache = Path(tempfile.gettempdir()) / f"fusion-desktop-{os.getuid()}"
    cache.mkdir(mode=0o700, exist_ok=True)
    metadata = cache.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise OSError("Yerel yardımcı önbelleğinin sahibi geçersiz.")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise OSError("Yerel yardımcı önbelleği özel değil.")
    binary = cache / fingerprint
    if binary.exists():
        if binary.is_symlink() or binary.stat().st_uid != os.getuid():
            raise OSError("Yerel yardımcı dosyasının sahibi geçersiz.")
        return binary
    # Ayrı geçici dosya sayesinde eşzamanlı ilk çağrılar eksik ikili çalıştırmaz.
    with tempfile.TemporaryDirectory(dir=cache) as staging_directory:
        staging = Path(staging_directory) / "desktop-host"
        await _process(
            ["/usr/bin/swiftc", str(source), "-o", str(staging)], NATIVE_COMPILE_TIMEOUT_S
        )
        staging.replace(binary)
    return binary


class SwiftDesktop:
    """Arka plan yakalama ve AX işlemleri genel ekran girdisine dönüşmez."""

    async def invoke(self, operation: str, target: dict[str, object]) -> dict[str, object]:
        if sys.platform != "darwin":
            return unavailable("Yerel pencere dock'u yalnız macOS destekliyor.")
        if operation not in {"list", "focus", "snapshot", "inspect", "action"}:
            return unavailable("Yerel hedef işlemi desteklenmiyor.")
        if operation != "list" and not (
            target.get("kind") == "window"
            and type(target.get("id")) is int
            and type(target.get("pid")) is int
            and int(str(target["id"])) > 0
            and int(str(target["pid"])) > 0
        ):
            return unavailable("Pencere ve süreç kimliği gerekli.")
        try:
            binary = await _executable()
            arguments = [str(binary), operation]
            if operation != "list":
                arguments += [str(target["id"]), str(target["pid"])]
            payload = json.dumps(target.get("request", {})).encode()
            result = json.loads(await _process(arguments, NATIVE_TIMEOUT_S, payload))
            if isinstance(result, dict):
                return result
        except (OSError, TimeoutError, ValueError):
            return unavailable(
                "Yerel yardımcıya erişilemedi; Fusion kurulumunu ve macOS izinlerini kontrol et."
            )
        return unavailable("Yerel yardımcı yanıtı geçersiz.")
