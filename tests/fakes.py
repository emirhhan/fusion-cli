"""Testlerde kullanılan sahte sağlayıcılar ve dinleyiciler (ağ erişimi YOK)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fusion_cli.core.events import Event
from fusion_cli.core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    TextChunk,
    TokenUsage,
)


class FakeProvider:
    """Verilen parçaları akıtan, istenirse geciken/başarısız olan sahte sağlayıcı."""

    def __init__(self, name, *, chunks=(), delay=0.0, ok=True, error=None):
        self._name = name
        self._chunks = tuple(chunks)
        self._delay = delay
        self._ok = ok
        self._error = error
        self.cancelled = False
        #: Sağlayıcı gerçekten çağrıldı mı? Gecikmeli yarıştırmada "yedek hiç
        #: başlatılmadı" iddiasını doğrulamak için gerekir.
        self.started = False

    @property
    def label(self):
        return self._name

    def _result(self):
        return ModelResult(
            name=self._name,
            model=self._name,
            text="".join(self._chunks),
            latency_ms=1,
            ok=self._ok,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=len(self._chunks)),
            error=self._error,
        )

    async def complete(self, request: CompletionRequest) -> ModelResult:
        self.started = True
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self._result()

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        self.started = True
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if not self._ok:
            yield StreamDone(self._result())
            return
        for chunk in self._chunks:
            yield TextChunk(chunk)
        yield StreamDone(self._result())


class RecordingSink:
    """Gelen olayları sırayla biriktiren dinleyici."""

    def __init__(self):
        self.events: list[Event] = []

    def handle(self, event: Event) -> None:
        self.events.append(event)


class ExplodingSink:
    """Her olayda hata fırlatan dinleyici — veriyolunun dayanıklılığını sınar."""

    def handle(self, event: Event) -> None:
        raise RuntimeError("dinleyici patladı")


def request(**overrides) -> CompletionRequest:
    from fusion_cli.core.types import Message

    defaults = {
        "messages": (Message("user", "merhaba"),),
        "temperature": 0.0,
        "max_tokens": 16,
        "timeout_s": 5.0,
        "max_retries": 0,
    }
    defaults.update(overrides)
    return CompletionRequest(**defaults)


def make_config(**overrides):
    """Testler için tam bir Config. Alanlar override ile değiştirilebilir.

    `memory_dir` verilmezse izole geçici bir dizin kullanılır; testler paylaşımlı
    bir `/tmp` yolunu paylaşmaz (RULES: testler yalnızca izole geçici alana yazar).
    """
    import tempfile
    from pathlib import Path as _Path

    from fusion_cli.config.models import Config, RuntimeConfig
    from fusion_cli.core.reasoning import ReasoningEffort
    from fusion_cli.core.types import ModelSpec

    runtime_overrides = overrides.pop("runtime", {})
    runtime = {
        "request_timeout_s": 5.0,
        "max_retries": 0,
        "temperature": 0.0,
        "judge_temperature": 0.0,
        "utility_temperature": 0.1,
        "reasoning_effort": ReasoningEffort.AUTO,
        "circuit_failure_threshold": 3,
        "circuit_cooldown_s": 60.0,
        "reliability_alpha": 0.3,
        "max_tokens": 32,
        # Testlerde yeniden deneme kapalıdır: gerçek gecikmeler 34 ve 68 saniyedir
        # ve her testi bekletirdi. Yeniden denemenin kendi davranışı
        # `test_retrying.py` içinde sahte uyutucuyla açıkça sınanır.
        "retry_delays_s": (),
        "judge_timeout_s": 5.0,
        "judge_max_tokens": 64,
        "min_successful_candidates": 1,
        "straggler_grace_s": 0.05,
        "candidate_hard_cap_s": 1.0,
        "synthesis": True,
        "verified_synthesis": False,
        "provider": "auto",
        "agent_max_steps": 8,
        "self_review": False,
        "reflexion": True,
        "lessons": False,
    }
    runtime.update(runtime_overrides)

    from fusion_cli.config.models import EmbeddingConfig

    defaults = {
        "agent": ModelSpec(name="agent", model="sahte/agent"),
        "candidates": (
            ModelSpec(name="a", model="sahte/a"),
            ModelSpec(name="b", model="sahte/b"),
            ModelSpec(name="c", model="sahte/c"),
        ),
        "judge": ModelSpec(name="hakem", model="sahte/hakem"),
        "vision": None,
        "task_model_map": {"general": "a", "code": "c"},
        "runtime": RuntimeConfig(**runtime),
        "embedding": EmbeddingConfig(provider="local", model="test"),
        "memory_dir": _Path(tempfile.mkdtemp(prefix="fusion-test-memory-")),
        "source": _Path("test"),
    }
    defaults.update(overrides)
    return Config(**defaults)


def patch_providers(monkeypatch, module, by_name):
    """`build_provider`'ı sahte sağlayıcılarla değiştir.

    `by_name`: rol adı → FakeProvider. Olay yayını istenirse EventingProvider ile sarılır.
    """
    from fusion_cli.core.events import Channel
    from fusion_cli.providers.eventing import EventingProvider

    def _build(
        spec,
        *,
        publisher,
        retry_delays_s=(),
        channel=Channel.MAIN,
        clock=None,
        sleeper=None,
        background=False,
    ):
        provider = by_name[spec.name]
        if publisher is None:
            return provider
        return EventingProvider(
            provider,
            publisher=publisher,
            role=spec.name,
            channel=channel,
            background=background,
        )

    monkeypatch.setattr(module, "build_provider", _build)


class ScriptedProvider:
    """Sırayla verilen ModelResult'ları döndüren sağlayıcı (agent döngüsü testleri için)."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0
        self.seen_messages = []
        self.seen_requests = []

    @property
    def label(self):
        return "scripted"

    async def complete(self, request):
        return self._next(request)

    async def stream(self, request):
        from fusion_cli.core.types import StreamDone, TextChunk

        result = self._next(request)
        if result.text:
            yield TextChunk(result.text)
        yield StreamDone(result)

    def _next(self, request):
        self.seen_messages.append(list(request.messages))
        self.seen_requests.append(list(request.tools))
        self.calls += 1
        if not self._results:
            return _sonuc("(betik bitti)")
        return self._results.pop(0)


def _sonuc(text="", *, tool_calls=(), ok=True, error=None):
    from fusion_cli.core.types import ModelResult

    return ModelResult(
        name="agent",
        model="sahte",
        text=text,
        latency_ms=1,
        ok=ok,
        error=error,
        tool_calls=tuple(tool_calls),
    )


def model_result(text="", *, tool_calls=(), ok=True, error=None):
    return _sonuc(text, tool_calls=tool_calls, ok=ok, error=error)


def tool_call(name, **args):
    import json

    from fusion_cli.core.types import ToolCall

    return ToolCall(id=f"call_{name}", name=name, arguments=json.dumps(args))


class AlwaysApprove:
    async def confirm(self, request):
        return True


class AlwaysReject:
    async def confirm(self, request):
        return False


class ScriptedAsker:
    """ask_user için sabit cevap veren sahte kullanıcı."""

    def __init__(self, answer="sahte cevap"):
        self.answer = answer
        self.questions = []

    async def ask(self, question):
        self.questions.append(question)
        return self.answer
