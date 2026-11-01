"""`--input-format stream-json` denetim kanalı (#280).

Claude Agent SDK'sı `claude -p --input-format stream-json --output-format stream-json`
sürecinin stdin'ine kullanıcı mesajlarının yanında denetim istekleri de yazar:

- `{"type":"control_request","request_id":..,"request":{"subtype":"interrupt"}}` süren turu
  keser; `initialize`, `set_permission_mode` (`mode`), `set_model` (`model`) de desteklenir.
  `bypassPermissions`'a geçiş yalnız koşu `--dangerously-skip-permissions` /
  `--allow-dangerously-skip-permissions` ile başladıysa kabul edilir; `--restricted`'da hiç.
  Her isteğe `{"type":"control_response","response":{"subtype":"success"|"error",...}}`
  ile cevap verilir; bilinmeyen alt tür `error` döner.
- `--permission-prompt-tool stdio` verilince onay gereken çağrı için stdout'a
  `control_request` (`subtype: can_use_tool`, `tool_name`, `input`, `tool_use_id`) yazılır ve
  stdin'den gelen `control_response` beklenir: yalnız `behavior: "allow"` onaydır.
  stdin kapanırsa bekleyen onay iptal edilir (istek reddedilmiş sayılır).

stdin ayrı bir iş parçacığında okunur; böylece tur sürerken gelen kesme ve onay cevapları
hemen işlenir. Kullanıcı satırları sırayla `users()` ile tur olarak döner.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from collections.abc import Callable, Coroutine, Iterator, Mapping
from typing import Any, TextIO, TypeVar

from ..engines.agent.approval import ApprovalAnswer, ApprovalMode, ApprovalRequest
from ..ui import print_messages as texts
from .print_runtime import PrintPrompter
from .sdk_messages import claude_tool_name

T = TypeVar("T")
Writer = Callable[[Mapping[str, object]], None]
#: `--permission-prompt-tool` için SDK'nın verdiği değer: onaylar stdin/stdout denetim akışında.
STDIO_PROMPT_TOOL = "stdio"
_END = object()


def content_text(content: object) -> str:
    """Kullanıcı mesajı içeriğinden düz metin (dizge ya da `text` blokları)."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n\n".join(part for part in parts if part).strip()
    return ""


