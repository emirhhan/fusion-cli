"""Unix soketinden loopback TCP portuna aktarıcı (Linux, kullanıcının kendi proxy'si; #350).

Claude `network.httpProxyPort` / `socksProxyPort` sandbox'ı kullanıcının proxy'sine yönlendirir.
Linux'ta komut ayrı ağ ad alanındadır ve ana makinenin `127.0.0.1:<port>`'una ulaşamaz;
Fusion bir Unix soketi açar, her bağlantıyı o porta aktarır, `socat` köprüsü soketi ad
alanının içine taşır (Fusion'ın kendi proxy'siyle aynı düzen). Süzme kullanıcının proxy'sindedir.
"""

from __future__ import annotations

import contextlib
import socket
import socketserver
import threading
from pathlib import Path

from .sandbox_proxy import relay

__all__ = ["UnixForwarder"]

_CONNECT_TIMEOUT_S = 15.0
_SHUTDOWN_POLL_S = 0.05


class _Handler(socketserver.BaseRequestHandler):
    server: _Server

    def handle(self) -> None:
        client: socket.socket = self.request
        try:
            upstream = socket.create_connection(
                ("127.0.0.1", self.server.target_port), timeout=_CONNECT_TIMEOUT_S
            )
        except OSError:
            return
        with contextlib.suppress(OSError):
            relay(client, upstream, b"")


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    target_port: int


class UnixForwarder:
    """`unix_path` → `127.0.0.1:port`; `start()` arka plan iş parçacığında dinler."""

    def __init__(self, unix_path: Path, port: int) -> None:
        self.unix_path, self.port = unix_path, port
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.unix_path.unlink(missing_ok=True)
        server = _Server(str(self.unix_path), _Handler)
        server.target_port = self.port
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": _SHUTDOWN_POLL_S},
            name="fusion-sandbox-forward",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self.unix_path.unlink(missing_ok=True)
