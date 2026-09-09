"""Streamable HTTP MCP için OAuth 2.1/PKCE tarayıcı akışı."""

from __future__ import annotations

import asyncio
import contextlib
import webbrowser
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata
from pydantic import AnyUrl

from ..config.models import McpServerConfig
from .tokens import KeyringTokenStorage


def validate_remote_mcp_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return
    raise ValueError("Uzak MCP adresi HTTPS olmalı; düz HTTP yalnız loopback için kullanılabilir.")


class LoopbackOAuthCallback:
    """Tek OAuth dönüşü için yalnız loopback üzerinde yaşayan HTTP dinleyici."""

    def __init__(self, *, timeout_seconds: float = 300) -> None:
        self._timeout_seconds = timeout_seconds
        self._server: asyncio.Server | None = None
        self._result: asyncio.Future[tuple[str, str | None]] | None = None
        self.redirect_uri = ""

    async def start(self) -> None:
        if self._server is not None:
            return
        loop = asyncio.get_running_loop()
        self._result = loop.create_future()
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        socket = self._server.sockets[0]
        port = int(socket.getsockname()[1])
        self.redirect_uri = f"http://127.0.0.1:{port}/oauth/callback"

    async def open_redirect(self, url: str) -> None:
        await asyncio.to_thread(webbrowser.open, url, new=1, autoraise=True)

    async def wait_for_code(self) -> tuple[str, str | None]:
        if self._result is None:
            raise RuntimeError("OAuth callback dinleyicisi başlatılmadı.")
        try:
            return await asyncio.wait_for(self._result, timeout=self._timeout_seconds)
        finally:
            await self.close()

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = (await reader.readline()).decode("ascii", errors="replace")
            parts = request_line.split(" ")
            target = parts[1] if len(parts) >= 2 else ""
            parsed = urlparse(target)
            query = parse_qs(parsed.query)
            state = query.get("state", [None])[0]
            error = query.get("error", [None])[0]
            code = query.get("code", [None])[0]
            if parsed.path != "/oauth/callback" or (not code and not error):
                self._set_error(RuntimeError("Geçersiz OAuth callback isteği."))
                status, message = "400 Bad Request", "Geçersiz OAuth dönüşü."
            elif error:
                self._set_error(RuntimeError("OAuth girişi reddedildi veya iptal edildi."))
                status, message = "400 Bad Request", "Fusion bağlantı izni verilmedi."
            else:
                self._set_result((str(code), state))
                status, message = (
                    "200 OK",
                    "Fusion bağlantısı alındı. Bu pencereyi kapatabilirsiniz.",
                )
            body = f"<html><body><h1>Fusion</h1><p>{message}</p></body></html>".encode()
            headers = (
                f"HTTP/1.1 {status}\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode()
            writer.write(headers + body)
            await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _set_result(self, value: tuple[str, str | None]) -> None:
        if self._result is not None and not self._result.done():
            self._result.set_result(value)

    def _set_error(self, error: Exception) -> None:
        if self._result is not None and not self._result.done():
            self._result.set_exception(error)


@dataclass(slots=True)
class OAuthBundle:
    auth: OAuthClientProvider
    callback: LoopbackOAuthCallback
    storage: KeyringTokenStorage


async def oauth_provider_for(config: McpServerConfig) -> OAuthBundle:
    """Yapılandırma için SDK OAuth sağlayıcısı ve yaşam döngüsü kaynaklarını kur."""
    validate_remote_mcp_url(config.url)
    callback = LoopbackOAuthCallback()
    await callback.start()
    storage = KeyringTokenStorage(config.url)
    metadata = OAuthClientMetadata(
        redirect_uris=[AnyUrl(callback.redirect_uri)],
        token_endpoint_auth_method="none",
        scope=" ".join(config.scopes) or None,
        client_name="Fusion Desktop",
    )
    if config.client_id and await storage.get_client_info() is None:
        await storage.set_client_info(
            OAuthClientInformationFull(**metadata.model_dump(), client_id=config.client_id)
        )
    auth = OAuthClientProvider(
        config.url,
        metadata,
        storage,
        redirect_handler=callback.open_redirect,
        callback_handler=callback.wait_for_code,
    )
    return OAuthBundle(auth=auth, callback=callback, storage=storage)
