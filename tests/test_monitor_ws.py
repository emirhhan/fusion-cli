"""Claude Monitor `ws` kaynağı: WebSocket metin iletileri olay olur, ayrıca onay ister (#336)."""

from __future__ import annotations

import base64
import hashlib
import socket
import struct
import threading
import time
from pathlib import Path

from fusion_cli.config.permission_rules import PermissionDecision, PermissionRuleSet, parse_rule
from fusion_cli.core.background_events import BackgroundEvents
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import (
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.monitor_tool import monitor
from fusion_cli.tools.task_stop import task_stop

from .fakes import AlwaysReject

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _server_frame(opcode: int, payload: bytes, *, fin: bool = True) -> bytes:
    head = bytes(((0x80 if fin else 0) | opcode,))
    if len(payload) < 126:
        return head + bytes((len(payload),)) + payload
    return head + bytes((126,)) + struct.pack("!H", len(payload)) + payload


def _read_client_frame(conn: socket.socket) -> tuple[int, bytes]:
    head = conn.recv(2)
    length = head[1] & 0x7F
    mask = conn.recv(4)
    data = conn.recv(length) if length else b""
    return head[0] & 0x0F, bytes(b ^ mask[i % 4] for i, b in enumerate(data))


class _Server(threading.Thread):
    """Tek bağlantılık WebSocket sunucusu; el sıkışır, verilen çerçeveleri yollar."""

    def __init__(self, frames: list[bytes], *, keep_open: bool = False) -> None:
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.frames, self.keep_open = frames, keep_open
        self.request = ""
        self.pong: bytes | None = None
        self.release = threading.Event()

    def run(self) -> None:
        conn, _ = self.sock.accept()
        with conn:
            data = b""
            while b"\r\n\r\n" not in data:
                data += conn.recv(4096)
            self.request = data.decode("latin-1")
            key = next(
                line.split(":", 1)[1].strip()
                for line in self.request.split("\r\n")
                if line.lower().startswith("sec-websocket-key")
            )
            accept = base64.b64encode(hashlib.sha1((key + _GUID).encode()).digest()).decode()
            conn.sendall(
                (
                    "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                    f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"
                ).encode()
            )
            for frame in self.frames:
                conn.sendall(frame)
                if frame[0] & 0x0F == 9:
                    self.pong = _read_client_frame(conn)[1]
            if self.keep_open:
                self.release.wait(10)


def _wait_for(events: BackgroundEvents, needle: str, timeout_s: float = 10.0) -> list[str]:
    seen: list[str] = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        seen.extend(events.drain())
        if any(needle in item for item in seen):
            return seen
        time.sleep(0.05)
    raise AssertionError(f"{needle!r} gelmedi: {seen}")


def _context(tmp_path: Path) -> tuple[ToolContext, BackgroundEvents]:
    events = BackgroundEvents()
    return ToolContext(root=tmp_path, background_events=events), events


def test_ws_metin_iletileri_olay_olur_parcali_ileti_birlesir_ping_yanitlanir(tmp_path):
    server = _Server(
        [
            _server_frame(1, "dağıtım başladı".encode()),
            _server_frame(9, b"hb"),
            _server_frame(1, b"ya", fin=False),
            _server_frame(0, b"rim"),
            _server_frame(2, b"\x00\x01"),
            _server_frame(1, b"x" * 300),
            _server_frame(8, struct.pack("!H", 1000)),
        ]
    )
    server.start()
    context, events = _context(tmp_path)

    result = monitor(
        {
            "ws": {"url": f"ws://127.0.0.1:{server.port}/olay?k=1", "protocols": ["v1"]},
            "description": "dağıtım",
        },
        context,
    )

    assert result.ok and "WebSocket izlemesi başladı" in result.output
    seen = _wait_for(events, "izleme bitti")
    bodies = [item.rsplit("] ", 1)[1] for item in seen if "· dağıtım]" in item]
    assert bodies == ["dağıtım başladı", "yarim", "x" * 300, "izleme bitti (sunucu kapattı)."]
    assert server.pong == b"hb"
    assert "GET /olay?k=1 HTTP/1.1" in server.request
    assert "Sec-WebSocket-Protocol: v1" in server.request


def test_ws_izlemesi_task_stop_ile_durur_ve_sure_dolunca_bir_kez_haber_verir(tmp_path):
    server = _Server([_server_frame(1, b"ilk")], keep_open=True)
    server.start()
    context, events = _context(tmp_path)
    started = monitor({"ws": {"url": f"ws://127.0.0.1:{server.port}"}, "description": "a"}, context)
    _wait_for(events, "ilk")

    stopped = task_stop({"task_id": started.structured["taskId"]}, context)

    assert stopped.ok and "durduruldu" in stopped.output
    server.release.set()

    expiring = _Server([], keep_open=True)
    expiring.start()
    monitor(
        {"ws": {"url": f"ws://127.0.0.1:{expiring.port}"}, "description": "b", "timeout_ms": 300},
        context,
    )
    seen = _wait_for(events, "süre doldu")
    assert sum("süre doldu" in item for item in seen) == 1
    expiring.release.set()


def test_ws_girdi_dogrulamasi(tmp_path):
    context, _ = _context(tmp_path)
    both = {"command": "true", "ws": {"url": "ws://x"}, "description": "x"}
    assert not monitor(both, context).ok
    assert not monitor({"ws": {"url": "http://x"}, "description": "x"}, context).ok
    assert not monitor({"ws": "wss://x", "description": "x"}, context).ok
    assert not monitor({"ws": {"url": "ws://x", "protocols": "v1"}, "description": "x"}, context).ok


def test_ws_baglanamazsa_hata_olayi_verir(tmp_path):
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    context, events = _context(tmp_path)

    assert monitor({"ws": {"url": f"ws://127.0.0.1:{port}"}, "description": "c"}, context).ok

    assert any("hatayla bitti" in item for item in _wait_for(events, "hatayla bitti"))


async def test_ws_izlemesi_bash_kurallarindan_gecmez_ayrica_sorulur():
    tool = build_registry().get("monitor")
    args = {"ws": {"url": "wss://ornek.com/akis"}, "description": "akış"}
    bash_allow = PermissionRuleSet((parse_rule("Bash", PermissionDecision.ALLOW, source="t"),))

    request = build_request(tool, args, rules=bash_allow)

    assert not request.pre_allowed and request.risk and "wss://ornek.com/akis" in request.risk
    politika = build_policy(ApprovalMode.AUTO, AlwaysReject())
    assert await politika.decide(request) is Decision.DENIED

    monitor_allow = PermissionRuleSet(
        (parse_rule("Monitor", PermissionDecision.ALLOW, source="t"),)
    )
    assert build_request(tool, args, rules=monitor_allow).pre_allowed
    # Komut izlemesi Bash kuralına tabi kalır.
    command = build_request(tool, {"command": "tail -f x", "description": "x"}, rules=bash_allow)
    assert command.pre_allowed


def test_ws_oturum_izni_adrese_ozel():
    from fusion_cli.engines.agent.approval import _scope

    tool = build_registry().get("monitor")
    first = build_request(tool, {"ws": {"url": "ws://a/1"}, "description": "x"})
    second = build_request(tool, {"ws": {"url": "ws://b/2"}, "description": "x"})

    assert _scope(first) == "monitor:ws:ws://a/1"
    assert _scope(first) != _scope(second)


def test_parcali_ileti_toplam_boyutu_tavani_asinca_hata(monkeypatch):
    """İnceleme bulgusu 4: tavan tek çerçeveye değil birikmiş iletiye uygulanır."""
    import pytest

    from fusion_cli.tools import ws_client

    monkeypatch.setattr(ws_client, "_MAX_MESSAGE", 16)
    for opcode in (1, 2):
        frames = [_server_frame(opcode, b"x" * 10, fin=False)]
        frames += [_server_frame(0, b"y" * 10, fin=False) for _ in range(3)]
        server = _Server(frames, keep_open=True)
        server.start()
        seen: list[str] = []
        try:
            with pytest.raises(ws_client.WebSocketError, match="çok büyük"):
                ws_client.read_text_messages(
                    f"ws://127.0.0.1:{server.port}/", (), seen.append, lambda: False
                )
        finally:
            server.release.set()
        assert seen == []
