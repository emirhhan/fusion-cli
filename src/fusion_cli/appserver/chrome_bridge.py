"""Chrome yan paneli ile bu uygulama oturumu arasındaki yerel, izinli köprü.

Sunucu yalnız 127.0.0.1'e bağlanır. Her istek rastgele oturum anahtarını ve
Chrome eklentisi Origin başlığını taşıyabilir; bazı Chrome uzantı isteklerinde
bu başlık bulunmaz. Her istekte rastgele oturum anahtarı zorunludur.
Köprü yalnız açıkken komut kuyruğu yaşar ve kapanınca bekleyen araçları çözer.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from .chrome_feed import panel_item
from .chrome_host import (
    candidate_extension_ids,
    clear_bridge_state,
    install_native_host,
    write_bridge_state,
)

MAX_REQUEST_BYTES = 4_194_304
COMMAND_TIMEOUT_SECONDS = 30
CONNECTION_STALE_SECONDS = 35
#: `/events` uzun yoklamasının bekleme süresi; `/poll` ile aynı: bağlantı canlı sayılır.
EVENTS_WAIT_SECONDS = 20
#: Panelin geri dönüp okuyabileceği son öğe sayısı (panel kapanıp açılabilir).
FEED_LIMIT = 200
#: Panel cevabında izin verilen alanlar: onayda `secim`, soruda `metin`.
ANSWER_FIELDS = ("secim", "metin")
#: İzin kartında gösterilen öğe adının üst sınırı (sayfa `nameOf` da 120'de keser).
ELEMENT_NAME_LIMIT = 120


class ChromeBridge:
    def __init__(
        self,
        on_turn: Callable[[str], Awaitable[dict[str, Any]]] | None = None,
        on_cancel: Callable[[], dict[str, Any]] | None = None,
        on_answer: Callable[[str, dict[str, Any]], bool] | None = None,
    ) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._token = ""
        self._port = 0
        self._connected = False
        self._last_seen = 0.0
        self._on_turn = on_turn
        self._on_cancel = on_cancel
        self._on_answer = on_answer
        #: Yan panelin canlı akışı: adımlar, sorular, tur başı/sonu (bkz. `chrome_feed`).
        self._feed: list[dict[str, Any]] = []
        self._feed_seq = 0
        self._feed_changed = asyncio.Event()
        #: Son `describe` sonuçları (ref → öğe adı); izin kartı adı gösterir.
        self._element_names: dict[str, str] = {}

    @property
    def running(self) -> bool:
        return self._server is not None

    def status(self, *, reveal_token: bool = False) -> dict[str, Any]:
        return {
            "calisiyor": self.running,
            "bagli": (
                self._connected and time.monotonic() - self._last_seen < CONNECTION_STALE_SECONDS
            ),
            "port": self._port if self.running else None,
            "anahtar": self._token if self.running and reveal_token else None,
            # Yeni açılan panel eski turları baştan oynatmasın diye akışın ucu.
            "son": self._feed_seq,
        }

    async def start(self) -> dict[str, Any]:
        if self._server is None:
            self._token = secrets.token_urlsafe(32)
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
            self._port = self._server.sockets[0].getsockname()[1]
            # Eklenti Fusion'ı yerel mesajlaşmayla KENDİSİ bulur (bkz. `chrome_host`);
            # yazılamazsa elle eşleştirme yolu yine çalışır.
            with contextlib.suppress(OSError):
                write_bridge_state(self._port, self._token)
                await asyncio.to_thread(install_native_host, candidate_extension_ids())
        return self.status(reveal_token=True)

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            with contextlib.suppress(OSError):
                clear_bridge_state()
            server.close()
            await server.wait_closed()
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Chrome bağlantısı kapandı."))
        self._pending.clear()
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait({})
        self._connected = False
        self._last_seen = 0.0
        self._token = ""
        self._port = 0
        # Bekleyen `/events` yoklaması kapanışta hemen döner.
        self._feed_changed.set()

    def publish(self, item: dict[str, Any]) -> None:
        """Panel akışına öğe ekle ve bekleyen uzun yoklamaları uyandır."""
        self._feed_seq += 1
        self._feed.append({"seq": self._feed_seq, **item})
        del self._feed[:-FEED_LIMIT]
        changed, self._feed_changed = self._feed_changed, asyncio.Event()
        changed.set()

    def tee(self, writer: Callable[[str], None]) -> Callable[[str], None]:
        """Masaüstü teline yazan fonksiyonu, panelle ilgili satırları da yayanla sar."""

        def write(line: str) -> None:
            writer(line)
            item = panel_item(line)
            if item is not None:
                self.publish(item)

        return write

    async def _events(self, after: object) -> dict[str, Any]:
        start = after if isinstance(after, int) and after >= 0 else 0
        if start >= self._feed_seq:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._feed_changed.wait(), EVENTS_WAIT_SECONDS)
        items = [item for item in self._feed if item["seq"] > start]
        return {"ok": True, "olaylar": items, "son": self._feed_seq}

    def _answer(self, body: dict[str, Any]) -> dict[str, Any]:
        identifier = body.get("id")
        data = body.get("veri")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 64:
            raise ValueError("Soru kimliği geçersiz")
        if not isinstance(data, dict) or self._on_answer is None:
            raise ValueError("Cevap geçersiz")
        clean = {
            key: value[:20_000]
            for key, value in data.items()
            if key in ANSWER_FIELDS and isinstance(value, str)
        }
        return {"ok": self._on_answer(identifier, clean)}

    def element_name(self, ref: object) -> str | None:
        """Tıklamadan önce okunan öğe adı; bilinmiyorsa `None`."""
        return self._element_names.get(ref) if isinstance(ref, str) else None

    def _remember_element(self, args: dict[str, Any], result: dict[str, Any]) -> None:
        veri = result.get("veri")
        ref = args.get("ref")
        if result.get("ok") and isinstance(veri, dict) and isinstance(ref, str):
            name = veri.get("name")
            if isinstance(name, str) and name.strip():
                self._element_names[ref] = name.strip()[:ELEMENT_NAME_LIMIT]

    async def invoke(self, operation: str, args: dict[str, Any]) -> dict[str, Any]:
        if not self.running or not self.status()["bagli"]:
            raise ConnectionError(
                "Chrome eklentisi bağlı değil. Ayarlar > Tarayıcı bölümünden bağla."
            )
        identifier = secrets.token_urlsafe(12)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[identifier] = future
        await self._queue.put({"id": identifier, "islem": operation, "veri": args})
        try:
            result = await asyncio.wait_for(future, COMMAND_TIMEOUT_SECONDS)
        finally:
            self._pending.pop(identifier, None)
        if operation == "describe":
            self._remember_element(args, result)
        return result

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
            if len(head) > 8192:
                await self._reply(writer, 413, {"hata": "Başlık çok uzun."})
                return
            lines = head.decode("latin-1").split("\r\n")
            method, target, _version = lines[0].split(" ", 2)
            headers = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
            headers = {key.lower().strip(): value.strip() for key, value in headers.items()}
            origin = headers.get("origin", "")
            parsed = urlsplit(origin)
            if origin and (parsed.scheme != "chrome-extension" or not parsed.netloc or parsed.path):
                await self._reply(writer, 403, {"hata": "Yalnız Chrome eklentisi erişebilir."})
                return
            if method == "OPTIONS":
                if not origin:
                    await self._reply(writer, 403, {"hata": "Origin gerekli."})
                    return
                await self._reply(writer, 204, {}, origin=origin)
                return
            valid_token = secrets.compare_digest(
                headers.get("authorization", ""), f"Bearer {self._token}"
            )
            if not valid_token:
                await self._reply(writer, 401, {"hata": "Eşleştirme anahtarı geçersiz."}, origin)
                return
            length = int(headers.get("content-length", "0"))
            if length < 0 or length > MAX_REQUEST_BYTES:
                await self._reply(writer, 413, {"hata": "İstek çok büyük."}, origin)
                return
            body = json.loads(await reader.readexactly(length)) if length else {}
            if not isinstance(body, dict):
                raise ValueError("JSON nesnesi bekleniyor")
            self._connected = True
            self._last_seen = time.monotonic()
            if method == "GET" and target == "/status":
                result: dict[str, Any] = self.status()
            elif method == "POST" and target == "/poll":
                try:
                    result = await asyncio.wait_for(self._queue.get(), 20)
                except TimeoutError:
                    result = {}
                while result.get("id") and result["id"] not in self._pending:
                    try:
                        result = self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        result = {}
            elif method == "POST" and target == "/result":
                identifier = body.get("id")
                future = self._pending.get(identifier) if isinstance(identifier, str) else None
                if future is None or future.done():
                    result = {"ok": False, "hata": "Komut bulunamadı."}
                else:
                    future.set_result(body)
                    result = {"ok": True}
            elif method == "POST" and target == "/turn" and self._on_turn is not None:
                prompt = body.get("prompt")
                if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
                    raise ValueError("Geçersiz görev metni")
                result = await self._on_turn(prompt.strip())
            elif method == "POST" and target == "/cancel" and self._on_cancel is not None:
                result = self._on_cancel()
            elif method == "POST" and target == "/events":
                result = await self._events(body.get("after"))
            elif method == "POST" and target == "/answer":
                result = self._answer(body)
            elif method == "POST" and target == "/disconnect":
                self._connected = False
                self._last_seen = 0.0
                result = {"ok": True}
            else:
                await self._reply(writer, 404, {"hata": "Uç bulunamadı."}, origin)
                return
            await self._reply(writer, 200, result, origin)
        except (ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
            await self._reply(writer, 400, {"hata": "Geçersiz istek."})
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    async def _reply(
        writer: asyncio.StreamWriter, status: int, body: dict[str, Any], origin: str = ""
    ) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode()
        headers = [
            f"HTTP/1.1 {status} OK",
            "Content-Type: application/json; charset=utf-8",
            f"Content-Length: {len(payload)}",
            "Connection: close",
        ]
        if origin:
            headers.extend(
                [
                    f"Access-Control-Allow-Origin: {origin}",
                    "Access-Control-Allow-Methods: GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers: Authorization, Content-Type",
                    "Access-Control-Allow-Private-Network: true",
                    "Vary: Origin",
                ]
            )
        writer.write(("\r\n".join(headers) + "\r\n\r\n").encode() + payload)
        await writer.drain()
