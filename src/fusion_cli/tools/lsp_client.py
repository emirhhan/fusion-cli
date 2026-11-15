"""Sınırlı yerel JSON-RPC taşıması ve çağrıya ait LSP süreç temizliği."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass

from ..core.constants import MAX_READ_BYTES, PROCESS_TERMINATE_GRACE_S
from ..core.errors import CleanupFailedError, FusionError
from ..core.process_control import terminate_async_process_tree

HEADER_LIMIT = 8192


class LspProtocolError(FusionError):
    """Sınırlandırılmış LSP iletişimindeki geçersiz yanıt."""


@dataclass(frozen=True, slots=True)
class LspQuery:
    """Adaptörün doğruladığı belge ve konum; sunucu komutu içermez."""

    uri: str
    root_uri: str
    text: str
    language: str
    action: str
    line: int
    character: int


async def close_owned(
    process: asyncio.subprocess.Process, tasks: list[asyncio.Task[object]]
) -> None:
    """Yinelenen iptal de sahip olunan süreç temizliğini yarıda bırakmaz."""

    async def cleanup() -> None:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await _close_process(process)

    owned = asyncio.create_task(cleanup())
    is_cancelled = False
    while not owned.done():
        try:
            await asyncio.shield(owned)
        except asyncio.CancelledError:
            is_cancelled = True
    owned.result()
    if is_cancelled:
        raise asyncio.CancelledError


async def _close_process(process: asyncio.subprocess.Process) -> None:
    """Okunmamış büyük yanıtta da boruyu boşalt; taşıyıcıyı açık bırakma."""

    async def drain() -> None:
        if process.stdout is not None:
            while await process.stdout.read(HEADER_LIMIT):
                continue

    draining = asyncio.create_task(drain())
    if process.stdin is not None:
        process.stdin.close()
    try:
        await terminate_async_process_tree(process)
        try:
            await asyncio.wait_for(draining, timeout=PROCESS_TERMINATE_GRACE_S)
        except TimeoutError:
            raise CleanupFailedError("LSP çıktı borusunun kapandığı doğrulanamadı.") from None
    finally:
        draining.cancel()
        await asyncio.gather(draining, return_exceptions=True)


class _LspClient:
    """Sıralı, sınırlı JSON-RPC; sunucu isteklerine yazma yetkisi vermez."""

    def __init__(self, process: asyncio.subprocess.Process, uri: str) -> None:
        self._process = process
        self._sequence = 0
        self._uri = uri
        self.diagnostics: object = None

    async def send(
        self, method: str, params: object = None, *, request_id: int | None = None
    ) -> None:
        message: dict[str, object] = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            message["id"] = request_id
        await self._write(message)

    async def _write(self, message: Mapping[str, object]) -> None:
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_READ_BYTES * 2:
            raise LspProtocolError("LSP istek boyutu sınırı aşıldı.")
        writer = self._process.stdin
        assert writer is not None
        writer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
        await writer.drain()

    async def receive(self) -> dict[str, object]:
        reader = self._process.stdout
        assert reader is not None
        header = await reader.readuntil(b"\r\n\r\n")
        if len(header) > HEADER_LIMIT:
            raise LspProtocolError("LSP başlık sınırı aşıldı.")
        lengths = [
            line.split(b":", 1)[1].strip()
            for line in header.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        ]
        if len(lengths) != 1 or not lengths[0].isdigit():
            raise LspProtocolError("LSP Content-Length başlığı geçersiz.")
        length = int(lengths[0])
        if not 0 < length <= MAX_READ_BYTES:
            raise LspProtocolError("LSP yanıt boyutu sınırı aşıldı.")
        payload = json.loads(await reader.readexactly(length))
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            raise LspProtocolError("LSP yanıtı bir nesne olmalı.")
        return payload

    async def request(self, method: str, params: object = None) -> object:
        self._sequence += 1
        request_id = self._sequence
        await self.send(method, params, request_id=request_id)
        while True:
            message = await self.receive()
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise LspProtocolError(
                        "LSP sunucusu sorguyu reddetti; yeteneklerini denetleyin."
                    )
                if "result" not in message:
                    raise LspProtocolError("LSP yanıtında sonuç alanı eksik.")
                return message.get("result")
            await self.notification(message)

    async def notification(self, message: dict[str, object]) -> None:
        if "method" in message and "id" in message:
            await self._write(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32601, "message": "İstek desteklenmiyor."},
                }
            )
        elif message.get("method") == "textDocument/publishDiagnostics":
            params = message.get("params")
            if (
                isinstance(params, dict)
                and params.get("uri") == self._uri
                and type(params.get("version")) is int
                and params.get("version") == 1
                and isinstance(params.get("diagnostics"), list)
            ):
                self.diagnostics = params["diagnostics"]


async def exchange(process: asyncio.subprocess.Process, query: LspQuery) -> object:
    client = _LspClient(process, query.uri)
    initialized = await client.request(
        "initialize",
        {
            "processId": None,
            "rootUri": query.root_uri,
            "capabilities": {"textDocument": {"diagnostic": {}}},
        },
    )
    await client.send("initialized", {})
    await client.send(
        "textDocument/didOpen",
        {
            "textDocument": {
                "uri": query.uri,
                "languageId": query.language,
                "version": 1,
                "text": query.text,
            }
        },
    )
    params: dict[str, object] = {
        "textDocument": {"uri": query.uri},
        "position": {"line": query.line, "character": query.character},
    }
    if query.action == "references":
        params["context"] = {"includeDeclaration": True}
    if query.action == "diagnostics":
        capabilities = initialized.get("capabilities", {}) if isinstance(initialized, dict) else {}
        if isinstance(capabilities, dict) and "diagnosticProvider" in capabilities:
            result = await client.request(
                "textDocument/diagnostic", {"textDocument": {"uri": query.uri}}
            )
        else:
            while client.diagnostics is None:
                await client.notification(await client.receive())
            result = {"kind": "full", "items": client.diagnostics}
    else:
        result = await client.request(f"textDocument/{query.action}", params)
    await client.send("textDocument/didClose", {"textDocument": {"uri": query.uri}})
    await client.request("shutdown")
    await client.send("exit")
    await process.wait()
    return result
