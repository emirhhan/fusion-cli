"""`monitor` ws kaynağı: WebSocket'in her metin iletisi tura olay olur (Claude Monitor, #336).

Claude Code Monitor `ws: {url, protocols?}` alır; her metin çerçevesi bir olaydır, süre
kuralları komut kaynağıyla aynıdır. Komut izlemesi Bash izin kurallarına tabidir, WebSocket
izlemesi ise AYRICA onay ister (onay katmanı: `engines.agent.approval`). İzleme Fusion
sürecinde bir iş parçacığıdır; kimliği `task_stop` ile durdurulur (`stop_ws_watch`).
"""

from __future__ import annotations

import secrets
import ssl
import threading
import time
from collections.abc import Sequence

from ..core.background_events import BackgroundEvents
from ..core.errors import FusionError
from ..core.tools import ToolArgs, ToolResult
from .ws_client import WebSocketError, parse_ws_url, read_text_messages

__all__ = ["is_ws_watch", "parse_ws_source", "start_ws_watch", "stop_ws_watch", "ws_url"]

_ACTIVE: dict[str, threading.Event] = {}
_LOCK = threading.Lock()
_LABEL_CHARS = 80


def ws_url(args: ToolArgs) -> str | None:
    """Çağrının ws adresi (onay katmanı ve kapsam anahtarı için); yoksa None."""
    source = args.get("ws")
    url = source.get("url") if isinstance(source, dict) else None
    return url.strip() if isinstance(url, str) and url.strip() else None


def is_ws_watch(tool_name: str, args: ToolArgs) -> bool:
    """`monitor` çağrısı komut değil WebSocket mi izliyor?"""
    return tool_name == "monitor" and "ws" in args and not isinstance(args.get("command"), str)


def parse_ws_source(raw: object) -> tuple[str, tuple[str, ...]] | ToolResult:
    """`{url, protocols?}` doğrula."""
    if not isinstance(raw, dict) or not isinstance(raw.get("url"), str):
        return ToolResult.failure("'ws' {url, protocols?} nesnesi olmalı.")
    try:
        parse_ws_url(raw["url"])
    except FusionError as error:
        return ToolResult.failure(str(error))
    protocols = raw.get("protocols") or []
    if not isinstance(protocols, list) or not all(isinstance(p, str) for p in protocols):
        return ToolResult.failure("'ws.protocols' metin listesi olmalı.")
    return raw["url"].strip(), tuple(protocols)


def stop_ws_watch(task_id: str) -> bool:
    """Süren WebSocket izlemesini durdur; böyle bir izleme yoksa False."""
    with _LOCK:
        stop = _ACTIVE.get(task_id)
    if stop is None:
        return False
    stop.set()
    return True


def start_ws_watch(
    events: BackgroundEvents,
    url: str,
    protocols: Sequence[str],
    label: str,
    timeout_ms: int,
    *,
    tls_context: ssl.SSLContext | None = None,
) -> str:
    """İzlemeyi başlat; görev kimliğini döndür."""
    task_id = f"ws{secrets.token_hex(4)}"
    stop = threading.Event()
    with _LOCK:
        _ACTIVE[task_id] = stop
    watch = _WsWatch(events, task_id, url, tuple(protocols), label, timeout_ms, stop, tls_context)
    watch.start()
    return task_id


class _WsWatch(threading.Thread):
    def __init__(
        self,
        events: BackgroundEvents,
        task_id: str,
        url: str,
        protocols: tuple[str, ...],
        label: str,
        timeout_ms: int,
        stop: threading.Event,
        tls_context: ssl.SSLContext | None,
    ) -> None:
        super().__init__(name=f"fusion-monitor-{task_id}", daemon=True)
        self._events, self._id, self._url, self._protocols = events, task_id, url, protocols
        self._label = " ".join(label.split())[:_LABEL_CHARS]
        self._deadline = time.monotonic() + timeout_ms / 1000
        self._stop_event, self._tls = stop, tls_context

    def _prefix(self) -> str:
        return f"[monitor {self._id} · {self._label}]"

    def _expired(self) -> bool:
        return time.monotonic() >= self._deadline

    def _should_stop(self) -> bool:
        return self._stop_event.is_set() or self._expired()

    def _emit(self, text: str) -> None:
        for line in text.splitlines() or [text]:
            if line.strip():
                self._events.push(f"{self._prefix()} {line.rstrip()}")

    def run(self) -> None:
        try:
            reason = read_text_messages(
                self._url,
                self._protocols,
                self._emit,
                self._should_stop,
                tls_context=self._tls,
            )
        except (WebSocketError, OSError) as error:
            self._events.push(f"{self._prefix()} izleme hatayla bitti: {error}")
            return
        finally:
            with _LOCK:
                _ACTIVE.pop(self._id, None)
        if self._expired() and not self._stop_event.is_set():
            self._events.push(
                f"{self._prefix()} süre doldu, izleme durduruldu; gerekirse yeni bir izleme başlat."
            )
        elif not self._stop_event.is_set():
            self._events.push(f"{self._prefix()} izleme bitti ({reason}).")
