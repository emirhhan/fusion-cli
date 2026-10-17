"""Görev servisinin arkasındaki yürütücü sözleşmesi ve `AppSession` bağdaştırıcısı."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from ..appserver.protocol import Request

EventSink = Callable[[str, dict[str, Any]], None]


class TaskBackend(Protocol):
    """Görevi çalıştıran taraf; olayları `sink` ile bildirir."""

    async def start(self, run_id: str, prompt: str, sink: EventSink) -> None:
        """Görevi başlat; bittiğinde dönmeden önce terminal olayı yaz."""
        ...

    def prepare_run(self, run_id: str, options: dict[str, Any]) -> None:
        """Göreve özgü bağlam: `chat_id`, `root`, `tier`, `attachments`; `start` öncesi."""
        ...

    async def call(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Oturum protokolüne tek seferlik istek (sohbet listesi, geçmiş, model, zamanlama)."""
        ...

    async def cancel(self, run_id: str) -> bool: ...

    async def answer(self, question_id: str, answer: dict[str, Any]) -> bool: ...

    def pause_supported(self) -> bool: ...

    def kits(self) -> list[dict[str, Any]]: ...


class AppSessionBackend:
    """Var olan `AppSession` oturumunu sürer; ikinci bir ajan motoru değildir.

    Oturum satır tabanlı bir yazıcıyla konuşur; buradaki yazıcı satırları ayrıştırıp
    ilgili görev sink'ine yönlendirir. Aynı anda tek tur sürer (oturum modeli).
    """

    def __init__(self, session_factory: Callable[[Callable[[str], None]], Any], root: Path) -> None:
        self._root = root
        self._active_run: str | None = None
        self._sink: EventSink | None = None
        self._results: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._options: dict[str, dict[str, Any]] = {}
        self._session = session_factory(self._on_line)

    def _on_line(self, line: str) -> None:
        try:
            message = json.loads(line)
        except ValueError:
            return
        kind = message.get("tip")
        data = message.get("veri") or {}
        if kind == "sonuc":
            future = self._results.pop(message.get("id", ""), None)
            if future is not None and not future.done():
                future.set_result(data)
        elif kind == "soru" and self._sink is not None:
            self._sink("question", {"questionId": message.get("id"), **data})
        elif kind == "olay" and self._sink is not None:
            self._sink("event", data)

    def prepare_run(self, run_id: str, options: dict[str, Any]) -> None:
        self._options[run_id] = options

    async def call(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        request_id = "uzak-" + uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._results[request_id] = future
        await self._session.handle(Request(request_id, name, data))
        return await future

    async def start(self, run_id: str, prompt: str, sink: EventSink) -> None:
        self._active_run = run_id
        self._sink = sink
        options = self._options.pop(run_id, {})
        sink("started", {})
        session_data: dict[str, Any] = {}
        if options.get("chat_id"):
            session_data["sohbet_id"] = options["chat_id"]
        if options.get("root"):
            session_data["kok"] = options["root"]
        if session_data:
            await self.call("oturum.baslat", session_data)
        if options.get("tier"):
            await self.call("kademe.sec", {"ad": options["tier"]})
        turn: dict[str, Any] = {"gorev": prompt}
        if options.get("attachments"):
            turn["ekler"] = options["attachments"]
        request_id = "uzak-" + uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._results[request_id] = future
        await self._session.handle(Request(request_id, "tur.calistir", turn))
        result = await future
        ok = bool(result.get("ok", True))
        sink("done" if ok else "failed", {"summary": str(result.get("metin", ""))})
        self._active_run = None
        self._sink = None

    async def cancel(self, run_id: str) -> bool:
        if run_id != self._active_run:
            return False
        request_id = "uzak-" + uuid.uuid4().hex
        await self._session.handle(Request(request_id, "tur.kes", {}))
        return True

    async def answer(self, question_id: str, answer: dict[str, Any]) -> bool:
        answer = dict(answer)
        answer.setdefault(
            "decisionId",
            uuid.uuid5(uuid.NAMESPACE_URL, question_id + json.dumps(answer, sort_keys=True)).hex,
        )
        request_id = "uzak-" + uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._results[request_id] = future
        await self._session.handle(
            Request(request_id, "soru.cevapla", {"questionId": question_id, "answer": answer})
        )
        return bool((await future).get("ok"))

    def pause_supported(self) -> bool:
        return False  # Oturum duraklatma sözleşmesi yok; sahte başarı döndürülmez.

    def kits(self) -> list[dict[str, Any]]:
        return []
