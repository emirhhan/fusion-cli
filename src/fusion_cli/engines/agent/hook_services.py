"""Kanca oturumuna model ve MCP erişimi bağlama (`mcp_tool`/`prompt`/`agent` türleri).

Claude Code `prompt` kancasını arka plan modeliyle (`model` yazılmadıysa) tek atışta,
`agent` kancasını Read/Grep/Glob'lu alt ajanla (en çok 50 tur) çalıştırır; `mcp_tool`
kancası yapılandırılmış sunucunun aracını onay akışına sokmadan çağırır (kanca
kullanıcının kendi ayarıdır). Fusion'da arka plan modeli hakem (`judge`) rolüdür.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any

from ...core.errors import FusionError
from ...core.events import NarrationPublished
from ...core.types import CompletionRequest, Message, ModelSpec
from ...mcp_bridge.elicitation_hooks import register_elicitation_hooks
from ...mcp_bridge.tool_name import fusion_tool_name
from ..hooks.handlers import EVALUATOR_SYSTEM, HookServices
from .skill_hooks import activate_selected_skill

if TYPE_CHECKING:
    from ...config.models import Config
    from .loop import AgentDeps

_LOG = logging.getLogger(__name__)
#: Claude: ajan kancası en çok 50 tur.
AGENT_HOOK_MAX_TURNS = 50
#: Ajan kancasının araçları (Claude Read, Grep, Glob ve LS karşılıkları).
AGENT_HOOK_TOOLS = frozenset(
    {"read_file", "view_file", "glob", "grep_search", "search_code", "list_dir", "list_files"}
)
_MODEL_MAX_TOKENS = 1024
_CLAUDE_ALIASES = ("haiku", "sonnet", "opus", "fable")


def hook_model_spec(config: Config, model: str) -> ModelSpec:
    """`model` alanı: boş → arka plan (hakem) modeli; tam kimlik ya da Claude takma adı."""
    wanted = model.strip()
    if not wanted:
        return config.judge
    if "/" in wanted:
        return ModelSpec(name=wanted, model=wanted)
    alias = wanted.lower()
    if alias in _CLAUDE_ALIASES:
        for spec in (config.judge, config.agent, *config.candidates):
            if alias in spec.model.lower():
                return spec
    return config.judge


def bind_hook_services(deps: AgentDeps, run_agent: Callable[..., Awaitable[Any]]) -> None:
    """Kök turda (UserPromptSubmit'ten önce) kanca oturumuna erişimleri bağla.

    MCP aracı çağrı anında temel defterde aranır: bağlayıcı araçları oraya kaydeder.
    """
    hooks = getattr(deps, "hooks", None)
    if hooks is None:
        return
    activate_selected_skill(deps)
    publisher = getattr(deps, "publisher", None)
    if publisher is not None:
        hooks.status_sink = lambda text: publisher.publish(NarrationPublished(text=text))
    hooks.services = HookServices(
        model_call=_model_call(deps),
        agent_call=_agent_call(deps, run_agent),
        mcp_call=_mcp_call(deps),
    )
    # MCP elicitation isteği bu oturumun Elicitation/ElicitationResult kancalarından geçer.
    from ..hooks.elicitation import SessionElicitationHooks  # döngüsel içe aktarma: notify

    register_elicitation_hooks(SessionElicitationHooks(hooks))


def _model_call(deps: AgentDeps) -> Callable[[str, str, float], Awaitable[str]]:
    async def call(prompt: str, model: str, timeout_s: float) -> str:
        from ...config.model_lookup import configured_model_specs
        from ...providers.factory import build_provider
        from ...providers.web_registry import web_registry_for

        config = deps.config
        request = CompletionRequest(
            messages=(Message("system", EVALUATOR_SYSTEM), Message("user", prompt)),
            temperature=config.runtime.utility_temperature,
            max_tokens=_MODEL_MAX_TOKENS,
            timeout_s=timeout_s,
            max_retries=config.runtime.max_retries,
        )
        try:
            provider = build_provider(
                hook_model_spec(config, model),
                publisher=getattr(deps, "publisher", None),
                retry_delays_s=config.runtime.retry_delays_s,
                background=True,
                web_sessions=web_registry_for(config),
                model_specs=configured_model_specs(config),
            )
            result = await provider.complete(request)
        except (FusionError, OSError) as error:
            raise RuntimeError(f"model kancası çalışmadı: {error}") from error
        if not result.ok:
            raise RuntimeError("model kancası: sağlayıcı hata döndürdü")
        return result.text

    return call


def _agent_call(
    deps: AgentDeps, run_agent: Callable[..., Awaitable[Any]]
) -> Callable[[str, str, float], Awaitable[str]]:
    async def call(prompt: str, model: str, timeout_s: float) -> str:
        child = dataclasses.replace(deps, hooks=None)
        if model.strip():
            child = dataclasses.replace(
                child, active_model_override=hook_model_spec(deps.config, model)
            )
        task = f"{EVALUATOR_SYSTEM}\n\n{prompt}"
        outcome = await run_agent(
            task,
            child,
            depth=1,
            self_review=False,
            plan_mode=True,
            verify=False,
            internal=True,
            allowed_tools=set(AGENT_HOOK_TOOLS),
            step_limit=AGENT_HOOK_MAX_TURNS,
        )
        if not outcome.ok:
            raise RuntimeError(outcome.final_text or "ajan kancası başarısız")
        return str(outcome.final_text)

    return call


def fusion_server_name(server: str) -> str:
    """Claude'un eklenti sunucusu adı `plugin:<eklenti>:<sunucu>` → Fusion kayıt adı."""
    prefix, _, rest = server.partition(":")
    plugin, _, name = rest.partition(":")
    if prefix != "plugin" or not plugin or not name:
        return server
    from ...config.plugin_layout import server_name

    return server_name(plugin, name)


def _mcp_call(
    deps: AgentDeps,
) -> Callable[[str, str, Mapping[str, object]], Awaitable[tuple[str, bool]]]:
    async def call(server: str, tool: str, args: Mapping[str, object]) -> tuple[str, bool]:
        registry = getattr(deps, "base_registry", None)
        name = fusion_tool_name(fusion_server_name(server), tool)
        found = registry.get(name) if registry is not None else None
        if found is None:
            raise LookupError(server)
        try:
            result = await found.run(dict(args), deps.tool_context)
        except asyncio.CancelledError:
            raise
        except (FusionError, OSError, RuntimeError, ValueError) as error:
            _LOG.warning("mcp_tool kancası çağrılamadı: %s", type(error).__name__)
            return str(error), True
        return result.output, not result.ok

    return call
