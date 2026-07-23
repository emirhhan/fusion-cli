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

import os
from typing import Any

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

#: `.env.example` içindeki örnek değerler izlemeyi AÇMAMALIDIR.
_PLACEHOLDER_MARKER = "..."


def is_configured() -> bool:
    """Gerçek (örnek olmayan) anahtarlar tanımlı mı?"""
    return all(_is_real(os.getenv(name)) for name in (ENV_PUBLIC_KEY, ENV_SECRET_KEY))


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
        if not is_configured():
            self.disabled_reason = "anahtar tanımlı değil"
            return
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=os.environ[ENV_PUBLIC_KEY],
                secret_key=os.environ[ENV_SECRET_KEY],
                host=os.getenv(ENV_HOST) or None,
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
