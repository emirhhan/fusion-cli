"""Görev servisinin arkasındaki yürütücü sözleşmesi ve `AppSession` bağdaştırıcısı."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from ..appserver.protocol import Request
from .constants import (
    BACKEND_CALL_TIMEOUT_SECONDS,
    BACKEND_RESULT_GRACE_SECONDS,
    BACKEND_TURN_TIMEOUT_SECONDS,
)

# Modül düzeyinde adlandırılır: testler süreleri kısaltabilsin.
CALL_TIMEOUT_SECONDS = BACKEND_CALL_TIMEOUT_SECONDS
CALL_RESULT_GRACE_SECONDS = BACKEND_RESULT_GRACE_SECONDS
TURN_TIMEOUT_SECONDS = BACKEND_TURN_TIMEOUT_SECONDS

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
        #: `cancel` çağrılan görev: `/goal` devam zinciri bir sonraki turu başlatmaz.
        self._cancelled_run: str | None = None
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

    async def _request(
        self, name: str, data: dict[str, Any], limit_seconds: float
    ) -> dict[str, Any]:
        """İsteği oturuma ver, sonucu bekle. Her yolda `_results` kaydı temizlenir.

        `handle` istisna sızdırmaz ve sonucu dönmeden yazar; yine de yazıcı satırı
        kaybolursa ya da oturum çökerse bekleme sınırlıdır: sonsuz `await future`
        `run_lock`'u sonsuza tutup sonraki tüm uzak görevleri kuyrukta bırakırdı.
        `limit_seconds` `handle` süresini (tur için uzun), kısa ek süre sonuç satırını sınırlar.
        """
        request_id = "uzak-" + uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._results[request_id] = future
        try:
            await asyncio.wait_for(
                self._session.handle(Request(request_id, name, data)), limit_seconds
            )
            return await asyncio.wait_for(future, CALL_RESULT_GRACE_SECONDS)
        finally:
            self._results.pop(request_id, None)

    async def call(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request(name, data, CALL_TIMEOUT_SECONDS)

    async def _prepare_session(self, options: dict[str, Any]) -> str | None:
        """Kök/sohbet ve kademeyi uygula; reddedilirse kullanıcıya gösterilecek metni döner.

        Sonuç denetlenmezse geçersiz kökte görev önceki kökte (yanlış dizin) çalışırdı.
        """
        session_data: dict[str, Any] = {}
        if options.get("chat_id"):
            session_data["sohbet_id"] = options["chat_id"]
        if options.get("root"):
            session_data["kok"] = options["root"]
        steps: list[tuple[str, dict[str, Any]]] = []
        if session_data:
            steps.append(("oturum.baslat", session_data))
        if options.get("tier"):
            steps.append(("kademe.sec", {"ad": options["tier"]}))
        for name, data in steps:
            result = await self.call(name, data)
            if not result.get("ok", True):
                return str(result.get("metin") or "Oturum hazırlanamadı; görev başlatılmadı.")
        return None

    async def start(self, run_id: str, prompt: str, sink: EventSink) -> None:
        self._active_run = run_id
        self._sink = sink
        try:
            options = self._options.pop(run_id, {})
            sink("started", {})
            refusal = await self._prepare_session(options)
            if refusal is not None:
                sink("failed", {"summary": refusal})
                return
            turn: dict[str, Any] = {"gorev": prompt}
            if options.get("attachments"):
                turn["ekler"] = options["attachments"]
            while True:
                try:
                    result = await self._request("tur.calistir", turn, TURN_TIMEOUT_SECONDS)
                except TimeoutError:
                    await self._stop_after_timeout()
                    sink("failed", {"summary": "Görev zaman aşımına uğradı ve durduruldu."})
                    return
                # `/goal` (P-058): masaüstü gibi uzak görev de devam turunu sürer; tavanı ve
                # duraklamayı oturum belirler. Ölçüldü (31 Ekim): `hedef_devam` yok sayılıyordu.
                continuation = result.get("hedef_devam")
                if not isinstance(continuation, str) or self._cancelled_run == run_id:
                    break
                sink("event", {"olay": "StatusChanged", "message": _goal_text(result)})
                turn = {"gorev": continuation}
            ok = bool(result.get("ok", True))
            summary = "\n\n".join(
                part for part in (str(result.get("metin", "")), _goal_text(result)) if part
            )
            sink("done" if ok else "failed", {"summary": summary})
        finally:
            self._options.pop(run_id, None)
            self._active_run = None
            self._sink = None
            if self._cancelled_run == run_id:
                self._cancelled_run = None

    async def _stop_after_timeout(self) -> None:
        """Zaman aşımında turu oturum tarafında da kes; hata terminal olayı engellemez."""
        try:
            await self.call("tur.kes", {})
        except Exception:  # kesme en iyi çabadır; failed olayı yine yazılır
            return

    async def cancel(self, run_id: str) -> bool:
        if run_id != self._active_run:
            return False
        self._cancelled_run = run_id
        request_id = "uzak-" + uuid.uuid4().hex
        await self._session.handle(Request(request_id, "tur.kes", {}))
        return True

    async def answer(self, question_id: str, answer: dict[str, Any]) -> bool:
        answer = dict(answer)
        answer.setdefault(
            "decisionId",
            uuid.uuid5(uuid.NAMESPACE_URL, question_id + json.dumps(answer, sort_keys=True)).hex,
        )
        result = await self._request(
            "soru.cevapla", {"questionId": question_id, "answer": answer}, CALL_TIMEOUT_SECONDS
        )
        return bool(result.get("ok"))

    def pause_supported(self) -> bool:
        return False  # Oturum duraklatma sözleşmesi yok; sahte başarı döndürülmez.

    def kits(self) -> list[dict[str, Any]]:
        return []


def _goal_text(result: dict[str, Any]) -> str:
    """Tur sonucundaki `/goal` karar metni (yoksa boş)."""
    goal = result.get("hedef")
    text = goal.get("metin") if isinstance(goal, dict) else None
    return text if isinstance(text, str) else ""
