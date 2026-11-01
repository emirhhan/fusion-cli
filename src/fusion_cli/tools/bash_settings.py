"""Claude Code'un Bash aracı ayarları: zaman aşımı, çıktı sınırı, arka plan anahtarı.

Claude Code (tools-reference, env-vars):
- `timeout` (ms) her çağrıda verilebilir; varsayılan `BASH_DEFAULT_TIMEOUT_MS` (2 dk), tavan
  `BASH_MAX_TIMEOUT_MS` (10 dk) (#332).
- Satır içi çıktı ~30.000 karakter; `BASH_MAX_OUTPUT_LENGTH` ile değişir (#357).
- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` arka plan komutlarını kapatır (#358).
- Parametre adları `run_in_background` ve `dangerouslyDisableSandbox`; Fusion'ın eski
  `background` / `unsandboxed` adları takma ad olarak okunur (#351, #356).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from ..core.tools import ToolArgs

DEFAULT_TIMEOUT_MS = 120_000
MAX_TIMEOUT_MS = 600_000
#: Claude'daki satır içi Bash çıktısı sınırı (karakter).
DEFAULT_OUTPUT_CHARS = 30_000
BACKGROUND_ARG = "run_in_background"
LEGACY_BACKGROUND_ARG = "background"
DISABLE_SANDBOX_ARG = "dangerouslyDisableSandbox"


def _positive_int(env: Mapping[str, str], name: str, fallback: int) -> int:
    raw = env.get(name, "").strip()
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return value if value > 0 else fallback


def timeout_seconds(args: ToolArgs, env: Mapping[str, str] | None = None) -> float:
    """Çağrının zaman aşımı (sn): `timeout` (ms) ya da varsayılan; tavanı aşamaz."""
    source = os.environ if env is None else env
    default = _positive_int(source, "BASH_DEFAULT_TIMEOUT_MS", DEFAULT_TIMEOUT_MS)
    ceiling = max(default, _positive_int(source, "BASH_MAX_TIMEOUT_MS", MAX_TIMEOUT_MS))
    requested = args.get("timeout")
    if isinstance(requested, bool) or not isinstance(requested, (int, float)) or requested <= 0:
        requested = default
    return min(float(requested), float(ceiling)) / 1000.0


def output_limit(env: Mapping[str, str] | None = None) -> int:
    """Kabuk çıktısının satır içi sınırı (`BASH_MAX_OUTPUT_LENGTH`)."""
    source = os.environ if env is None else env
    return _positive_int(source, "BASH_MAX_OUTPUT_LENGTH", DEFAULT_OUTPUT_CHARS)


def background_disabled(env: Mapping[str, str] | None = None) -> bool:
    """`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` mi?"""
    source = os.environ if env is None else env
    return source.get("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def wants_background(args: ToolArgs, env: Mapping[str, str] | None = None) -> bool:
    """Çağrı arka planda mı çalışacak? Eski `background` adı da okunur."""
    asked = args.get(BACKGROUND_ARG) is True or args.get(LEGACY_BACKGROUND_ARG) is True
    return asked and not background_disabled(env)
