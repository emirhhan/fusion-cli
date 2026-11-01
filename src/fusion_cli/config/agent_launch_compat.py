"""Claude ajan ayarlarını güvenilen eski dosyalardan ve süreç ortamından bir kez oku."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.errors import ConfigError
from .agent_launch_settings import AgentLaunchConfig
from .setting_sources import SOURCE_LOCAL, SOURCE_PROJECT, SOURCE_USER, source_enabled
from .trust import is_permissions_trusted, is_project_settings_trusted

if TYPE_CHECKING:
    from .models import Config

SUBAGENT_MODEL_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"
SUBAGENT_FORCE_ENV = "CLAUDE_CODE_SUBAGENT_MODEL_FORCE"
BACKGROUND_ENV = "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"
FORK_ENV = "CLAUDE_CODE_FORK_SUBAGENT"
EXPLORE_PLAN_ENV = "CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS"
SDK_BUILTIN_ENV = "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS"
SPAWN_DEPTH_ENV = "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"
CONCURRENT_ENV = "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"
DEFAULT_MODEL_ENV = "ANTHROPIC_DEFAULT_{alias}_MODEL"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


def read_agent_launch(
    configured: AgentLaunchConfig, *, home: Path, root: Path, environ: Mapping[str, str]
) -> AgentLaunchConfig:
    """Güvenilmeyen proje ayarı kod/sunucu/model yönlendirmesi açamaz."""
    paths = [home / ".claude" / "settings.json"] if source_enabled(SOURCE_USER) else []
    if source_enabled(SOURCE_PROJECT) and is_project_settings_trusted(root):
        paths.append(root / ".claude" / "settings.json")
    if source_enabled(SOURCE_LOCAL) and is_permissions_trusted(root):
        paths.append(root / ".claude" / "settings.local.json")
    legacy = AgentLaunchConfig()
    merged_env: dict[str, str] = {}
    for path in paths:
        raw = _read(path)
        if not raw:
            continue
        legacy = _legacy(legacy, raw, path)
        env = raw.get("env")
        if isinstance(env, dict):
            merged_env.update(
                {
                    key: value
                    for key, value in env.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            )
    defaults = AgentLaunchConfig()
    values = {
        item.name: getattr(configured, item.name)
        for item in fields(configured)
        if getattr(configured, item.name) != getattr(defaults, item.name)
    }
    loaded = replace(legacy, **values)
    merged_env.update(environ)
    aliases = dict(loaded.model_aliases)
    for alias in ("sonnet", "opus", "haiku", "fable"):
        value = merged_env.get(DEFAULT_MODEL_ENV.format(alias=alias.upper()), "").strip()
        if value:
            aliases[alias] = value
    force = loaded.force_subagent_model
    if SUBAGENT_FORCE_ENV in merged_env:
        raw_force = merged_env[SUBAGENT_FORCE_ENV].strip().lower()
        if raw_force not in _TRUE_VALUES | _FALSE_VALUES:
            raise ConfigError(f"{SUBAGENT_FORCE_ENV}: 1/0 veya true/false bekleniyor.")
        force = raw_force in _TRUE_VALUES
    return replace(
        loaded,
        subagent_model=merged_env.get(SUBAGENT_MODEL_ENV, loaded.subagent_model).strip(),
        force_subagent_model=force,
        disable_background_tasks=_environment_bool(
            merged_env, BACKGROUND_ENV, loaded.disable_background_tasks
        ),
        fork_enabled=_environment_bool(merged_env, FORK_ENV, loaded.fork_enabled),
        disable_explore_plan_agents=_environment_bool(
            merged_env, EXPLORE_PLAN_ENV, loaded.disable_explore_plan_agents
        ),
        disable_builtin_agents=_environment_bool(
            merged_env, SDK_BUILTIN_ENV, loaded.disable_builtin_agents
        ),
        max_spawn_depth=_environment_count(merged_env, SPAWN_DEPTH_ENV, loaded.max_spawn_depth),
        max_concurrent_subagents=_environment_count(
            merged_env, CONCURRENT_ENV, loaded.max_concurrent_subagents
        ),
        model_aliases=tuple(aliases.items()),
    )


def reload_agent_launch(
    config: Config, *, home: Path, root: Path, environ: Mapping[str, str]
) -> Config:
    """Kök/ev değişince Claude ajan ayarlarını YAML tabanından yeniden oku (masaüstü)."""
    base = getattr(config, "agent_launch_configured", None)
    if base is None:
        return config
    return replace(
        config, agent_launch=read_agent_launch(base, home=home, root=root, environ=environ)
    )


def _read(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConfigError(
            f"Claude ajan ayarı okunamadı: {path}; JSON dosyasını düzeltin."
        ) from error
    if not isinstance(raw, dict):
        raise ConfigError(f"Claude ajan ayarı nesne olmalı: {path}")
    return raw


def _legacy(current: AgentLaunchConfig, raw: Mapping[str, object], path: Path) -> AgentLaunchConfig:
    agent = current.default_agent
    allowed = current.available_models
    disable_auto = current.disable_auto_mode
    if "agent" in raw:
        value = raw["agent"]
        if not isinstance(value, str):
            raise ConfigError(f"Claude agent ayarı metin olmalı: {path}")
        agent = value
    if "availableModels" in raw:
        models = raw["availableModels"]
        if not isinstance(models, list) or any(not isinstance(model, str) for model in models):
            raise ConfigError(f"Claude availableModels ayarı metin listesi olmalı: {path}")
        allowed = tuple(dict.fromkeys((*(allowed or ()), *(str(model) for model in models))))
    permissions = raw.get("permissions")
    if isinstance(permissions, Mapping) and "disableAutoMode" in permissions:
        value = permissions["disableAutoMode"]
        if value not in (True, False, "disable", "enable"):
            raise ConfigError(f"Claude disableAutoMode ayarı disable/enable olmalı: {path}")
        disable_auto = value in (True, "disable")
    return replace(
        current, default_agent=agent, available_models=allowed, disable_auto_mode=disable_auto
    )


def _environment_count(environ: Mapping[str, str], name: str, default: int) -> int:
    """Pozitif tam sayı bekleyen Claude ortam değişkeni; bozuk değer açık hata verir."""
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or int(raw) < 1:
        raise ConfigError(f"{name}: pozitif tam sayı bekleniyor.")
    return int(raw)


def _environment_bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    """Ortam booleanı yanlışsa sessiz izin varsayımı üretme."""
    if name not in environ:
        return default
    value = environ[name].strip().lower()
    if value not in _TRUE_VALUES | _FALSE_VALUES:
        raise ConfigError(f"{name}: 1/0 veya true/false bekleniyor.")
    return value in _TRUE_VALUES
