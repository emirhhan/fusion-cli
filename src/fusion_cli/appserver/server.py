"""stdio döngüsü: satır oku, yönlendir, satır yaz.

Süreç yalnız akış bitince (uygulama stdin'i kapatınca) ya da açıkça
sonlandırılınca durur. Hiçbir bozuk mesaj süreci düşürmez.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

from .bridges import Writer
from .protocol import Reply, Request, decode, encode_error
from .session import AppSession


async def serve(lines: AsyncIterator[str], writer: Writer, *, root: Path, home: Path) -> None:
    """Satır akışını oturuma bağla ve akış bitene kadar sür."""
    session = AppSession(writer, root=root, home=home)
    try:
        async for line in lines:
            message = decode(line)
            if message is None:
                writer(encode_error("çözülemeyen satır"))
                continue
            if isinstance(message, Request):
                await session.handle(message)
                continue
            if isinstance(message, Reply) and not session.resolve_reply(message):
                writer(encode_error("eşleşmeyen cevap kimliği"))
    finally:
        await session.close()


async def _stdin_lines() -> AsyncIterator[str]:
    """stdin'i bloklamadan satır satır oku."""
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        yield line


def _stdout_writer(line: str) -> None:
    """Tek satır yaz ve hemen boşalt; uygulama olayları anında görmeli."""
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except (BrokenPipeError, ValueError):
        # Yazılamayan bir kanala olay biriktirmek bellek sızdırır; sessizce dur.
        raise SystemExit(0) from None


async def run_stdio(root: Path, home: Path) -> None:
    """Gerçek stdio üzerinde protokolü çalıştır."""
    await serve(_stdin_lines(), _stdout_writer, root=root, home=home)
