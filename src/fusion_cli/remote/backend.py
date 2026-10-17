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

    async def start(self, run_id: str, prompt: str, sink: EventSink) -> None:
        self._active_run = run_id
        self._sink = sink
        request_id = "uzak-" + uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._results[request_id] = future
        sink("started", {})
        await self._session.handle(Request(request_id, "tur.calistir", {"gorev": prompt}))
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
