"""Seçili model zinciri için geçmiş sıkıştırma bütçesi."""

from __future__ import annotations

from dataclasses import dataclass

from ...config.models import Config
from ...core.types import ModelSpec
from ...providers.context_window import input_window_tokens
from .execution_policy import uses_web_context
from .history import COMPRESS_THRESHOLD_CHARS, WEB_COMPRESS_THRESHOLD_CHARS

# Tarihsel 177.000 karakter eşiğinin hesabı: 131.072 token pencereden
# çıktı ve sistem/araç payı çıktıktan sonra geçmişe yaklaşık yarısı ayrılır.
OUTPUT_RESERVE_TOKENS = 8_192
SYSTEM_AND_TOOLS_RESERVE_TOKENS = 4_000
CHARS_PER_TOKEN_ESTIMATE = 3
HISTORY_SHARE = 0.5


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """Özetleme eşiği ve doğrulanmış model penceresi; ikisi ayrı kavramdır."""

    compression_chars: int
    window_tokens: int | None
    model: str


def context_budget(config: Config, spec: ModelSpec) -> ContextBudget:
    """Yedek zincirin en dar bilinen penceresini kullan; bilinmeyeni gizleme."""
    if uses_web_context(config, spec):
        return ContextBudget(WEB_COMPRESS_THRESHOLD_CHARS, None, spec.model)
    models = (spec.model,) if spec.strict else spec.models
    windows = [input_window_tokens(model) for model in models]
    known = [window for window in windows if window is not None]
    if not known:
        return ContextBudget(COMPRESS_THRESHOLD_CHARS, None, spec.model)
    smallest = min(known)
    reserved = min(OUTPUT_RESERVE_TOKENS + SYSTEM_AND_TOOLS_RESERVE_TOKENS, smallest // 2)
    usable = smallest - reserved
    calculated = max(1, round(usable * HISTORY_SHARE * CHARS_PER_TOKEN_ESTIMATE))
    if len(known) != len(windows):
        return ContextBudget(min(calculated, COMPRESS_THRESHOLD_CHARS), None, spec.model)
    return ContextBudget(calculated, smallest, spec.model)
