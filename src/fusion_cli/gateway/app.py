"""Yerel gateway — OpenAI-uyumlu ASGI uygulaması.

Fusion'ın router yığınını (registry + fallback + health) tek bir OpenAI-uyumlu
`/v1/chat/completions` uç noktası olarak açar. Böylece SENİN BİLGİSAYARINDAKİ her
araç (Cursor, Cline, hatta Claude Code) Fusion'a bağlanabilir — hiçbir uygulamayı
bozmadan/rootlamadan. Uzak sunucu DEĞİLDİR; yalnız yerelde (127.0.0.1) çalışır.

Çerçeve yok: saf ASGI. `uvicorn` ile çalışır (`gateway` ekstrası). Test için gerçek
sunucu gerekmez — `httpx.ASGITransport` ile doğrudan çağrılır.
"""

from __future__ import annotations

import json
import random
from collections.abc import Awaitable, Callable
from typing import Any

from ..config.models import Config
from ..core.health import HealthRegistry
from ..core.protocols import LlmProvider
from ..core.routing_strategy import order_models
from ..core.types import CompletionRequest, ModelSpec, StreamDone, TextChunk
from ..providers.factory import build_provider
from . import translate
from .routing import available_models, resolve_spec

#: `build_provider` imzasının gateway'in ihtiyaç duyduğu sadeleştirilmiş hâli.
ProviderFactory = Callable[[ModelSpec], LlmProvider]

