"""stdio döngüsü: satır oku, yönlendir, satır yaz.

Süreç yalnız akış bitince (uygulama stdin'i kapatınca) ya da açıkça
sonlandırılınca durur. Hiçbir bozuk mesaj süreci düşürmez.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

from ..ui import messages
from .bridges import Writer
from .protocol import Reply, Request, decode, encode_error
from .session import AppSession


def _spawn_request_task(
    session: AppSession,
    request: Request,
    writer: Writer,
    tasks: set[asyncio.Task[None]],
) -> None:
    """İsteği arka planda işle; okuma döngüsü hemen sıradaki satıra geçsin.

    `handle` burada `await` edilirse, motor onay sorduğunda döngü
    `cevap` satırını hiç okuyamaz ve süreç kilitlenir — onu çözecek tek
    yer bu döngüdür. Görev, biten görevlerin referans birikmemesi için
    kümeye eklenir ve bittiğinde kümeden çıkarılır.
    """
    task = asyncio.ensure_future(session.handle(request))
    tasks.add(task)
    task.add_done_callback(lambda finished: _on_request_task_done(finished, tasks, writer))


def _on_request_task_done(
    task: asyncio.Task[None], tasks: set[asyncio.Task[None]], writer: Writer
) -> None:
    """Görevi kümeden çıkar; sessizce yutulan bir istisna varsa hata olayı yaz."""
    tasks.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        writer(encode_error(f"{messages.APP_BACKGROUND_TASK_FAILED}: {error}"))


async def serve(lines: AsyncIterator[str], writer: Writer, *, root: Path, home: Path) -> None:
    """Satır akışını oturuma bağla ve akış bitene kadar sür."""
    session = AppSession(writer, root=root, home=home)
    tasks: set[asyncio.Task[None]] = set()
    try:
        async for line in lines:
            message = decode(line)
            if message is None:
                writer(encode_error(messages.APP_UNDECODABLE_LINE))
                continue
            if isinstance(message, Request):
                _spawn_request_task(session, message, writer, tasks)
                continue
            if isinstance(message, Reply) and not session.resolve_reply(message):
                writer(encode_error(messages.APP_UNMATCHED_REPLY_ID))
    finally:
        # Önce close(): çalışan turu ve bekleyen onay sorularını iptal
        # eder. Sıra tersine çevrilirse — görevleri close()'dan önce
        # bekleseydik — stdin zaten kapandığı için onay bekleyen bir
        # görev asla `cevap` alamaz ve süreç asılı kalırdı. close()
        # iptali tetikledikten sonra görevler bu iptali işleyip kendi
        # sonuçlarını yazar; onları burada bekleyerek düzgün kapanışı
        # garanti ederiz.
        await session.close()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


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
