"""Seçili model zinciri için geçmiş sıkıştırma bütçesi."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ...config.models import Config
from ...core.types import ModelSpec
from ...providers.context_window import input_window_tokens
from .execution_policy import uses_web_context
from .history import COMPRESS_THRESHOLD_CHARS, WEB_COMPRESS_THRESHOLD_CHARS

# Tarihsel 177.000 karakter eşiğinin hesabı: 131.072 token pencereden
# çıktı ve sistem/araç payı çıktıktan sonra geçmişe yaklaşık yarısı ayrılır.
OUTPUT_RESERVE_TOKENS = 8_192
# Ölçüldü (29 Ekim, A1-04): yalnız yerleşik 48 aracın şeması 17.221 karakter, sistem
# istemleri (`prompts/`) ~10 bin karakter; ~27 bin karakter ≈ 9 bin token eder. Eski
# 4.000 değeri bunun yarısından azdı ve MCP/eklenti araçları ayrıca eklenir. 10.000
# yerleşik payı karşılar; küçük pencerede `smallest // 2` sınırı yine geçerlidir.
SYSTEM_AND_TOOLS_RESERVE_TOKENS = 10_000
CHARS_PER_TOKEN_ESTIMATE = 3
HISTORY_SHARE = 0.5
#: Öğrenilen eşiğin altına inilmeyecek taban (karakter).
LEARNED_FLOOR_CHARS = 4_000

#: Sağlayıcının "bağlam penceresi aşıldı" dediği hata işaretleri.
_OVERFLOW_MARKERS = (
    "context length",
    "context_length_exceeded",
    "contextwindowexceeded",
    "maximum context",
    "context window",
    "prompt is too long",
    "too many tokens",
    "exceeds the context",
)
#: Hata metninde bildirilen pencere: "maximum context length is 8192 tokens".
_STATED_WINDOW = re.compile(
    r"(?:maximum context length|context (?:length|window)|max(?:imum)? (?:input )?tokens?)"
    r"[^0-9]{0,40}(\d[\d,_]*)",
    re.IGNORECASE,
)


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


def is_context_overflow(error: str | None) -> bool:
    """Sağlayıcı hatası "istem modelin bağlam penceresine sığmadı" mı diyor?"""
    lowered = (error or "").lower()
    return any(marker in lowered for marker in _OVERFLOW_MARKERS)


def chars_for_window(window_tokens: int) -> int:
    """Pencere büyüklüğünden geçmişe ayrılabilecek karakter (`context_budget` ile aynı formül)."""
    smallest = max(1, window_tokens)
    reserved = min(OUTPUT_RESERVE_TOKENS + SYSTEM_AND_TOOLS_RESERVE_TOKENS, smallest // 2)
    return max(1, round((smallest - reserved) * HISTORY_SHARE * CHARS_PER_TOKEN_ESTIMATE))


def learned_threshold_chars(error: str | None, history_chars: int) -> int:
    """Bağlam taşması hatasından yeni (daha küçük) sıkıştırma eşiğini öğren.

    Pencere bilinmeyen model (yerel Ollama/LM Studio, yeni ücretsiz modeller) 177 bin
    karakterlik varsayılanla 400 verir ve sıkıştırma hiç tetiklenmezdi (A1-04). Hata
    metni pencereyi söylüyorsa ondan, söylemiyorsa o anki geçmişin yarısından türetilir;
    sonuç her zaman o anki geçmişten KÜÇÜKTÜR, yoksa sıkıştırma yine tetiklenmezdi.
    """
    ceiling = max(LEARNED_FLOOR_CHARS, history_chars * 3 // 4)
    match = _STATED_WINDOW.search(error or "")
    if match is not None:
        try:
            stated = int(re.sub(r"[,_]", "", match.group(1)))
        except ValueError:
            stated = 0
        if stated >= 1_024:
            return max(LEARNED_FLOOR_CHARS, min(chars_for_window(stated), ceiling))
    return max(LEARNED_FLOOR_CHARS, history_chars // 2)
