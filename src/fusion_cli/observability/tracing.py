"""Langfuse izleme — olay veriyoluna takılan bir dinleyici.

Mimarinin sınavı buydu: yeni bir gözlemlenebilirlik arka ucu eklemek motor koduna
DOKUNMADAN mümkün olmalıydı. Bu dosya yalnızca `EventSink` implemente eder;
motorlar Langfuse'ün varlığından habersizdir.

Tam no-op güvenliği: anahtar yoksa, anahtar örnek değerse (`pk-lf-...`), paket
kurulu değilse ya da bağlantı kurulamıyorsa izleme sessizce kapanır ve uygulama
tam olarak çalışmaya devam eder. İzleme bir iyileştirmedir; turu düşürmesi kabul
edilemez.

Kurulum:  pip install "fusion-cli[tracing]"
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Any
from urllib.parse import urlparse

from ..core.events import (
    CandidatesStarted,
    Event,
    FusionCompleted,
    ModelCallFinished,
    SubAgentStarted,
    ToolExecuted,
    TurnFinished,
)

ENV_PUBLIC_KEY = "LANGFUSE_PUBLIC_KEY"
ENV_SECRET_KEY = "LANGFUSE_SECRET_KEY"
ENV_HOST = "LANGFUSE_HOST"
ENV_ENABLED = "FUSION_TRACING"

#: `.env.example` içindeki örnek değerler izlemeyi AÇMAMALIDIR.
_PLACEHOLDER_MARKER = "..."


def is_configured() -> bool:
    """İzleme açıkça opt-in'dir ve anahtarlar gerçek olmalıdır.

    Langfuse anahtarlarını yalnızca `.env`'de bırakmak asla gürültülü bir exporter
    başlatmamalı. Toplayıcı bilerek çalışıyorsa `FUSION_TRACING=1` verilir.
    """
    enabled = os.getenv(ENV_ENABLED, "").strip().lower() in {"1", "true", "yes", "on"}
    return enabled and all(_is_real(os.getenv(name)) for name in (ENV_PUBLIC_KEY, ENV_SECRET_KEY))


def _host_reachable(host: str | None) -> bool:
    if not host:
        return True
    parsed = urlparse(host if "://" in host else f"http://{host}")
    hostname = parsed.hostname
    if not hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((hostname, port), timeout=0.25):
            return True
    except OSError:
        return False


def _quiet_sdk_loggers() -> None:
    for name in ("langfuse", "opentelemetry", "opentelemetry.sdk", "urllib3.connectionpool"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def _is_real(value: str | None) -> bool:
    return bool(value) and _PLACEHOLDER_MARKER not in str(value)


class LangfuseTracer:
    """Olayları Langfuse'e yazan dinleyici. Kurulamazsa sessizce devre dışı kalır."""

    def __init__(self, *, task: str) -> None:
        self._client: Any = None
        self._root: Any = None
        self.disabled_reason: str | None = None
        self._start(task)

    @property
    def enabled(self) -> bool:
        return self._root is not None

    def handle(self, event: Event) -> None:
        if self._root is None:
            return
        # İzleme hiçbir koşulda turu düşürmemeli: bu bir sınır noktasıdır.
        try:
            self._record(event)
        except Exception as exc:
            self.disabled_reason = f"{type(exc).__name__}: {exc}"
            self._root = None

    def flush(self) -> None:
        """Bekleyen kayıtları gönder. Süreç kapanmadan çağrılmalıdır."""
        if self._client is None:
            return
        try:
            self._client.flush()
        except Exception:
            # Gönderilemeyen izleme verisi kaybolur; bu kabul edilebilir bir kayıptır.
            return

    # ----------------------------------------------------------------------- #

    def _start(self, task: str) -> None:
        keys = [os.getenv(name) for name in (ENV_PUBLIC_KEY, ENV_SECRET_KEY)]
        if not all(_is_real(value) for value in keys):
            self.disabled_reason = "anahtar tanımlı değil"
            return
        if not is_configured():
            self.disabled_reason = "izleme kapalı (FUSION_TRACING=1 ile açılır)"
            return
        host = os.getenv(ENV_HOST) or None
        if not _host_reachable(host):
            self.disabled_reason = f"izleme ucu erişilemiyor: {host}"
            return
        _quiet_sdk_loggers()
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=os.environ[ENV_PUBLIC_KEY],
                secret_key=os.environ[ENV_SECRET_KEY],
                host=host,
            )
            self._root = self._client.start_observation(
                name="fusion-turn", as_type="span", input=task
            )
        except ImportError:
            self.disabled_reason = 'paket kurulu değil (pip install "fusion-cli[tracing]")'
        except Exception as exc:
            self.disabled_reason = f"{type(exc).__name__}: {exc}"
            self._client = None
            self._root = None

    def _record(self, event: Event) -> None:
        if isinstance(event, ModelCallFinished):
            self._generation(event)
        elif isinstance(event, ToolExecuted):
            self._span(
                name=f"tool:{event.name}",
                metadata={"args": dict(event.args), "outcome": event.outcome.value},
                output=event.output[:2000],
            )
        elif isinstance(event, CandidatesStarted):
            self._span(name="candidates", metadata={"names": list(event.names)})
        elif isinstance(event, SubAgentStarted):
            self._span(name="subagent", metadata={"task": event.task})
        elif isinstance(event, FusionCompleted):
            self._root.update(output=event.result.final_answer)
        elif isinstance(event, TurnFinished):
            self._root.end()

    def _generation(self, event: ModelCallFinished) -> None:
        result = event.result
        observation = self._root.start_observation(
            name=f"model:{event.role}",
            as_type="generation",
            model=result.model,
            output=result.text if result.ok else (result.error or ""),
            usage_details={
                "input": result.usage.prompt_tokens,
                "output": result.usage.completion_tokens,
            },
            metadata={"latency_ms": result.latency_ms, "cost_usd": result.usage.cost_usd},
            level="DEFAULT" if result.ok else "ERROR",
        )
        observation.end()

    def _span(self, *, name: str, metadata: dict[str, Any], output: str | None = None) -> None:
        observation = self._root.start_observation(
            name=name, as_type="span", metadata=metadata, output=output
        )
        observation.end()
