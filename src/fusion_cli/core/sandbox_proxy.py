"""Sandbox ağ allowlist'inin yerel HTTP/HTTPS proxy'si (P-010).

Sandbox içindeki komut yalnız bu proxy'ye bağlanabilir (macOS Seatbelt `deny network*`
+ tek port; Linux'ta ayrı ağ ad alanı + Unix soket köprüsü). Proxy `CONNECT host:port`
(HTTPS, git, pip) ve mutlak URI'li düz HTTP isteklerini karşılar; ana makine adı
`domain_allowed` ile denetlenir, izinsizse `403` ve Türkçe gerekçe döner.

İç ağ koruması: izinli bir alan adı genel olmayan bir adrese (127.0.0.1, 10.x, 169.254.x,
CGNAT…) çözülürse bağlanılmaz; yalnız listede AÇIKÇA yazılmış IP ya da `localhost`
iç adrese gidebilir (DNS yeniden bağlama ile allowlist'ten iç ağa sızma olmasın).
Bağlantı denetlenen adrese yapılır, ad ikinci kez çözülmez.

Reddedilen ana makineler sayaçla tutulur; `run_shell` komuttan sonra "ağ engellendi:
x" notunu buradan çıkarır (Codex `--log-denials` karşılığı).
"""

from __future__ import annotations

import contextlib
import logging
import select
import socket
import socketserver
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .network_address import is_public_ip
from .sandbox_policy import SandboxPolicy, domain_allowed, normalize_domain

__all__ = ["DomainProxy", "ProxyDenial"]

_LOG = logging.getLogger(__name__)

#: İstek başlığının en fazla boyutu; daha büyüğü reddedilir.
_MAX_HEADER_BYTES = 65_536
#: Hedefe bağlanma ve boşta bekleme süreleri (sn).
_CONNECT_TIMEOUT_S = 15.0
_IDLE_TIMEOUT_S = 300.0
_CHUNK = 65_536
#: Bellekte tutulan son ret kaydı sayısı.
_MAX_DENIALS = 200
_DEFAULT_PORTS = {"http": 80, "https": 443}

Resolver = Callable[[str, int], list[str]]


@dataclass(frozen=True, slots=True)
class ProxyDenial:
    """Reddedilen tek bağlantı: sıra numarası, ana makine ve gerekçe."""

    serial: int
    host: str
    reason: str


@dataclass(frozen=True, slots=True)
class _Verdict:
    address: str | None
    reason: str


def _resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


class _Handler(socketserver.BaseRequestHandler):
    server: _ProxyServer

    def handle(self) -> None:
        client: socket.socket = self.request
        client.settimeout(_IDLE_TIMEOUT_S)
        try:
            self.server.owner.serve(client)
        except OSError as error:
            _LOG.debug("sandbox proxy bağlantısı kapandı", extra={"hata": str(error)})


class _ProxyServer(socketserver.ThreadingMixIn, socketserver.BaseServer):
    daemon_threads = True
    owner: DomainProxy


class _TcpServer(_ProxyServer, socketserver.TCPServer):
    allow_reuse_address = True


class _UnixServer(_ProxyServer, socketserver.UnixStreamServer):
    pass


