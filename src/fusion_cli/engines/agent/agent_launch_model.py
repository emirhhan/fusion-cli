"""Ajan modeli seçimini yapılandırılmış kimliklerle, ağ olmadan çöz."""

from __future__ import annotations

import logging
import re
from dataclasses import replace

from ...config.agent_launch_settings import AgentLaunchConfig
from ...core.errors import ConfigError
from ...core.types import ModelSpec

_LOG = logging.getLogger(__name__)
CLAUDE_ALIASES = frozenset({"sonnet", "opus", "haiku", "fable"})
UNRESOLVED_MODEL_ALIAS = (
    "Alt ajan modeli '{model}' çözülemedi. candidates içinde bu takma adla veya "
    "Claude ailesiyle bir model yapılandırın ya da tam sağlayıcı/model kimliğini yazın."
)
SUBSTITUTION_WARNING = "Alt ajan modeli '%s' yerine '%s' uygulanıyor (model izin listesi)."
_SUBSTITUTING_PROVIDERS = frozenset({"anthropic", "mantle"})


def claude_family(model: str) -> str | None:
    """Sağlayıcı yolunu ve bağlam sonekini sürümden bağımsız aileye indirger."""
    tokens = re.split(r"[-_./:\[\]]+", model.lower())
    if "claude" not in tokens and "anthropic" not in tokens:
        return model.lower() if model.lower() in CLAUDE_ALIASES else None
    return next((token for token in tokens if token in CLAUDE_ALIASES), None)


def resolve_agent_model(
    requested: str,
    parent: ModelSpec,
    *,
    candidates: tuple[ModelSpec, ...],
    launch: AgentLaunchConfig,
    invocation_model: str = "",
    keep_builtin_model: bool = False,
) -> ModelSpec | None:
    """Çağrı → tanım → ortam → üst; FORCE ve katı kimlik ayrı üst sınırdır."""
    if parent.strict:
        return parent
    environment = launch.subagent_model.strip()
    wanted = invocation_model.strip() or requested.strip() or environment or "inherit"
    from_environment = not invocation_model.strip() and not requested.strip() and bool(environment)
    if launch.force_subagent_model:
        wanted = environment or (requested.strip() if keep_builtin_model else "inherit")
        from_environment = bool(environment)
    selected = _resolve(wanted, parent, candidates, launch, can_inherit_family=not from_environment)
    if selected is None or selected is parent or _is_allowed(selected.model, launch):
        return selected
    substitute = _allowed_family(wanted, parent, candidates, launch)
    if substitute is None and environment and environment != wanted:
        alternate = _resolve(environment, parent, candidates, launch, can_inherit_family=False)
        if alternate is not None and _is_allowed(alternate.model, launch):
            substitute = alternate
    substitute = substitute or parent
    _LOG.warning(SUBSTITUTION_WARNING, wanted, substitute.model)
    return substitute


def _resolve(
    wanted: str,
    parent: ModelSpec,
    candidates: tuple[ModelSpec, ...],
    launch: AgentLaunchConfig,
    *,
    can_inherit_family: bool,
) -> ModelSpec | None:
    alias = wanted.lower()
    if alias in ("", "inherit"):
        return parent
    if alias in CLAUDE_ALIASES:
        if can_inherit_family and claude_family(parent.model) == alias:
            return parent
        mappings = dict(launch.model_aliases)
        if (
            can_inherit_family
            and alias == "opus"
            and launch.provider != "anthropic"
            and launch.unresolved_parent_family
            and claude_family(parent.model) is None
            and alias not in mappings
        ):
            return parent
        mapped = mappings.get(alias)
        candidate = (
            next((item for item in candidates if item.model == mapped), None) if mapped else None
        )
        if candidate is None and mapped is None:
            candidate = next((item for item in candidates if item.name.lower() == alias), None)
            candidate = candidate or next(
                (item for item in candidates if claude_family(item.model) == alias), None
            )
        if candidate is not None:
            return _with_fallback(candidate, parent)
        if mapped:
            return ModelSpec(name=parent.name, model=_model_id(mapped), fallback=parent.models)
        raise ConfigError(UNRESOLVED_MODEL_ALIAS.format(model=wanted))
    model = _model_id(wanted)
    if "/" not in model:
        _LOG.warning("alt ajan modeli tanınmadı", extra={"model": wanted})
        return None
    if model == parent.model:
        return parent
    candidate = next((item for item in candidates if item.model == model), None)
    return (
        _with_fallback(candidate, parent)
        if candidate is not None
        else ModelSpec(parent.name, model, fallback=parent.models)
    )


def _model_id(model: str) -> str:
    return f"anthropic/{model}" if model.startswith("claude-") else model


def _with_fallback(candidate: ModelSpec, parent: ModelSpec) -> ModelSpec:
    extra = tuple(item for item in parent.models if item not in candidate.models)
    return replace(candidate, fallback=(*candidate.fallback, *extra))


def _is_allowed(model: str, launch: AgentLaunchConfig) -> bool:
    allowed = launch.available_models
    if allowed is None:
        return True
    family = claude_family(model)
    specific = tuple(
        item for item in allowed if item not in CLAUDE_ALIASES and claude_family(item) == family
    )
    for item in allowed:
        if item in CLAUDE_ALIASES:
            if item == family and not specific:
                return True
        elif model == item or model.rsplit("/", 1)[-1].startswith(item.rsplit("/", 1)[-1]):
            return True
    return False


def _allowed_family(
    requested: str,
    parent: ModelSpec,
    candidates: tuple[ModelSpec, ...],
    launch: AgentLaunchConfig,
) -> ModelSpec | None:
    alias = requested.lower()
    if alias not in CLAUDE_ALIASES or launch.provider not in _SUBSTITUTING_PROVIDERS:
        return None
    explicit = tuple(
        ModelSpec("izinli", _model_id(item))
        for item in launch.available_models or ()
        if item.startswith("claude-") or "/" in item
    )
    permitted = tuple(
        item
        for item in (*candidates, *explicit)
        if claude_family(item.model) == alias and _is_allowed(item.model, launch)
    )
    if not permitted:
        return None
    selected = max(
        permitted, key=lambda item: tuple(int(part) for part in re.findall(r"\d+", item.model))
    )
    return _with_fallback(selected, parent)
