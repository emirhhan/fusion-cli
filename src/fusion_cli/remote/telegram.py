"""Telegram köprüsü: kullanıcının kendi botu, uzun yoklama (`getUpdates`), dışarı bağlantı.

Güvenlik duruşu:
- Yalnız eşleşmiş Telegram kullanıcı kimliği ve yalnız özel sohbet (DM) işlenir.
- Onay düğmesi YOK: riskli işlem bildirimi yalnız "masaüstünde onayla" der.
- Sohbet uçtan uca şifreli (Secret Chat) DEĞİLDİR; sır görünen mesajlar işlenmez.
- Aynı `update_id` iki kez işlenmez (idempotency anahtarı da buna bağlıdır).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from ..core.atomic_file import atomic_replace_text
from ..core.execution_context import ExecutionContext
from ..core.protocols import Clock
from .constants import (
    NOTIFICATION_SUMMARY_LIMIT,
    TELEGRAM_FAILED_PAIR_LIMIT,
    TELEGRAM_POLL_TIMEOUT_SECONDS,
)
from .devices import CHANNEL_TELEGRAM, Device, DeviceRegistry
from .pairing import PairingError, PairingService
from .rate_limit import FailureLimiter
from .redaction import REDACTED, notification_summary, redact_text
from .rpc import RemoteService, RpcResult
from .tasks import TERMINAL_STATES, TaskRecord, TaskStore, device_context

_LOG = logging.getLogger(__name__)
#: Köprü hata sonrası yeniden yoklamadan önce bekler.
RETRY_SECONDS = 3

# /pause ve /resume yardımda ANILMAZ: oturum duraklatma sözleşmesi yok, komutlar dürüstçe
# "desteklenmiyor" döner (R1-18). Yürütücü destek ekleyince buraya geri eklenir.
HELP_TEXT = (
    "Komutlar: /projects /tasks /status /kits /kit <ad> /cancel /audit /devices\n"
    "Düz mesaj yeni görev oluşturur. Riskli işlemler yalnız masaüstünde onaylanır.\n"
    "Bu sohbet uçtan uca şifreli değildir; parola/anahtar yazma."
)
SECRET_WARNING = (
    "Mesajında sır gibi görünen bir içerik var (parola:/token= gibi bir kalıp); işlenmedi. "
    "Sırları sohbete yazma; sır değilse o kalıbı çıkarıp yeniden yaz."
)
STEP_UP_NOTICE = "Onay gerekiyor. Bu işlem güvenlik için yalnız masaüstü Fusion'da onaylanır."


class TelegramApi(Protocol):
    """Telegram Bot API'nin kullandığımız küçük yüzü."""

    async def get_updates(self, offset: int, poll_seconds: int) -> list[dict[str, Any]]: ...

    async def send_message(self, chat_id: int, text: str) -> None: ...

    async def delete_message(self, chat_id: int, message_id: int) -> None: ...


class HttpTelegramApi:
    """`api.telegram.org` istemcisi. Belirteç yalnız URL'de yaşar; hata metninden temizlenir."""

    def __init__(self, token: str, client: httpx.AsyncClient | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}"
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=TELEGRAM_POLL_TIMEOUT_SECONDS + 10)

    async def _call(self, method: str, payload: dict[str, Any]) -> Any:  # noqa: ANN401
        try:
            response = await self._client.post(f"{self._base}/{method}", json=payload)
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TelegramError(str(error).replace(self._token, REDACTED)) from None
        if not data.get("ok"):
            raise TelegramError(str(data.get("description", "Telegram hatası")))
        return data.get("result")

    async def get_updates(self, offset: int, poll_seconds: int) -> list[dict[str, Any]]:
        result = await self._call(
            "getUpdates",
            {"offset": offset, "timeout": poll_seconds, "allowed_updates": ["message"]},
        )
        return result if isinstance(result, list) else []

    async def send_message(self, chat_id: int, text: str) -> None:
        await self._call("sendMessage", {"chat_id": chat_id, "text": text})

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        await self._call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


class TelegramError(RuntimeError):
    """Telegram çağrısı başarısız; mesaj belirteç içermez."""