class ControlChannel:
    """stdin'i okuyup kullanıcı turlarını ve denetim iletilerini ayıran kanal."""

    def __init__(
        self,
        stdin: TextIO,
        write: Writer,
        *,
        bypass_allowed: bool = False,
        restricted: bool = False,
    ) -> None:
        self._stdin = stdin
        #: `set_permission_mode bypassPermissions` yalnız koşu buna izin verdiyse kabul edilir.
        self._bypass_allowed = bypass_allowed and not restricted
        self._restricted = restricted
        self._write = write
        self._users: queue.Queue[object] = queue.Queue()
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Future[object]]] = {}
        self._turn: tuple[asyncio.AbstractEventLoop, asyncio.Task[Any]] | None = None
        self._closed = False
        #: Sonraki turdan geçerli `set_permission_mode` / `set_model` istekleri.
        self.mode: str | None = None
        self.model: str | None = None
        self.interrupted = False
        self._thread = threading.Thread(target=self._read, name="fusion-stdin", daemon=True)

    def start(self) -> ControlChannel:
        self._thread.start()
        return self

    def users(self) -> Iterator[tuple[str, object]]:
        """Kullanıcı satırlarını sırayla ver; bozuk satır `ValueError`."""
        while True:
            item = self._users.get()
            if item is _END:
                return
            if isinstance(item, Exception):
                raise item
            assert isinstance(item, tuple)
            yield item

    # --- stdin okuma ------------------------------------------------------------- #

    def _read(self) -> None:
        try:
            for line in self._stdin:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as error:
                    self._users.put(ValueError(texts.PRINT_STREAM_LINE_INVALID.format(error=error)))
                    return
                if isinstance(data, dict):
                    self._dispatch(data)
        finally:
            self._close()

    def _close(self) -> None:
        with self._lock:
            self._closed = True
            pending = list(self._pending.values())
            self._pending.clear()
        for loop, future in pending:
            loop.call_soon_threadsafe(_settle, future, None)
        self._users.put(_END)

    def _dispatch(self, data: dict[str, object]) -> None:
        kind = data.get("type")
        if kind == "user":
            message = data.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            text = content_text(content)
            if text:
                self._users.put((text, content))
        elif kind == "control_request":
            self._request(str(data.get("request_id", "")), data.get("request"))
        elif kind == "control_response":
            self._response(data.get("response"))

    # --- SDK → Fusion denetim istekleri ------------------------------------------ #

    def _request(self, request_id: str, request: object) -> None:
        body = request if isinstance(request, dict) else {}
        subtype = str(body.get("subtype", ""))
        if subtype == "initialize":
            self._reply(request_id, {"commands": [], "output_style": "default"})
        elif subtype == "interrupt":
            self._interrupt()
            self._reply(request_id, {})
        elif subtype == "set_permission_mode":
            self._set_mode(request_id, body.get("mode"))
        elif subtype == "set_model":
            model = body.get("model")
            self.model = str(model) if isinstance(model, str) and model.strip() else None
            self._reply(request_id, {})
        else:
            self._fail(request_id, texts.PRINT_CONTROL_UNSUPPORTED.format(subtype=subtype))

    def _set_mode(self, request_id: str, mode: object) -> None:
        from .print_options import parse_permission_mode

        try:
            parsed = parse_permission_mode(str(mode or ""), skip_permissions=False)
        except ValueError as error:
            self._fail(request_id, str(error))
            return
        if parsed is ApprovalMode.BYPASS and not self._bypass_allowed:
            # Claude: bypass'a oturum içinden geçmek başlangıçta izin bayrağı ister;
            # `--restricted` koşuda hiç geçilemez.
            denied = (
                texts.PRINT_RESTRICTED_BYPASS
                if self._restricted
                else texts.PRINT_BYPASS_NOT_ALLOWED
            )
            self._fail(request_id, denied)
            return
        self.mode = str(mode)
        self._reply(request_id, {})

    def _reply(self, request_id: str, response: dict[str, object]) -> None:
        self._write(
            {
                "type": "control_response",
                "response": {"subtype": "success", "request_id": request_id, "response": response},
            }
        )

    def _fail(self, request_id: str, error: str) -> None:
        self._write(
            {
                "type": "control_response",
                "response": {"subtype": "error", "request_id": request_id, "error": error},
            }
        )

    def _interrupt(self) -> None:
        with self._lock:
            turn = self._turn
        if turn is None:
            return
        self.interrupted = True
        loop, task = turn
        loop.call_soon_threadsafe(task.cancel)

    # --- süren tur ve onay soruları ---------------------------------------------- #

    async def guard(self, coro: Coroutine[Any, Any, T]) -> T:
        """Turu kesilebilir koş: `interrupt` gelirse görev iptal edilir."""
        task = asyncio.current_task()
        assert task is not None
        self.interrupted = False
        with self._lock:
            self._turn = (asyncio.get_running_loop(), task)
        try:
            return await coro
        finally:
            with self._lock:
                self._turn = None

    async def can_use_tool(self, tool_name: str, args: dict[str, object], call_id: str) -> object:
        """SDK'ya onay sor; cevabın `response` gövdesini (ya da `None`) döndür."""
        request_id = f"fusion_{uuid.uuid4().hex[:16]}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future[object] = loop.create_future()
        with self._lock:
            if self._closed:
                return None
            self._pending[request_id] = (loop, future)
        self._write(
            {
                "type": "control_request",
                "request_id": request_id,
                "request": {
                    "subtype": "can_use_tool",
                    "tool_name": tool_name,
                    "input": args,
                    "permission_suggestions": [],
                    "tool_use_id": call_id,
                },
            }
        )
        try:
            return await future
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def _response(self, response: object) -> None:
        if not isinstance(response, dict):
            return
        request_id = str(response.get("request_id", ""))
        with self._lock:
            entry = self._pending.pop(request_id, None)
        if entry is None:
            return
        loop, future = entry
        body = response.get("response") if response.get("subtype") == "success" else None
        loop.call_soon_threadsafe(_settle, future, body)


def _settle(future: asyncio.Future[object], value: object) -> None:
    if not future.done():
        future.set_result(value)


class StdioPrompter(PrintPrompter):
    """`--permission-prompt-tool stdio`: onayları SDK'ya denetim isteğiyle sorar."""

    def __init__(self, channel: ControlChannel) -> None:
        super().__init__()
        self._channel = channel

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer:
        self.requests.append(request)
        body = await self._channel.can_use_tool(
            claude_tool_name(request.tool.name),
            dict(request.args),
            str(getattr(request, "call_id", "") or ""),
        )
        if isinstance(body, Mapping) and str(body.get("behavior", "")).lower() == "allow":
            return ApprovalAnswer.ONCE
        return ApprovalAnswer.UNAVAILABLE
