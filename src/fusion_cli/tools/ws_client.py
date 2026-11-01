"""Yalnız okuyan, stdlib'li küçük WebSocket istemcisi (RFC 6455; `monitor` ws kaynağı, #336).

Claude Code Monitor `ws: {url, protocols?}` ile bir WebSocket açar ve her metin çerçevesini
olay olarak verir. Bağımlılık listesinde WebSocket istemcisi olmadığından burada yalnız
gereken kadarı yazıldı: `ws://` / `wss://` el sıkışması (`Sec-WebSocket-Accept` doğrulanır),
parçalı metin iletisi, ping'e pong, kapanış. İstemci çerçeveleri RFC gereği maskelenir.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import socket
import ssl
import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..core.errors import FusionError

__all__ = ["WebSocketError", "WsTarget", "parse_ws_url", "read_text_messages"]

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_CONNECT_TIMEOUT_S = 15.0
#: Okuma zaman aşımı: bu aralıkla `should_stop` yoklanır.
_POLL_S = 0.5
_MAX_HEAD = 65_536
#: Tek iletinin en büyük boyutu (bellek tavanı).
_MAX_MESSAGE = 1_048_576
_OP_CONT, _OP_TEXT, _OP_BINARY, _OP_CLOSE, _OP_PING, _OP_PONG = 0, 1, 2, 8, 9, 10


class WebSocketError(FusionError):
    """WebSocket bağlantısı kurulamadı ya da protokol bozuldu."""


@dataclass(frozen=True, slots=True)
class WsTarget:
    """Çözümlenmiş adres: şema, ana makine, port, yol (+sorgu)."""

    secure: bool
    host: str
    port: int
    path: str
    url: str


def parse_ws_url(url: str) -> WsTarget:
    """`ws://` ya da `wss://` adresini çözümle; başka şema hata."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("ws", "wss") or not parts.hostname:
        raise WebSocketError("ws.url ws:// ya da wss:// ile başlayan bir adres olmalı.")
    secure = parts.scheme == "wss"
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return WsTarget(secure, parts.hostname, parts.port or (443 if secure else 80), path, url)


def _accept_key(key: str) -> str:
    digest = hashlib.sha1((key + _GUID).encode("ascii")).digest()  # RFC 6455 gereği SHA-1
    return base64.b64encode(digest).decode("ascii")


def _handshake(sock: socket.socket, target: WsTarget, protocols: Sequence[str]) -> bytes:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    host = target.host if target.port in (80, 443) else f"{target.host}:{target.port}"
    lines = [
        f"GET {target.path} HTTP/1.1",
        f"Host: {host}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
    ]
    if protocols:
        lines.append(f"Sec-WebSocket-Protocol: {', '.join(protocols)}")
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        chunk = sock.recv(4096)
        if not chunk or len(buffer) > _MAX_HEAD:
            raise WebSocketError("WebSocket el sıkışması yanıtı alınamadı.")
        buffer += chunk
    head, _, rest = buffer.partition(b"\r\n\r\n")
    status, *header_lines = head.decode("latin-1").split("\r\n")
    if " 101 " not in f"{status} ":
        raise WebSocketError(f"WebSocket yükseltmesi reddedildi: {status.strip()}")
    headers = {
        name.strip().lower(): value.strip()
        for name, _, value in (line.partition(":") for line in header_lines)
    }
    if headers.get("sec-websocket-accept") != _accept_key(key):
        raise WebSocketError("Sunucunun Sec-WebSocket-Accept değeri geçersiz.")
    return rest


def _open(target: WsTarget, context: ssl.SSLContext | None) -> socket.socket:
    try:
        raw = socket.create_connection((target.host, target.port), timeout=_CONNECT_TIMEOUT_S)
    except OSError as error:
        raise WebSocketError(f"{target.url} bağlanılamadı: {error}") from error
    if not target.secure:
        return raw
    tls = context or ssl.create_default_context()
    try:
        return tls.wrap_socket(raw, server_hostname=target.host)
    except (OSError, ssl.SSLError) as error:
        raw.close()
        raise WebSocketError(f"{target.url} TLS kurulamadı: {error}") from error


def _frame(opcode: int, payload: bytes) -> bytes:
    """Maskeli istemci çerçevesi (kontrol çerçeveleri ≤125 bayt)."""
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes((0x80 | opcode, 0x80 | len(payload))) + mask + masked


class _Reader:
    """Soketten tam bayt sayısı okur; zaman aşımında `should_stop`'u yoklar."""

    def __init__(
        self, sock: socket.socket, pending: bytes, should_stop: Callable[[], bool]
    ) -> None:
        self._sock, self._buffer, self._should_stop = sock, pending, should_stop

    def take(self, count: int) -> bytes | None:
        while len(self._buffer) < count:
            if self._should_stop():
                return None
            try:
                chunk = self._sock.recv(65_536)
            except TimeoutError:
                continue
            if not chunk:
                return None
            self._buffer += chunk
        data, self._buffer = self._buffer[:count], self._buffer[count:]
        return data


def _next_frame(reader: _Reader) -> tuple[bool, int, bytes] | None:
    head = reader.take(2)
    if head is None:
        return None
    fin, opcode, length = bool(head[0] & 0x80), head[0] & 0x0F, head[1] & 0x7F
    masked = bool(head[1] & 0x80)
    if length in (126, 127):
        extended = reader.take(2 if length == 126 else 8)
        if extended is None:
            return None
        length = struct.unpack("!H" if len(extended) == 2 else "!Q", extended)[0]
    if length > _MAX_MESSAGE:
        raise WebSocketError("WebSocket iletisi çok büyük (1 MB tavanı).")
    mask = reader.take(4) if masked else b""
    payload = reader.take(length) if length else b""
    if mask is None or payload is None:
        return None
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return fin, opcode, payload


def read_text_messages(
    url: str,
    protocols: Sequence[str],
    on_message: Callable[[str], None],
    should_stop: Callable[[], bool],
    *,
    tls_context: ssl.SSLContext | None = None,
) -> str:
    """Bağlan; her metin iletisini `on_message`'a ver. Bitiş nedenini döndürür."""
    target = parse_ws_url(url)
    sock = _open(target, tls_context)
    with sock:
        pending = _handshake(sock, target, protocols)
        sock.settimeout(_POLL_S)
        reader, parts, kind = _Reader(sock, pending, should_stop), [], _OP_TEXT
        while True:
            frame = _next_frame(reader)
            if frame is None:
                return "durduruldu" if should_stop() else "bağlantı kapandı"
            fin, opcode, payload = frame
            if opcode == _OP_PING:
                sock.sendall(_frame(_OP_PONG, payload[:125]))
                continue
            if opcode == _OP_CLOSE:
                with contextlib.suppress(OSError):
                    sock.sendall(_frame(_OP_CLOSE, payload[:2]))
                return "sunucu kapattı"
            if opcode in (_OP_TEXT, _OP_BINARY):
                parts, kind = [payload], opcode
            elif opcode == _OP_CONT:
                parts.append(payload)
            if fin and opcode in (_OP_TEXT, _OP_BINARY, _OP_CONT) and kind == _OP_TEXT:
                on_message(b"".join(parts).decode("utf-8", errors="replace"))
            if fin:
                parts = []