class OffsetStore:
    """Son işlenen `update_id`'yi kalıcı tutar; yeniden başlatmada tekrar işleme olmaz."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> int:
        try:
            return int(json.loads(self._path.read_text(encoding="utf-8"))["offset"])
        except (OSError, ValueError, KeyError, TypeError):
            return 0

    def save(self, offset: int) -> None:
        atomic_replace_text(self._path, json.dumps({"offset": offset}))


class TelegramBridge:
    """Telegram güncellemelerini RPC çağrılarına çevirir."""

    def __init__(
        self,
        *,
        api: TelegramApi,
        service: RemoteService,
        registry: DeviceRegistry,
        pairing: PairingService,
        store: TaskStore,
        clock: Clock,
        offsets: OffsetStore,
    ) -> None:
        self._api = api
        self._service = service
        self._registry = registry
        self._pairing = pairing
        self._store = store
        self._offsets = offsets
        self._offset = offsets.load()
        self._limiter = FailureLimiter(clock, limit=TELEGRAM_FAILED_PAIR_LIMIT)
        #: Görevler kalıcı: köprüden ÖNCE açılmış görevlerin geçmiş olayları yeniden
        #: bildirilmez (yeniden başlatmada eski onay/bitiş mesajları yağmasın).
        self._started_at = clock.now()
        self._projects: dict[str, str] = {}
        self._notified: dict[str, int] = {}
        self._chats: dict[str, int] = {}

    async def run(
        self, stop: asyncio.Event, on_error: Callable[[str], Awaitable[None]] | None = None
    ) -> None:
        """Dışarı bağlantıyla yokla; port açılmaz. Hata olursa kısa bekleyip sürer.

        Yalnız `TelegramError` değil her istisna yakalanır: aksi halde beklenmeyen bir hata
        köprü görevini sessizce bitirir (`telegramHata` boş, durum "bağlı değil") olurdu.
        """
        while not stop.is_set():
            try:
                await self.poll_once(TELEGRAM_POLL_TIMEOUT_SECONDS, on_error)
            except Exception as error:  # köprü ayakta kalmalı; ayrıntı günlükte
                await self._report(error, on_error)
                await asyncio.sleep(RETRY_SECONDS)

    @staticmethod
    async def _report(error: Exception, on_error: Callable[[str], Awaitable[None]] | None) -> None:
        _LOG.warning("Telegram köprüsü hatası: %s", error, exc_info=True)
        if on_error is not None:
            detail = str(error) if isinstance(error, TelegramError) else repr(error)
            await on_error(redact_text(detail))

    async def poll_once(
        self, poll_seconds: int = 0, on_error: Callable[[str], Awaitable[None]] | None = None
    ) -> None:
        for update in await self._api.get_updates(self._offset, poll_seconds):
            try:
                await self.handle_update(update)
            except Exception as error:  # zehirli güncelleme diğerlerini ve bildirimi engellemesin
                await self._report(error, on_error)
        await self.notify()

    async def handle_update(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if not isinstance(update_id, int) or update_id < self._offset:
            return  # tekrar gelen güncelleme: ikinci kez çalıştırma
        self._offset = update_id + 1
        try:
            await self._process(update, update_id)
        finally:
            # İşlendikten SONRA kalıcı: süreç ortada ölürse güncelleme yeniden gelir
            # (görev anahtarı `tg:<update_id>` olduğundan çift görev açılmaz). Hata
            # fırlatan güncelleme de atlanır; yoksa her yoklamada aynı hataya takılırdı.
            self._offsets.save(self._offset)

    async def _process(self, update: dict[str, Any], update_id: int) -> None:
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat, sender = message.get("chat") or {}, message.get("from") or {}
        text = message.get("text")
        if chat.get("type") != "private" or not isinstance(text, str) or "id" not in sender:
            return  # grup/kanal/medya: yok sayılır
        if not isinstance(chat.get("id"), int):
            return  # bozuk güncelleme: yanıtlanacak sohbet yok
        user_id = str(sender["id"])
        chat_id = chat["id"]
        device = self._registry.find_external(CHANNEL_TELEGRAM, user_id)
        if device is None:
            await self._pair(chat_id, user_id, sender, text)
            return
        self._chats[device.device_id] = chat_id
        if redact_text(text) != text:
            await self._reject_secret(chat_id, message)
            return
        await self._reply(chat_id, await self._dispatch(device, text, update_id))

    async def _pair(self, chat_id: int, user_id: str, sender: dict[str, Any], text: str) -> None:
        key = f"tg:{user_id}"
        parts = text.split()
        if len(parts) != 2 or parts[0] != "/pair" or self._limiter.is_locked(key):
            return  # eşleşmemiş kullanıcıya bilgi sızdırma
        name = f"Telegram {sender.get('username') or user_id}"
        try:
            self._pairing.submit(parts[1], name, external_id=user_id, channel=CHANNEL_TELEGRAM)
        except PairingError:
            self._limiter.record_failure(key)
            await self._reply(chat_id, "Kod geçersiz veya süresi doldu.")
            return
        await self._reply(chat_id, "Kod alındı. Eşleştirmeyi masaüstü Fusion'da onayla.")

    async def _reject_secret(self, chat_id: int, message: dict[str, Any]) -> None:
        await self._reply(chat_id, SECRET_WARNING)
        message_id = message.get("message_id")
        if isinstance(message_id, int):
            # Silme izni olmayabilir; uyarı yeterli.
            with contextlib.suppress(TelegramError):
                await self._api.delete_message(chat_id, message_id)

    async def _dispatch(self, device: Device, text: str, update_id: int) -> str:
        command, _, argument = text.strip().partition(" ")
        argument = argument.strip()
        user = device.external_id
        if command in {"/start", "/help"}:
            return HELP_TEXT
        if command == "/project":
            self._projects[user] = argument[:200]
            return f"Proje: {argument or '(yok)'}"
        if command == "/projects":
            tasks = self._store.list_tasks(device_context(device))
            names = sorted({t.project for t in tasks if t.project})
            return "\n".join(names) or "Henüz proje adı yok. /project <ad> ile seç."
        if command == "/tasks":
            return await self._tasks_text(device)
        if command in {"/status", "/audit"}:
            return await self._status_text(device, argument, audit=command == "/audit")
        if command == "/kits":
            return await self._kits_text(device)
        if command == "/kit":
            return self._summary(
                await self._service.call(
                    device, "kits.run", {"slug": argument, "idempotencyKey": f"tg:{update_id}"}
                ),
                "Kit başlatıldı",
            )
        if command in {"/pause", "/resume"}:
            method = "tasks.pause" if command == "/pause" else "tasks.resume"
            return self._summary(await self._service.call(device, method, {}), "Tamam")
        if command == "/cancel":
            run_id = argument or self._latest_run(device)
            return self._summary(
                await self._service.call(device, "tasks.cancel", {"runId": run_id}), "İptal istendi"
            )
        if command == "/devices":
            return "\n".join(
                f"{d.name} — {'iptal' if d.revoked else 'aktif'}"
                for d in self._registry.list_devices()
            )
        if command.startswith("/"):
            return "Bilinmeyen komut. /help"
        return self._summary(
            await self._service.call(
                device,
                "tasks.create",
                {
                    "prompt": text,
                    "project": self._projects.get(user, ""),
                    "idempotencyKey": f"tg:{update_id}",
                },
            ),
            "Görev alındı",
        )

    def _latest_run(self, device: Device) -> str:
        tasks = self._store.list_tasks(device_context(device))
        return tasks[0].run_id if tasks else ""

    @staticmethod
    def _summary(result: RpcResult, ok_text: str) -> str:
        if result.ok:
            run_id = result.data.get("runId")
            return f"{ok_text}{f' ({run_id})' if run_id else ''}"
        if result.error == "step_up":
            return STEP_UP_NOTICE
        return result.message or "İşlem reddedildi."

    async def _tasks_text(self, device: Device) -> str:
        result = await self._service.call(device, "tasks.list", {})
        if not result.ok:
            return result.message
        rows = [f"{t['runId']} · {t['state']} · {t['summary']}" for t in result.data["tasks"][:8]]
        return "\n".join(rows) or "Görev yok."

    async def _status_text(self, device: Device, run_id: str, *, audit: bool) -> str:
        target = run_id or self._latest_run(device)
        if audit:
            result = await self._service.call(device, "tasks.events", {"runId": target})
            if not result.ok:
                return result.message
            kinds = ", ".join(event["kind"] for event in result.data["events"][-10:])
            return notification_summary(f"Olay kaydı ({target}): {kinds}")
        result = await self._service.call(device, "tasks.status", {"runId": target})
        return notification_summary(f"{target}: {result.data.get('state', result.message)}")

    async def _kits_text(self, device: Device) -> str:
        result = await self._service.call(device, "kits.list", {})
        if not result.ok:
            return result.message
        return "\n".join(kit["slug"] for kit in result.data["kits"]) or "Uzaktan açık kit yok."

    async def notify(self) -> None:
        """Düşük hacim: yalnız onay isteği ve terminal durum; kod/diff dökülmez."""
        for device_id, chat_id in list(self._chats.items()):
            device = self._registry.active(device_id)
            if device is None:
                continue
            context = device_context(device)
            for task in self._store.list_tasks(context):
                if task.owner_device == device_id:
                    await self._notify_task(context, chat_id, task)

    async def _notify_task(self, context: ExecutionContext, chat_id: int, task: TaskRecord) -> None:
        seen = self._notified.get(task.run_id)
        if seen is None:
            seen = task.last_seq if task.created_at < self._started_at else 0
        for event in self._store.events_after(context, task.run_id, seen):
            text = self._notice_for(task, event.kind)
            if text is not None:
                # İmleç gönderimden SONRA ilerler: gönderim düşerse olay yeniden denenir.
                await self._reply(chat_id, text)
            self._notified[task.run_id] = event.seq

    @staticmethod
    def _notice_for(task: TaskRecord, kind: str) -> str | None:
        if kind == "approval_request":
            return STEP_UP_NOTICE
        if task.state in TERMINAL_STATES and kind in {
            "done",
            "failed",
            "cancelled",
            "needs_reconciliation",
        }:
            return notification_summary(f"{task.run_id}: {kind}")
        return None

    async def _reply(self, chat_id: int, text: str) -> None:
        await self._api.send_message(chat_id, text[: NOTIFICATION_SUMMARY_LIMIT * 4])
