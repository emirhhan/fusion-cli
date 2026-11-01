"""Ana/alt ajan başlatma için değişmez, anahtarsız yapılandırma."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.errors import ConfigError


@dataclass(frozen=True, slots=True)
class AgentLaunchConfig:
    """Model çözümü ve izin kullanılabilirliği; ortam bu değerden sonra okunmaz."""

    subagent_model: str = ""
    force_subagent_model: bool = False
    model_aliases: tuple[tuple[str, str], ...] = ()
    available_models: tuple[str, ...] | None = None
    provider: str = "anthropic"
    unresolved_parent_family: bool = False
    disable_auto_mode: bool = False
    disable_background_tasks: bool = False
    #: `CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS`: yalnız yerleşik Explore/Plan kaldırılır.
    disable_explore_plan_agents: bool = False
    fork_enabled: bool = True
    auto_supported_models: tuple[str, ...] = ()
    managed_agent_roots: tuple[str, ...] = ()
    default_agent: str = ""

    def __post_init__(self) -> None:
        if self.provider not in {"anthropic", "mantle", "bedrock", "vertex", "foundry", "gateway"}:
            raise ConfigError(
                "agent_launch.provider: anthropic, mantle, bedrock, vertex, "
                "foundry veya gateway olmalı."
            )
        known = {"sonnet", "opus", "haiku", "fable"}
        if any(alias not in known or not model.strip() for alias, model in self.model_aliases):
            raise ConfigError(
                "agent_launch.model_aliases: bilinen Claude takma adı ve dolu model gerekli."
            )
        if len({alias for alias, _ in self.model_aliases}) != len(self.model_aliases):
            raise ConfigError("agent_launch.model_aliases: aynı takma ad birden fazla yazılamaz.")