#: ASGI3 imzaları — çerçeve kullanmadığımız için elle tiplenir.
Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class GatewayApp:
    """OpenAI-uyumlu yerel gateway (ASGI3 uygulaması)."""

    def __init__(
        self,
        config: Config,
        *,
        provider_factory: ProviderFactory | None = None,
        health: HealthRegistry | None = None,
    ) -> None:
        self._config = config
        self._health = health
        self._factory = provider_factory or self._default_factory
        self._strategy = config.runtime.routing_strategy
        #: round-robin/random için tur-ötesi durum (modül-global değil, örneğe bağlı).
        self._rotation = 0
        self._rng = random.Random()

    def _routed_spec(self, spec: ModelSpec) -> ModelSpec:
        """Yedek zincirini seçili stratejiye göre yeniden sırala (hiçbir modeli düşürmez)."""
        ordered = order_models(
            spec.models,
            strategy=self._strategy,
            health=self._health,
            rotation=self._rotation,
            rng=self._rng,
        )
        self._rotation += 1
        return ModelSpec(name=spec.name, model=ordered[0], fallback=ordered[1:], tags=spec.tags)

    def _default_factory(self, spec: ModelSpec) -> LlmProvider:
        return build_provider(
            spec,
            publisher=None,
            retry_delays_s=self._config.runtime.retry_delays_s,
            health=self._health,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        method = scope["method"]
        path = scope["path"]
        if method == "GET" and path in ("/", "/health"):
            await _json(send, {"status": "ok", "service": "fusion-gateway"})
            return
        if method == "GET" and path == "/v1/models":
            await self._models(send)
            return
        if method == "GET" and path in ("/dashboard", "/dashboard/"):
            await _html(send, _dashboard_html())
            return
        if method == "GET" and path == "/api/providers":
            await _json(send, {"providers": _providers_json()})
            return
        if method == "GET" and path == "/api/health":
            await _json(send, {"models": self._health_json()})
            return
        if method == "GET" and path == "/api/models":
            await self._models(send)
            return
        if method == "POST" and path == "/v1/chat/completions":
            await self._chat(receive, send)
            return
        await _json(send, {"error": {"message": "bulunamadı", "type": "not_found"}}, status=404)

    def _health_json(self) -> list[dict[str, Any]]:
        if self._health is None:
            return []
        return [
            {
                "model": model_id,
                "score": round(entry.score, 3),
                "phase": entry.phase.value,
                "samples": entry.samples,
            }
            for model_id, entry in self._health.snapshot()
        ]

    async def _models(self, send: Send) -> None:
        data = [
            {"id": mid, "object": "model", "owned_by": "fusion"}
            for mid in available_models(self._config)
        ]
        await _json(send, {"object": "list", "data": data})

    async def _chat(self, receive: Receive, send: Send) -> None:
        try:
            payload = await _read_json(receive)
            request, model, stream = translate.to_request(payload, self._config.runtime)
        except (translate.GatewayError, json.JSONDecodeError, ValueError) as error:
            await _json(send, _error_body(str(error)), status=400)
            return

        spec = self._routed_spec(resolve_spec(self._config, model))
        provider = self._factory(spec)
        route = f"{self._strategy.value}:{spec.model}"
        if stream:
            await self._stream(send, provider, request, model)
        else:
            result = await provider.complete(request)
            await _json(
                send,
                translate.to_openai_response(result, model),
                extra_headers=[(b"x-fusion-route", route.encode())],
            )

    async def _stream(
        self, send: Send, provider: LlmProvider, request: CompletionRequest, model: str
    ) -> None:
        chunk_id = f"fusion-{id(request)}"
        await _sse_start(send)
        finish = "stop"
        async for item in provider.stream(request):
            if isinstance(item, TextChunk) and item.text:
                await _sse_data(
                    send, translate.to_openai_chunk(item.text, model, chunk_id=chunk_id)
                )
            elif isinstance(item, StreamDone):
                finish = "stop" if item.result.is_usable else "error"
        await _sse_data(send, translate.final_chunk(model, chunk_id=chunk_id, finish_reason=finish))
        await _sse_done(send)


# --------------------------------------------------------------------------- #
# Küçük ASGI yardımcıları (çerçeve kullanmamak için)
# --------------------------------------------------------------------------- #


def _error_body(message: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": "invalid_request_error"}}


def _providers_json() -> list[dict[str, Any]]:
    """Panel için sağlayıcı listesi: tür, resmiyet, risk, kurulu-mu, çalışır-mı."""
    from ..config.keys import environ_snapshot
    from ..providers.registry import BUILTIN_PROVIDERS

    environ = environ_snapshot()
    return [
        {
            "id": p.id,
            "name": p.name,
            "kind": p.kind.value,
            "status": p.official_status.value,
            "risk": p.risk_level.value,
            "implemented": p.implemented,
            "configured": p.is_configured(environ) if p.implemented else False,
            "local": p.auth_env is None and p.implemented,
        }
        for p in BUILTIN_PROVIDERS
    ]


def _dashboard_html() -> str:
    """Yerel panel HTML'i — paket verisi olarak yüklenir (koda gömülü değil)."""
    from pathlib import Path

    return (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")


async def _html(send: Send, body: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/html; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": body.encode()})


async def _read_json(receive: Receive) -> dict[str, Any]:
    body = b""
    while True:
        event = await receive()
        body += event.get("body", b"")
        if not event.get("more_body", False):
            break
    if not body:
        return {}
    parsed = json.loads(body.decode())
    if not isinstance(parsed, dict):
        raise translate.GatewayError("gövde bir JSON nesnesi olmalı.")
    return parsed


async def _json(
    send: Send,
    data: dict[str, Any],
    *,
    status: int = 200,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = json.dumps(data).encode()
    headers = [(b"content-type", b"application/json"), *(extra_headers or [])]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _sse_start(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/event-stream"), (b"cache-control", b"no-cache")],
        }
    )


async def _sse_data(send: Send, data: dict[str, Any]) -> None:
    payload = f"data: {json.dumps(data)}\n\n".encode()
    await send({"type": "http.response.body", "body": payload, "more_body": True})


async def _sse_done(send: Send) -> None:
    await send({"type": "http.response.body", "body": b"data: [DONE]\n\n", "more_body": False})
