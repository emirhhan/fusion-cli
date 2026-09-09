"""Kamuya açık ikili kaynakları proje içine, baytları değiştirmeden indirir."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urljoin

import httpx

from ..core.constants import MAX_DOWNLOAD_BYTES, MAX_WEB_REDIRECTS, WEB_TIMEOUT_S
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .files import display_path, resolve_path
from .web import url_block_reason


async def _download_bytes(url: str, context: ToolContext) -> bytes:
    """Her hedefi denetle; sıkıştırılmış yanıtın açılan baytlarını da sınırla."""
    current = url
    async with httpx.AsyncClient(follow_redirects=False, timeout=WEB_TIMEOUT_S) as client:
        for _ in range(MAX_WEB_REDIRECTS + 1):
            reason = await asyncio.to_thread(url_block_reason, current)
            if reason:
                raise ValueError(reason)
            if context.cancelled.is_set():
                raise InterruptedError("İndirme iptal edildi.")
            async with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Yönlendirme hedefi boş.")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if context.cancelled.is_set():
                        raise InterruptedError("İndirme iptal edildi.")
                    if len(body) + len(chunk) > MAX_DOWNLOAD_BYTES:
                        raise ValueError(f"İndirme {MAX_DOWNLOAD_BYTES} bayt sınırını aşıyor.")
                    body.extend(chunk)
                if not body:
                    raise ValueError("Kaynak boş dosya döndürdü.")
                return bytes(body)
    raise ValueError(f"En fazla {MAX_WEB_REDIRECTS} yönlendirme aşıldı.")


def _save_new(path: Path, content: bytes, context: ToolContext) -> None:
    """Tamamlanan dosyayı atomik yayınla; mevcut dosyanın üzerine yazma."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        if context.cancelled.is_set():
            raise InterruptedError("İndirme iptal edildi.")
        os.link(temporary, path)
        context.changes.record_created(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def download_file(args: ToolArgs, context: ToolContext) -> ToolResult:
    """İndirilen dosyanın gerçek boyutunu ve SHA-256 özetini kanıt olarak döndür."""
    path = resolve_path(context, require_str(args, "path"))
    if path.exists():
        return ToolResult.failure("Hedef dosya zaten var; üzerine yazılmadı. Yeni bir yol seç.")
    url = require_str(args, "url")
    try:
        content = await _download_bytes(url, context)
        _save_new(path, content, context)
    except (httpx.HTTPError, OSError, ValueError) as error:
        return ToolResult.failure(f"Dosya indirilemedi: {error}")
    context.touched.add(path)
    digest = hashlib.sha256(content).hexdigest()
    return ToolResult(
        f"İndirildi: {display_path(context, path)}\n"
        f"Boyut: {len(content)} bayt\nSHA-256: {digest}\n"
        "Kaynağın lisansını ayrıca doğrula ve ASSETS.json içine kaydet. "
        "Dosya indirilmiş olması lisans veya dosya biçimi doğrulaması değildir."
    )
