"""Claude Code `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` (#368).

Claude Code (env-vars): `1` iken Anthropic ve bulut sağlayıcı kimlik bilgileri alt süreç
ortamından (Bash aracı, kancalar, MCP stdio sunucuları) çıkarılır; ana süreç API çağrıları için
onları tutar, alt süreç okuyamaz. Fusion bunun karşılığında kendi sağlayıcı anahtarlarını da
(OpenRouter, NIM, OpenAI, Gemini) çıkarır. Yalnız stdlib (core katmanı).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

__all__ = ["SCRUBBED_NAMES", "SCRUB_ENV", "scrub_enabled", "scrubbed_env"]

SCRUB_ENV = "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"
#: Çıkarılan adlar: Claude'un Anthropic/bulut kimlik bilgileri + Fusion sağlayıcı anahtarları
#: (`config.keys` adları; core oradan içe aktaramaz, test iki listeyi eşler).
SCRUBBED_NAMES: frozenset[str] = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AZURE_API_KEY",
        "ANTHROPIC_FOUNDRY_API_KEY",
        "OPENROUTER_API_KEY",
        "NVIDIA_NIM_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
    }
)
_TRUE = frozenset({"1", "true", "yes", "on"})


def scrub_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """`CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` açık mı?"""
    source = os.environ if environ is None else environ
    return source.get(SCRUB_ENV, "").strip().lower() in _TRUE


def scrubbed_env(
    base: Mapping[str, str], environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Ayar açıksa kimlik bilgisi adları çıkarılmış yeni sözlük; kapalıysa kopya."""
    if not scrub_enabled(environ):
        return dict(base)
    return {name: value for name, value in base.items() if name not in SCRUBBED_NAMES}
