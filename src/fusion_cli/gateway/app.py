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
from dataclasses import replace as _dc_replace
from typing import Any

from ..config.credentials import FernetSecretStore
from ..config.live import reload_if_changed, revision
from ..config.models import Config
from ..core.compression import compress_messages, saved_chars
from ..core.health import HealthRegistry
from ..core.protocols import LlmProvider
from ..core.redaction import redact
from ..core.routing_strategy import RoutingStrategy, order_models
from ..core.types import CompletionRequest, ModelResult, ModelSpec, StreamDone, TextChunk
from ..providers.factory import build_provider
from ..providers.key_pool import KeyPoolRegistry
from . import translate
from .analytics import Analytics, RequestRecord
from .cache import PromptCache
from .catalog_cache import CatalogCache
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
        secret_store: FernetSecretStore | None = None,
        catalog: CatalogCache | None = None,
    ) -> None:
        self._config = config
        self._config_revision = revision(config)
        self._health = health
        self._factory = provider_factory or self._default_factory
        self._key_pools = _build_key_pools(config)
        self._strategy = config.runtime.routing_strategy
        #: round-robin/random için tur-ötesi durum (modül-global değil, örneğe bağlı).
        self._rotation = 0
        self._rng = random.Random()
        #: Panelden girilen anahtarlar buraya ŞİFRELİ yazılır; ayrıca canlı ortama uygulanır.
        #: Test için enjekte edilebilir (yoksa gerçek kullanıcı deposu kurulur).
        self._secret_store = secret_store or _default_secret_store()
        #: Oturum boyunca canlı kullanım telemetrisi (panelde gösterilir).
        self._analytics = Analytics()
        #: Tam-eşleşme prompt önbelleği (token/süre tasarrufu).
        self._cache = PromptCache()
        #: Panel için birleşik model kataloğu (otomatik listeleme); TTL önbellekli.
        self._catalog = catalog or CatalogCache()

    def _refresh_config(self) -> None:
        """HTTP istek sınırlarında panel/terminal ile paylaşılan yapılandırmayı yeniden yükle."""
        updated, rev, changed = reload_if_changed(self._config, self._config_revision)
        if not changed:
            self._config_revision = rev
            return
        self._config = updated
        self._config_revision = rev
        self._key_pools = _build_key_pools(updated)
        self._strategy = updated.runtime.routing_strategy

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
        from ..providers.web_registry import web_registry_for

        return build_provider(
            spec,
            publisher=None,
            retry_delays_s=self._config.runtime.retry_delays_s,
            health=self._health,
            key_pools=self._key_pools,
            web_sessions=web_registry_for(self._config),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        self._refresh_config()
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
        if method == "GET" and path == "/api/models/catalog":
            await self._api_catalog(scope, send)
            return
        if method == "GET" and path == "/api/state":
            await self._api_state(send)
            return
        if method == "GET" and path == "/api/analytics":
            await _json(send, self._analytics.snapshot())
            return
        if method == "GET" and path == "/api/ready":
            await self._api_ready(send)
            return
        if method == "GET" and path == "/v1/route/candidates":
            await self._api_candidates(scope, send)
            return
        if method == "GET" and path == "/api/config/export":
            await self._api_export(send)
            return
        if method == "POST" and path == "/api/health/reset":
            await self._api_health_reset(send)
            return
        if method == "POST" and path == "/api/model":
            await self._api_set_model(receive, send)
            return
        if method == "POST" and path == "/api/keys":
            await self._api_set_key(receive, send)
            return
        if method == "POST" and path == "/api/keys/delete":
            await self._api_delete_key(receive, send)
            return
        if method == "POST" and path == "/api/routing":
            await self._api_set_routing(receive, send)
            return
        if method == "POST" and path == "/api/fallback":
            await self._api_set_fallback(receive, send)
            return
        if method == "POST" and path == "/v1/chat/completions":
            await self._chat(receive, send)
            return
        await _json(send, {"error": {"message": "bulunamadı", "type": "not_found"}}, status=404)

    # --- Panel yönetim uçları (yerel; durumu DEĞİŞTİRİR) -------------------- #

    async def _api_state(self, send: Send) -> None:
        """Panelin tek çağrıda ihtiyaç duyduğu her şey: sağlayıcılar, yönlendirme,
        fallback zinciri, sağlık, modeller."""
        from .. import __version__

        await _json(
            send,
            {
                "version": __version__,
                "providers": _providers_json(),
                "routing": {
                    "current": self._strategy.value,
                    "options": [strategy.value for strategy in RoutingStrategy],
                },
                "fallback": list(self._config.agent.models),
                "judge": list(self._config.judge.models),
                "health": self._health_json(),
                "models": available_models(self._config),
                "analytics": self._analytics.snapshot(),
                "secret_ready": self._secret_store.available,
                "config_path": str(self._config.source) if self._config.source else None,
                "config_revision": self._config_revision.value,
            },
        )

    async def _api_set_key(self, receive: Receive, send: Send) -> None:
        """Bir sağlayıcının API anahtarını panelden gir: şifreli sakla + canlı uygula."""
        import os

        from ..providers.registry import BUILTIN_PROVIDERS

        body = await _read_json(receive)
        provider_id = str(body.get("provider", ""))
        value = str(body.get("value", "")).strip()
        definition = next((p for p in BUILTIN_PROVIDERS if p.id == provider_id), None)
        if definition is None or definition.auth_env is None:
            await _json(
                send, _error_body("bu sağlayıcı anahtar almıyor ya da tanınmıyor"), status=400
            )
            return
        if not value:
            await _json(send, _error_body("anahtar boş olamaz"), status=400)
            return
        persisted = False
        if self._secret_store.available:
            self._secret_store.set(definition.auth_env, value)
            persisted = True
        # Her durumda CANLI uygula: çalışan gateway hemen kullanabilsin.
        os.environ[definition.auth_env] = value
        await _json(send, {"ok": True, "persisted": persisted, "provider": provider_id})

    async def _api_delete_key(self, receive: Receive, send: Send) -> None:
        import os

        from ..providers.registry import BUILTIN_PROVIDERS

        body = await _read_json(receive)
        provider_id = str(body.get("provider", ""))
        definition = next((p for p in BUILTIN_PROVIDERS if p.id == provider_id), None)
        if definition is None or definition.auth_env is None:
            await _json(send, _error_body("tanınmayan sağlayıcı"), status=400)
            return
        if self._secret_store.available:
            self._secret_store.delete(definition.auth_env)
        os.environ.pop(definition.auth_env, None)
        await _json(send, {"ok": True, "provider": provider_id})

    async def _api_set_routing(self, receive: Receive, send: Send) -> None:
        body = await _read_json(receive)
        wanted = str(body.get("strategy", ""))
        try:
            self._strategy = RoutingStrategy(wanted)
        except ValueError:
            await _json(send, _error_body(f"geçersiz strateji: {wanted}"), status=400)
            return
        await _json(send, {"ok": True, "strategy": self._strategy.value})

    async def _api_set_fallback(self, receive: Receive, send: Send) -> None:
        """Agent rolünün yedek (fallback) zincirini panelden düzenle + kalıcılaştır."""
        from dataclasses import replace

        from ..config import writer
        from ..core.errors import ConfigError

        body = await _read_json(receive)
        models = [str(m).strip() for m in body.get("models", []) if str(m).strip()]
        if not models:
            await _json(send, _error_body("en az bir model olmalı"), status=400)
            return
        new_agent = replace(self._config.agent, model=models[0], fallback=tuple(models[1:]))
        updated = replace(self._config, agent=new_agent)
        try:
            writer.write_model_section(updated)
        except ConfigError as error:
            await _json(send, _error_body(str(error)), status=500)
            return
        self._config = updated
        self._config_revision = revision(updated)
        await _json(
            send,
            {
                "ok": True,
                "saved": True,
                "chain": list(new_agent.models),
                "config_revision": self._config_revision.value,
            },
        )

    async def _api_ready(self, send: Send) -> None:
        """Gateway kullanıma hazır mı? En az bir anahtarlı sağlayıcı kurulu mu?"""
        from ..config.keys import environ_snapshot
        from ..providers.registry import BUILTIN_PROVIDERS

        environ = environ_snapshot()
        configured = [
            p.id
            for p in BUILTIN_PROVIDERS
            if p.implemented and p.auth_env and p.is_configured(environ)
        ]
        await _json(send, {"ready": bool(configured), "configured_providers": configured})

    async def _api_candidates(self, scope: Scope, send: Send) -> None:
        """Bir model/profil için ÇALIŞTIRILACAK aday zinciri (neden bu route)."""
        from urllib.parse import parse_qs

        params = parse_qs(scope.get("query_string", b"").decode())
        model = params.get("model", ["auto"])[0]
        spec = resolve_spec(self._config, model)
        ordered = order_models(
            spec.models,
            strategy=self._strategy,
            health=self._health,
            rotation=self._rotation,
            rng=self._rng,
        )
        await _json(
            send,
            {"model": model, "strategy": self._strategy.value, "candidates": list(ordered)},
        )

    async def _api_catalog(self, scope: Scope, send: Send) -> None:
        """Sağlayıcılardan gerçekten erişilebilen modeller (panelde açılır liste).

        Katalog çekimi bloklayan (httpx) olduğu için olay döngüsünü bloklamamak
        adına iş parçacığında çalıştırılır. `?refresh=1` önbelleği zorla tazeler.
        """
        import asyncio
        from urllib.parse import parse_qs

        params = parse_qs(scope.get("query_string", b"").decode())
        refresh = params.get("refresh", ["0"])[0] in ("1", "true")
        models = await asyncio.to_thread(self._catalog.get, refresh=refresh)
        await _json(
            send,
            {
                "count": len(models),
                "models": [
                    {
                        "id": model.id,
                        "provider": model.provider,
                        "free": model.free,
                        "context_length": model.context_length,
                    }
                    for model in models
                ],
            },
        )

    async def _api_export(self, send: Send) -> None:
        """Aktif config.yaml içeriğini döndür (panelden indirilebilsin)."""
        source = self._config.source
        text = source.read_text(encoding="utf-8") if source and source.is_file() else ""
        await _json(send, {"config": text, "path": str(source) if source else None})

    async def _api_health_reset(self, send: Send) -> None:
        if self._health is not None:
            self._health.reset()
        await _json(send, {"ok": True})

    async def _api_set_model(self, receive: Receive, send: Send) -> None:
        """Bir rolün (agent/judge) modelini + yedek zincirini düzenle + kaydet."""
        from dataclasses import replace

        from ..config import writer
        from ..core.errors import ConfigError

        body = await _read_json(receive)
        role = str(body.get("role", ""))
        models = [str(m).strip() for m in body.get("models", []) if str(m).strip()]
        if role not in ("agent", "judge") or not models:
            await _json(
                send, _error_body("rol 'agent'|'judge' ve en az bir model olmalı"), status=400
            )
            return
        current = self._config.agent if role == "agent" else self._config.judge
        spec = replace(current, model=models[0], fallback=tuple(models[1:]))
        updated = (
            replace(self._config, agent=spec)
            if role == "agent"
            else replace(self._config, judge=spec)
        )
        try:
            writer.write_model_section(updated)
        except ConfigError as error:
            await _json(send, _error_body(str(error)), status=500)
            return
        self._config = updated
        self._config_revision = revision(updated)
        await _json(
            send,
            {
                "ok": True,
                "saved": True,
                "role": role,
                "chain": list(spec.models),
                "config_revision": self._config_revision.value,
            },
        )

    def _health_json(self) -> list[dict[str, Any]]:
        if self._health is None:
            return []
        return [
            {
                "model": model_id,
                "score": round(entry.score, 3),
                "phase": entry.phase.value,
                "samples": entry.samples,
                "avg_latency_ms": round(entry.avg_latency_ms),
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

        runtime = self._config.runtime
        # Güvenli sıkıştırma (opt-in): giden mesajları kısalt, tasarrufu say.
        if runtime.gateway_compression:
            original = request.messages
            request = _dc_replace(request, messages=compress_messages(request.messages))
            self._analytics.add_compression_saving(saved_chars(original, request.messages))

        spec = self._routed_spec(resolve_spec(self._config, model))
        route = f"{self._strategy.value}:{spec.model}"
        if stream:
            await self._stream(send, self._factory(spec), request, model)
            return

        # Önbellek: aynı istek daha önce geldiyse modeli hiç çağırma.
        cached = self._cache.get(model, request) if runtime.gateway_cache else None
        if cached is not None:
            result, from_cache = cached, True
        else:
            result = await self._factory(spec).complete(request)
            if runtime.gateway_cache:
                self._cache.put(model, request, result)
            from_cache = False
        # Credential guardrail: yanıtta sızan sır/anahtar desenini maskele.
        if runtime.gateway_mask_secrets and result.text:
            result = _dc_replace(result, text=redact(result.text))
        self._record(model, result, cached=from_cache)
        usage = result.usage
        await _json(
            send,
            translate.to_openai_response(result, model),
            extra_headers=[
                (b"x-fusion-route", route.encode()),
                (b"x-fusion-usage", f"{usage.prompt_tokens};{usage.completion_tokens}".encode()),
                (b"x-fusion-cache", b"HIT" if from_cache else b"MISS"),
            ],
        )

    def _record(self, requested: str, result: ModelResult, *, cached: bool = False) -> None:
        """Bir isteği telemetriye işle (metin saklanmaz)."""
        self._analytics.record(
            RequestRecord(
                requested_model=requested,
                served_model=result.model,
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                latency_ms=result.latency_ms,
                ok=result.ok,
                cached=cached,
            )
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
                self._record(model, item.result)
        await _sse_data(send, translate.final_chunk(model, chunk_id=chunk_id, finish_reason=finish))
        await _sse_done(send)


# --------------------------------------------------------------------------- #
# Küçük ASGI yardımcıları (çerçeve kullanmamak için)
# --------------------------------------------------------------------------- #


def _default_secret_store() -> FernetSecretStore:
    """Gerçek kullanıcı sır deposunu kur (anahtar FUSION_SECRET_KEY'den)."""
    from ..config.keys import secret_key
    from ..config.paths import credentials_file

    return FernetSecretStore(credentials_file(), secret_key=secret_key())


def _build_key_pools(config: Config) -> KeyPoolRegistry:
    """Ortamdaki çoklu anahtarlardan havuz kaydı kur (cooldown circuit'inkiyle aynı)."""
    from ..config.keys import environ_snapshot

    return KeyPoolRegistry(environ_snapshot(), cooldown_s=config.runtime.circuit_cooldown_s)


def _error_body(message: str) -> dict[str, Any]:
    return {"error": {"message": message, "type": "invalid_request_error"}}


def _providers_json() -> list[dict[str, Any]]:
    """Panel için sağlayıcı listesi: tür, resmiyet, risk, kurulu-mu, çalışır-mı."""
    from ..config.key_pool import collect_keys
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
            # Kaç hesap (anahtar) bağlı? Çok-hesap havuzunun panelde görünür hâli.
            "keys": len(collect_keys(p.auth_env, environ)) if p.auth_env else 0,
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
