"""Ana ajan ayarlarını mevcut AgentDeps nesnesine bağlayan dar köprü."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from . import team_settings

if TYPE_CHECKING:
    from .loop import AgentDeps
    from .team import Persona


def prepare_main_agent(deps: AgentDeps, persona: Persona) -> None:
    """Taze kök tur bağımlılıklarına uygula; ortak bütçeyi/kapsamı değiştirme."""
    explicit = deps.active_model_override
    if not deps.main_config_applied:
        base = replace(deps.config, agent=explicit) if explicit is not None else deps.config
        effective = replace(persona, model="") if explicit is not None else persona
        deps.config = team_settings.main_agent_config(
            base, effective, root=deps.tool_context.root, home=deps.home
        )
    deps.active_model_override = explicit if explicit is not None else deps.config.agent
    effective_policy = replace(persona, permission_mode="") if deps.main_config_applied else persona
    policy, factory = team_settings.child_policies(
        deps, effective_policy, team_settings.agent_label(persona, "ana")
    )
    mode_reader = team_settings.child_approval_mode(deps, effective_policy)
    deps.policy, deps.policy_factory = policy, factory
    deps.approval_mode = mode_reader