class DomainProxy:
    """Alan adı süzgeçli proxy; `start()` ile arka plan thread'inde dinler."""

    def __init__(
        self,
        policy: SandboxPolicy,
        *,
        unix_path: Path | None = None,
        resolver: Resolver = _resolve,
    ) -> None:
        self._policy = policy
        self._unix_path = unix_path
        self._resolver = resolver
        self._lock = threading.Lock()
        self._denials: list[ProxyDenial] = []
        self._serial = 0
        self._server: _ProxyServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._server is None or self._unix_path is not None:
            return 0
        address = self._server.server_address
        return int(address[1]) if isinstance(address, tuple) else 0

    @property
    def unix_path(self) -> Path | None:
        return self._unix_path

    def start(self) -> None:
        if self._server is not None:
            return
        server: _ProxyServer
        if self._unix_path is not None:
            self._unix_path.unlink(missing_ok=True)
            server = _UnixServer(str(self._unix_path), _Handler)
        else:
            server = _TcpServer(("127.0.0.1", 0), _Handler)
        server.owner = self
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="fusion-sandbox-proxy", daemon=True
        )
        self._thread.start()

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=_CONNECT_TIMEOUT_S)
        if self._unix_path is not None:
            self._unix_path.unlink(missing_ok=True)
        self._server = None

    def mark(self) -> int:
        """Şu anki ret sayacı; `denials_since(mark)` sonrakileri verir."""
        with self._lock:
            return self._serial

    def denials_since(self, mark: int) -> list[ProxyDenial]:
        with self._lock:
            return [item for item in self._denials if item.serial > mark]

    # --- bağlantı ---------------------------------------------------------- #

    def serve(self, client: socket.socket) -> None:
        head, rest = _read_head(client)
        if head is None:
            return
        request_line, _, header_text = head.partition("\r\n")
        parts = request_line.split(" ")
        if len(parts) != 3:
            _reply(client, 400, "Geçersiz istek satırı.")
            return
        method, target, version = parts
        if method.upper() == "CONNECT":
            host, port = _split_host_port(target, 443)
            upstream = self._open(client, host, port)
            if upstream is not None:
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                _relay(client, upstream, rest)
            return
        scheme, host, port, path = _split_url(target)
        if scheme != "http" or not host:
            _reply(client, 400, "Proxy yalnız CONNECT ve mutlak http:// isteklerini karşılar.")
            return
        upstream = self._open(client, host, port)
        if upstream is None:
            return
        headers = "\r\n".join(
            line for line in header_text.split("\r\n") if not line.lower().startswith("proxy-")
        )
        upstream.sendall(f"{method} {path} {version}\r\n{headers}\r\n\r\n".encode("latin-1"))
        _relay(client, upstream, rest)

    def _open(self, client: socket.socket, host: str, port: int) -> socket.socket | None:
        verdict = self._check(host, port)
        if verdict.address is None:
            self._deny(host, verdict.reason)
            _reply(client, 403, f"Fusion sandbox: {host} engellendi ({verdict.reason}).")
            return None
        try:
            return socket.create_connection((verdict.address, port), timeout=_CONNECT_TIMEOUT_S)
        except OSError as error:
            _reply(client, 502, f"Fusion sandbox: {host}:{port} bağlanılamadı ({error}).")
            return None

    def _check(self, host: str, port: int) -> _Verdict:
        """İzinliyse bağlanılacak (denetlenmiş) adres, değilse gerekçe."""
        normalized = normalize_domain(host)
        if normalized is None or not domain_allowed(normalized, self._policy):
            return _Verdict(None, "alan adı sandbox.allowed_domains listesinde değil")
        try:
            addresses = self._resolver(normalized, port)
        except OSError as error:
            return _Verdict(None, f"ad çözülemedi: {error}")
        if not addresses:
            return _Verdict(None, "ad çözülemedi")
        literal = normalized == "localhost" or _is_ip(normalized)
        explicit = literal and normalized in self._policy.allowed_domains
        if not explicit and not all(is_public_ip(address) for address in addresses):
            return _Verdict(
                None, "iç ağ adresine çözülüyor; yalnız listede açıkça yazılmış IP/localhost izinli"
            )
        return _Verdict(addresses[0], "")

    def _deny(self, host: str, reason: str) -> None:
        with self._lock:
            self._serial += 1
            self._denials.append(ProxyDenial(self._serial, host, reason))
            del self._denials[:-_MAX_DENIALS]


def _is_ip(text: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET6 if ":" in text else socket.AF_INET, text)
    except OSError:
        return False
    return True


def _read_head(client: socket.socket) -> tuple[str | None, bytes]:
    buffer = b""
    while b"\r\n\r\n" not in buffer:
        chunk = client.recv(_CHUNK)
        if not chunk:
            return None, b""
        buffer += chunk
        if len(buffer) > _MAX_HEADER_BYTES:
            _reply(client, 431, "İstek başlığı çok büyük.")
            return None, b""
    head, _, rest = buffer.partition(b"\r\n\r\n")
    return head.decode("latin-1"), rest


def _split_host_port(text: str, default_port: int) -> tuple[str, int]:
    if text.startswith("["):
        host, _, tail = text[1:].partition("]")
        port_text = tail.removeprefix(":")
    else:
        host, _, port_text = text.rpartition(":") if ":" in text else (text, "", "")
    try:
        port = int(port_text) if port_text else default_port
    except ValueError:
        port = default_port
    return host, port


def _split_url(target: str) -> tuple[str, str, int, str]:
    scheme, sep, remainder = target.partition("://")
    if not sep:
        return "", "", 0, ""
    authority, slash, path = remainder.partition("/")
    authority = authority.rpartition("@")[2]
    host, port = _split_host_port(authority, _DEFAULT_PORTS.get(scheme.lower(), 80))
    return scheme.lower(), host, port, f"/{path}" if slash else "/"


def _reply(client: socket.socket, status: int, message: str) -> None:
    body = (message + "\n").encode("utf-8")
    head = (
        f"HTTP/1.1 {status} Fusion Sandbox\r\nContent-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    ).encode("ascii")
    with contextlib.suppress(OSError):
        client.sendall(head + body)


def _relay(client: socket.socket, upstream: socket.socket, pending: bytes) -> None:
    """İki yönlü kopyalama; taraflardan biri kapanınca ya da boşta kalınca biter."""
    with upstream:
        if pending:
            upstream.sendall(pending)
        sockets = [client, upstream]
        while True:
            readable, _, _ = select.select(sockets, [], [], _IDLE_TIMEOUT_S)
            if not readable:
                return
            for source in readable:
                data = source.recv(_CHUNK)
                if not data:
                    return
                (upstream if source is client else client).sendall(data)
