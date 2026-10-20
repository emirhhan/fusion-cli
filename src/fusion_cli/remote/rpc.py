"""Sürümlü RPC: `tasks.*`, `approvals.respond`, `kits.*`, `devices.*`, `service.status`.

Her çağrı kimliği doğrulanmış bir cihaza bağlıdır; kapsam kontrolü yürütmeden
önce yapılır. Yüksek etkili onaylar imzalı telefonda tek işleme bağlı açık
ikinci teyitle verilir; kalıcı kapsam genişletilmez.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..core.protocols import Clock
from .approval_confirmation import ApprovalConfirmations
from .approvals import classify_question, is_approval
from .backend import EventSink, TaskBackend
from .constants import DELTA_FLUSH_SECONDS, RPC_VERSION
from .devices import CHANNEL_SIGNED, Device, DeviceRegistry
from .mobile import MobileApi, MobileError
from .redaction import notification_summary
from .scopes import Scope, allows
from .screen import ScreenCapture, ScreenShareGate, ScreenUnavailableError
from .tasks import (
    STATE_CANCELLED,
    STATE_DONE,
    STATE_FAILED,
    STATE_PAUSED,
    STATE_QUEUED,
    STATE_RUNNING,
    STATE_WAITING_APPROVAL,
    TERMINAL_STATES,
    TaskStore,
)

HOST_OFFLINE_NOTICE = (
    "Görevler bu bilgisayarda çalışır. Bilgisayar uyku, kilit veya kapalı durumdaysa "
    "ve internet kopuksa görev ilerlemez."
)

Handler = Callable[[Device, dict[str, Any]], Awaitable["RpcResult"]]


@dataclass(frozen=True, slots=True)
class RpcResult:
    """Zarf: başarı ya da tipli hata kodu."""

    ok: bool
    data: dict[str, Any]
    error: str = ""
    message: str = ""

    def view(self) -> dict[str, Any]:
        base: dict[str, Any] = {"version": RPC_VERSION, "ok": self.ok}
        if self.ok:
            return {**base, "data": self.data}
        return {**base, "error": self.error, "message": self.message}


def _fail(code: str, message: str) -> RpcResult:
    return RpcResult(False, {}, code, message)


class RemoteService:
    """RPC yöntemlerinin sahibi. Zaman, depo ve yürütücü dışarıdan verilir."""

    def __init__(
        self,
        *,
        clock: Clock,
        registry: DeviceRegistry,
        store: TaskStore,
        backend: TaskBackend,
        version: str = "0",
        screen_gate: ScreenShareGate | None = None,
        screen_capture: ScreenCapture | None = None,
        mobile: MobileApi | None = None,
        run_lock: asyncio.Lock | None = None,
    ) -> None:
        self._clock = clock
        self._registry = registry
        self._store = store
        self._backend = backend
        self._version = version
        self._screen_gate = screen_gate or ScreenShareGate(clock)
        self._screen_capture = screen_capture
        self._remember_screen: set[str] = set()
        self._last_frames: dict[str, tuple[int, bytes, float]] = {}
        self._mobile = mobile
        self._run_lock = run_lock or asyncio.Lock()
        self._deltas: dict[str, tuple[str, float]] = {}
        self._runs: set[asyncio.Task[None]] = set()
        self._confirmations = ApprovalConfirmations(clock)
        self._questions: dict[str, tuple[str, dict[str, Any]]] = {}
        self._active_run: str | None = None

    async def call(self, device: Device, method: str, params: dict[str, Any]) -> RpcResult:
        handler = self._handlers().get(method)
        if handler is None:
            return _fail("yontem_yok", f"Bilinmeyen yöntem: {method}")
        return await handler(device, params)

    def _handlers(self) -> dict[str, Handler]:
        return {
            "service.status": self._status,
            "tasks.create": self._create,
            "tasks.list": self._list,
            "tasks.status": self._task_status,
            "tasks.events": self._events,
            "tasks.cancel": self._cancel,
            "tasks.pause": self._pause,
            "tasks.resume": self._pause,
            "approvals.respond": self._respond,
            "approvals.challenge": self._challenge,
            "kits.list": self._kits_list,
            "kits.run": self._kits_run,
            "devices.revoke": self._revoke_self,
            "screen.request": self._screen_request,
            "screen.status": self._screen_status,
            "screen.frame": self._screen_frame,
            "screen.stop": self._screen_stop,
            **self._mobile_handlers(),
        }

    def _mobile_handlers(self) -> dict[str, Handler]:
        if self._mobile is None:
            return {}
        handlers: dict[str, Handler] = {"schedules.run": self._schedule_run}

        def wrap(
            scope: str, method: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
        ) -> Handler:
            async def handler(device: Device, params: dict[str, Any]) -> RpcResult:
                denied = self._need(device, scope)
                if denied:
                    return denied
                try:
                    return RpcResult(True, await method(params))
                except MobileError as error:
                    return _fail(error.code, error.message)

            return handler

        for name, (scope, method) in self._mobile.methods().items():
            handlers[name] = wrap(scope, method)
        return handlers

    async def _schedule_run(self, device: Device, params: dict[str, Any]) -> RpcResult:
        """Zamanlanan görevi şimdi başlatır: görev metni bu oturumda yeni sohbet olarak çalışır."""
        denied = self._need(device, Scope.AGENT_RUN.value)
        if denied or self._mobile is None:
            return denied or _fail("desteklenmiyor", "Zamanlananlar bu kurulumda yok.")
        item = await self._mobile.find_schedule(str(params.get("id", "")))
        if item is None:
            return _fail("gorev_yok", "Zamanlanan görev bulunamadı.")
        request: dict[str, Any] = {
            "prompt": str(item.get("gorev", "")),
            "chatId": "z_" + uuid.uuid4().hex[:16],
            "idempotencyKey": str(params.get("idempotencyKey", "")),
        }
        try:
            self._mobile.root_for(item.get("kok"))
            request["root"] = item.get("kok")
        except MobileError:
            pass  # klasör masaüstünden bildirilmemiş: varsayılan kökte çalışır
        return await self._create(device, request)

    @staticmethod
    def _need(device: Device, scope: str) -> RpcResult | None:
        if allows(device.scopes, scope):
            return None
        return _fail("yetki_yok", f"Bu işlem için '{scope}' yetkisi gerekir.")

    async def _status(self, device: Device, _params: dict[str, Any]) -> RpcResult:
        return RpcResult(
            True,
            {
                "hostOnline": True,
                "version": self._version,
                "activeRun": self._active_run,
                "scopes": sorted(device.scopes),
                "notice": HOST_OFFLINE_NOTICE,
            },
        )

    async def _create(self, device: Device, params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.AGENT_RUN.value)
        if denied:
            return denied
        prompt = params.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return _fail("gecersiz_istek", "Görev metni gerekli.")
        key = params.get("idempotencyKey")
        options: dict[str, Any] = {}
        if self._mobile is not None:
            try:
                options = self._mobile.run_options(params)
            except MobileError as error:
                return _fail(error.code, error.message)
        record, is_new = self._store.create(
            device.device_id,
            notification_summary(prompt),
            project=str(params.get("project", ""))[:200],
            idempotency_key=key if isinstance(key, str) else "",
            chat_id=str(options.get("chat_id", "")),
        )
        if is_new:
            if options:
                self._backend.prepare_run(record.run_id, options)
            self._launch(record.run_id, prompt)
        return RpcResult(True, {**record.view(), "duplicate": not is_new})

    def _launch(self, run_id: str, prompt: str) -> None:
        task = asyncio.ensure_future(self._run(run_id, prompt))
        self._runs.add(task)
        task.add_done_callback(self._runs.discard)

    async def _run(self, run_id: str, prompt: str) -> None:
        async with self._run_lock:
            record = self._store.get(run_id)
            if record is None or record.state in TERMINAL_STATES:
                return  # sıradayken iptal edildi
            self._active_run = run_id
            try:
                await self._backend.start(run_id, prompt, self._sink_for(run_id))
            except Exception as error:  # yürütücü hatası servisi düşürmez
                self._store.append(run_id, "failed", {"summary": notification_summary(str(error))})
                self._store.set_state(run_id, STATE_FAILED)
            finally:
                self._active_run = None

    def _sink_for(self, run_id: str) -> EventSink:
        def sink(kind: str, payload: dict[str, Any]) -> None:
            if kind == "event" and payload.get("olay") == "TokenReceived":
                if not payload.get("provisional"):
                    self._buffer_delta(run_id, str(payload.get("text", "")))
                return
            self._flush_delta(run_id)
            if kind == "started":
                self._store.set_state(run_id, STATE_RUNNING)
            elif kind == "question":
                self._on_question(run_id, payload)
                return
            elif kind == "done":
                self._store.set_state(run_id, STATE_DONE)
            elif kind == "failed":
                self._store.set_state(run_id, STATE_FAILED)
            self._store.append(run_id, kind, payload)

        return sink

    def _buffer_delta(self, run_id: str, text: str) -> None:
        """Akan yanıt parçalarını birleştirir: saniyede birkaç olay, binlerce değil."""
        pending, last = self._deltas.get(run_id, ("", 0.0))  # ilk parça gecikmeden
        pending += text
        if self._clock.now() - last >= DELTA_FLUSH_SECONDS:
            self._deltas.pop(run_id, None)
            self._store.append(run_id, "delta", {"text": pending})
            self._deltas[run_id] = ("", self._clock.now())
        else:
            self._deltas[run_id] = (pending, last)

    def _flush_delta(self, run_id: str) -> None:
        pending, _last = self._deltas.pop(run_id, ("", 0.0))
        if pending:
            self._store.append(run_id, "delta", {"text": pending})

    def _on_question(self, run_id: str, payload: dict[str, Any]) -> None:
        question_id = str(payload.get("questionId", ""))
        self._questions[question_id] = (run_id, payload)
        self._store.set_state(run_id, STATE_WAITING_APPROVAL)
        view: dict[str, Any] = {
            "questionId": question_id,
            "title": payload.get("baslik", ""),
            "target": payload.get("hedef", ""),
            "kind": payload.get("tur", ""),
            "tool": payload.get("arac", ""),
            "args": payload.get("argumanlar", []),
            "danger": payload.get("tehlike"),
            "reason": payload.get("neden"),
            "diff": payload.get("diff", ""),
            "options": payload.get("secenekler", []),
        }
        if is_approval(payload):
            approval = classify_question(payload)
            view["stepUp"] = approval.step_up
            view["requiredScope"] = approval.required_scope
        self._store.append(run_id, "approval_request", view)

    async def _list(self, device: Device, _params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.PROJECT_READ.value)
        if denied:
            return denied
        return RpcResult(True, {"tasks": [task.view() for task in self._store.list_tasks()]})

    async def _task_status(self, device: Device, params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.PROJECT_READ.value)
        if denied:
            return denied
        record = self._store.get(str(params.get("runId", "")))
        if record is None:
            return _fail("gorev_yok", "Görev bulunamadı.")
        return RpcResult(True, record.view())

    async def _events(self, device: Device, params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.PROJECT_READ.value)
        if denied:
            return denied
        run_id = str(params.get("runId", ""))
        record = self._store.get(run_id)
        if record is None:
            return _fail("gorev_yok", "Görev bulunamadı.")
        after = params.get("afterSeq", 0)
        after_seq = after if isinstance(after, int) and after >= 0 else 0
        events = self._store.events_after(run_id, after_seq)
        return RpcResult(
            True, {"events": [event.view() for event in events], "state": record.state}
        )

    async def _cancel(self, device: Device, params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.AGENT_CANCEL.value)
        if denied:
            return denied
        record = self._store.get(str(params.get("runId", "")))
        if record is None:
            return _fail("gorev_yok", "Görev bulunamadı.")
        if record.state in TERMINAL_STATES:
            return RpcResult(True, {**record.view(), "changed": False})
        if record.state == STATE_QUEUED:
            self._store.set_state(record.run_id, STATE_CANCELLED)
            self._store.append(record.run_id, "cancelled", {})
            return RpcResult(True, {**record.view(), "changed": True})
        stopped = await self._backend.cancel(record.run_id)
        if stopped:
            self._store.set_state(record.run_id, STATE_CANCELLED)
            self._store.append(record.run_id, "cancelled", {})
        return RpcResult(True, {**record.view(), "changed": stopped})

    async def _pause(self, device: Device, _params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.AGENT_PAUSE.value)
        if denied:
            return denied
        if not self._backend.pause_supported():
            return _fail(
                "desteklenmiyor", "Duraklatma bu sürümde desteklenmiyor; iptal edebilirsin."
            )
        return RpcResult(True, {"state": STATE_PAUSED})

    async def _respond(self, device: Device, params: dict[str, Any]) -> RpcResult:
        question_id = str(params.get("questionId", ""))
        entry = self._questions.get(question_id)
        if entry is None:
            return _fail("soru_yok", "Soru bulunamadı veya zaten kapandı.")
        run_id, question = entry
        choice = params.get("choice")
        if is_approval(question):
            refusal = self._approval_refusal(device, question, choice, run_id, question_id, params)
            if refusal is not None:
                return refusal
            answer: dict[str, Any] = {"secim": choice}
        else:
            denied = self._need(device, Scope.AGENT_RUN.value)
            if denied:
                return denied
            text = params.get("text")
            if not isinstance(text, str):
                return _fail("gecersiz_istek", "Cevap metni gerekli.")
            answer = {"metin": text}
        if isinstance(params.get("decisionId"), str) and params["decisionId"]:
            answer["decisionId"] = params["decisionId"]
        accepted = await self._backend.answer(question_id, answer)
        if not accepted:
            return _fail("cevap_reddedildi", "Soru cevabı yürütücü tarafından kabul edilmedi.")
        if accepted:
            self._questions.pop(question_id, None)
            self._store.set_state(run_id, STATE_RUNNING)
            self._store.append(
                run_id, "approval_answered", {"questionId": question_id, "choice": choice}
            )
        return RpcResult(True, {"accepted": accepted})

    @staticmethod
    def _choices(question: dict[str, Any]) -> set[str]:
        options = question.get("secenekler")
        if isinstance(options, list):
            return {str(item.get("deger")) for item in options if isinstance(item, dict)}
        return set()

    async def _challenge(self, device: Device, params: dict[str, Any]) -> RpcResult:
        question_id = str(params.get("questionId", ""))
        entry = self._questions.get(question_id)
        if entry is None:
            return _fail("soru_yok", "Soru bulunamadı veya zaten kapandı.")
        run_id, question = entry
        choice = params.get("choice")
        if device.channel != CHANNEL_SIGNED or self._need(device, Scope.AGENT_RUN.value):
            return _fail("yetki_yok", "İmzalı ve görev yetkili telefon gerekli.")
        if (
            not is_approval(question)
            or not isinstance(choice, str)
            or choice not in self._choices(question)
        ):
            return _fail("gecersiz_istek", "Sunulmayan onay seçeneği.")
        token = self._confirmations.issue(
            device.device_id, run_id, question_id, str(choice), question
        )
        return RpcResult(True, {"challengeId": token})

    def _approval_refusal(
        self,
        device: Device,
        question: dict[str, Any],
        choice: object,
        run_id: str,
        question_id: str,
        params: dict[str, Any],
    ) -> RpcResult | None:
        """İmzalı telefon tek işlem için açık teyitle bütün onayları verebilir."""
        if not isinstance(choice, str) or choice not in self._choices(question):
            return _fail("gecersiz_istek", "Sunulmayan onay seçeneği.")
        if device.channel == CHANNEL_SIGNED:
            denied = self._need(device, Scope.AGENT_RUN.value)
            if denied:
                return denied
        if choice == "deny":
            return None
        approval = classify_question(question)
        if device.channel == CHANNEL_SIGNED:
            if (approval.step_up or choice == "session") and not self._confirmations.consume(
                params.get("confirmation"),
                device.device_id,
                run_id,
                question_id,
                choice,
                question,
            ):
                return _fail("step_up", "Bu işlem için telefonda açık ikinci teyit gerekli.")
            return None
        denied = self._need(device, approval.required_scope)
        if denied:
            return denied
        if approval.step_up or choice == "session":
            return _fail("step_up", "Bu işlem imzalı telefonda açık teyit gerektirir.")
        return None

    async def _kits_list(self, device: Device, _params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.KITS_LIST.value)
        if denied:
            return denied
        listed = [
            {"slug": kit["slug"], "title": kit.get("title", kit["slug"])}
            for kit in self._backend.kits()
            if kit.get("remote_allowed") is True
        ]
        return RpcResult(True, {"kits": listed})

    async def _kits_run(self, device: Device, params: dict[str, Any]) -> RpcResult:
        slug = str(params.get("slug", ""))
        denied = self._need(device, f"kits.run.{slug}")
        if denied:
            return denied
        kit = next((k for k in self._backend.kits() if k.get("slug") == slug), None)
        if kit is None or kit.get("remote_allowed") is not True:
            return _fail("kit_izinsiz", "Bu kit uzaktan çalıştırmaya açık değil.")
        return await self._create(device, {**params, "prompt": str(kit.get("prompt", slug))})

    async def _revoke_self(self, device: Device, params: dict[str, Any]) -> RpcResult:
        target = str(params.get("deviceId", device.device_id))
        if target != device.device_id:
            return _fail("yetki_yok", "Başka cihazı yalnız masaüstünden iptal edebilirsin.")
        self.stop_screen(target)
        return RpcResult(True, {"revoked": self._registry.revoke(target)})

    def pending_questions(self) -> list[dict[str, Any]]:
        """Masaüstü kullanıcısının görebileceği bekleyen sorular (sır içermez)."""
        return [
            {
                "soruId": question_id,
                "runId": run_id,
                "baslik": str(question.get("baslik", "")),
                "hedef": str(question.get("hedef", "")),
                "onay": is_approval(question),
            }
            for question_id, (run_id, question) in self._questions.items()
        ]

    @property
    def screen_gate(self) -> ScreenShareGate:
        return self._screen_gate

    async def _screen_request(self, device: Device, params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.DESKTOP_OBSERVE.value)
        if denied:
            return denied
        if device.channel != CHANNEL_SIGNED:
            return _fail("yetki_yok", "Ekran yalnız imzalı telefondan istenebilir.")
        if params.get("remember") is True:
            self._remember_screen.add(device.device_id)
        state = self._screen_gate.request(device.device_id)
        current = self._registry.active(device.device_id)
        if state == "pending" and (
            (current is not None and current.screen_trusted) or params.get("confirmed") is True
        ):
            self.approve_screen(device.device_id)
            current = self._registry.active(device.device_id)
            state, _remaining = self._screen_gate.status(device.device_id)
        return RpcResult(
            True, {"state": state, "remembered": bool(current and current.screen_trusted)}
        )

    async def _screen_status(self, device: Device, _params: dict[str, Any]) -> RpcResult:
        denied = self._need(device, Scope.DESKTOP_OBSERVE.value)
        if denied:
            return denied
        state, remaining = self._screen_gate.status(device.device_id)
        current = self._registry.active(device.device_id)
        return RpcResult(
            True,
            {
                "state": state,
                "secondsLeft": remaining,
                "remembered": bool(current and current.screen_trusted),
            },
        )

    async def _screen_frame(self, device: Device, _params: dict[str, Any]) -> RpcResult:
        if device.channel != CHANNEL_SIGNED:
            return _fail("yetki_yok", "Ekran yalnız imzalı telefondan izlenebilir.")
        denied = self._need(device, Scope.DESKTOP_OBSERVE.value)
        if denied:
            return denied
        sequence = self._screen_gate.next_sequence(device.device_id)
        if sequence == "onay_yok":
            return _fail(
                "ekran_onay_yok", "Ekran paylaşımı masaüstünde onaylanmadı veya süresi doldu."
            )
        if sequence == "cok_sik":
            return _fail("cok_sik", "Kareler çok sık isteniyor; biraz yavaşla.")
        if self._screen_capture is None:
            return _fail("ekran_kullanilamaz", "Bu kurulumda ekran yakalama yok.")
        try:
            frame = await self._screen_capture.frame()
        except ScreenUnavailableError as error:
            return _fail("ekran_kullanilamaz", str(error))
        if isinstance(sequence, int):
            self._last_frames[device.device_id] = (sequence, frame, self._clock.now())
        return RpcResult(
            True, {"seq": sequence, "jpegBase64": base64.b64encode(frame).decode("ascii")}
        )

    def latest_screen_frame(self, device_id: str) -> tuple[int, bytes, float] | None:
        """Telefona en son verilen kare; masaüstü önizlemesi ek yakalama yapmadan bunu gösterir."""
        if device_id not in self._screen_gate.active():
            self._last_frames.pop(device_id, None)
            return None
        return self._last_frames.get(device_id)

    async def _screen_stop(self, device: Device, _params: dict[str, Any]) -> RpcResult:
        return RpcResult(True, {"stopped": self.stop_screen(device.device_id)})

    def approve_screen(self, device_id: str) -> bool:
        """İlk yerel onaydan sonra cihazın açık hatırlama tercihini sakla."""
        if not self._screen_gate.approve(device_id):
            return False
        if device_id in self._remember_screen:
            self._registry.set_screen_trusted(device_id, True)
            self._remember_screen.discard(device_id)
        return True

    def stop_screen(self, device_id: str) -> bool:
        """Yerel veya telefon kesmesi oturumu ve hatırlanan güveni kaldırır."""
        self._remember_screen.discard(device_id)
        self._last_frames.pop(device_id, None)
        self._registry.set_screen_trusted(device_id, False)
        return self._screen_gate.stop(device_id)

    async def answer_from_desktop(self, question_id: str, choice: str) -> bool:
        """Masaüstü kullanıcısının yerel kararı (step-up burada tamamlanır)."""
        entry = self._questions.get(question_id)
        if entry is None or choice not in self._choices(entry[1]):
            return False
        run_id, _question = entry
        accepted = await self._backend.answer(question_id, {"secim": choice})
        if accepted:
            self._questions.pop(question_id, None)
            self._store.set_state(run_id, STATE_RUNNING)
            self._store.append(
                run_id,
                "approval_answered",
                {"questionId": question_id, "choice": choice, "by": "desktop"},
            )
        return accepted

    async def aclose(self) -> None:
        for task in list(self._runs):
            task.cancel()
        await asyncio.gather(*self._runs, return_exceptions=True)
