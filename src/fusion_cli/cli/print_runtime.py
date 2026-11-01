"""`fusion -p` koşu ortamı: yapılandırma, onay davranışı ve sinyaller.

Claude'da `-p` hiçbir zaman terminalde onay sormaz (#292): onay gereken çağrı bir allow
kuralı ya da kip onaylamadıkça reddedilir ve `permission_denials` listesine düşer. Bu yüzden
`ConsolePrompter` yerine `PrintPrompter` kullanılır: her isteği "sorulamadı" sayar (tur
sürer, model başka yol dener). `--bare` (#300) kancaları, belleği, MCP'yi, proje talimatını
kapatır ve araç kümesini Bash + dosya okuma/düzenleme ile sınırlar.
"""

from __future__ import annotations

import logging
import os
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any

from ..config.models import Config
from ..engines.agent.approval import ApprovalAnswer, ApprovalRequest
from ..engines.agent.engine_tools import QuestionOption
from ..ui import messages

if TYPE_CHECKING:
    from ..tools.capabilities import CapabilityRegistry

#: `--bare` kipinde modele sunulan yerleşik araçlar (Claude: Bash, dosya okuma, düzenleme).
BARE_TOOLS = frozenset(
    {"run_shell", "read_file", "view_file", "edit_file", "multi_edit", "write_file"}
)
#: SIGTERM ile kesilen koşunun çıkış kodu (128 + 15; Claude ile aynı).
SIGTERM_EXIT_CODE = 143


class PrintPrompter:
    """Etkileşimsiz `-p` onay arayüzü: kimseye sormaz, isteği "sorulamadı" sayar."""

    def __init__(self) -> None:
        self.requests: list[ApprovalRequest] = []

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer:
        self.requests.append(request)
        return ApprovalAnswer.UNAVAILABLE

    async def ask(
        self,
        question: str,
        options: tuple[QuestionOption, ...] = (),
        recommended: str | None = None,
    ) -> str:
        return messages.NO_ANSWER_AVAILABLE


def apply_print_limits(
    config: Config, *, max_turns: int | None, max_budget_usd: float | None, bare: bool
) -> Config:
    """`--max-turns` (verilmezse sınırsız, #285), `--max-budget-usd`, `--bare` (#300)."""
    from .print_options import UNLIMITED_TURNS

    runtime = replace(
        config.runtime,
        agent_max_steps=max_turns if max_turns is not None else UNLIMITED_TURNS,
    )
    if max_budget_usd is not None:
        runtime = replace(runtime, agent_max_cost_usd=max_budget_usd)
    config = replace(config, runtime=runtime)
    return apply_bare(config) if bare else config


#: `--bare` ortam değişkeni (Claude: `--bare` bunu ayarlar).
BARE_ENV = "CLAUDE_CODE_SIMPLE"


def apply_bare(config: Config) -> Config:
    """`--bare` (#298): kanca, otomatik bellek, MCP/bağlayıcı ve proje talimatı kapalı.

    Claude'daki gibi modele beceri listesi verilmez (`skill_index_chars: 0`) ve arka plan
    alt ajanı başlatılamaz (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` karşılığı).
    """
    os.environ[BARE_ENV] = "1"
    runtime = replace(
        config.runtime,
        project_instructions=False,
        hooks_enabled=False,
        auto_memory=False,
        skill_index_chars=0,
    )
    launch = replace(config.agent_launch, disable_background_tasks=True)
    return replace(
        config, runtime=runtime, agent_launch=launch, mcp_servers=(), hosted_connectors=()
    )


#: `--safe-mode` ortam değişkeni (Claude ile aynı ad).
SAFE_MODE_ENV = "CLAUDE_CODE_SAFE_MODE"


def apply_safe_mode(config: Config) -> Config:
    """`--safe-mode`: proje talimatı, kancalar, MCP kapalı; yerleşik araçlar ve izinler aynen."""
    os.environ[SAFE_MODE_ENV] = "1"
    runtime = replace(config.runtime, project_instructions=False, hooks_enabled=False)
    return replace(config, runtime=runtime, mcp_servers=(), hosted_connectors=())


def apply_session_flags(config: Config, pairs: tuple[str, ...], tier: str | None) -> Config:
    """`--set`/`--profile` (Fusion ekleri) — bildirim basmadan; stdout makine çıktısıdır."""
    from ..config import model_select
    from ..config.settings_access import apply_overrides

    if pairs:
        config = apply_overrides(config, pairs)
    if tier:
        config = model_select.apply_tier(
            config, model_select.normalize_tier_name(tier.strip().lower())
        )
    return config


class TerminatedError(Exception):
    """SIGTERM alındı; koşu kapanış işlerini yapıp 143 ile çıkar (#307)."""


@contextmanager
def sigterm_as_exception() -> Iterator[None]:
    """SIGTERM'i istisnaya çevir: `finally` blokları (SessionEnd kancası) çalışsın."""

    def _handler(_signum: int, _frame: FrameType | None) -> None:
        raise TerminatedError

    try:
        previous = signal.signal(signal.SIGTERM, _handler)
    except ValueError:  # ana iş parçacığı değil (testler); sinyal kurulmaz
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def enable_debug_logging(categories: str | None, path: str | None) -> logging.Handler | None:
    """`--debug [kategoriler]` stderr'e, `--debug-file <yol>` dosyaya ayrıntılı günlük (#305).

    Kategori süzgeci (`"api,hooks"`, `"!statsig"`) Fusion günlükçü adlarına (`fusion_cli.*`)
    alt dize olarak uygulanır; `all` ya da boş hepsi demektir.
    """
    if categories is None and not path:
        return None
    handler: logging.Handler = (
        logging.FileHandler(path, encoding="utf-8") if path else logging.StreamHandler()
    )
    handler.setFormatter(logging.Formatter("[DEBUG] %(name)s: %(message)s"))
    wanted = [item.strip() for item in (categories or "").split(",") if item.strip()]
    if wanted and wanted != ["all"]:
        handler.addFilter(lambda record: _category_match(record.name, wanted))
    logger = logging.getLogger("fusion_cli")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return handler


def _category_match(name: str, wanted: list[str]) -> bool:
    excluded = [item[1:] for item in wanted if item.startswith("!")]
    included = [item for item in wanted if not item.startswith("!")]
    if any(item in name for item in excluded):
        return False
    return not included or any(item in name for item in included)


#: `--bare` kataloğunun kökü: hiçbir zaman var olmayan bir yol (keşif boş döner).
_BARE_ROOT = Path("/nonexistent/fusion-bare")


def bare_catalog(
    config: Config, extra_roots: tuple[Path, ...], session_agents: tuple[Any, ...] = ()
) -> CapabilityRegistry:
    """`--bare` (#298): kullanıcı/proje becerileri, komutları, ajanları ve eklentileri keşfedilmez.

    Claude'daki gibi yalnız `--add-dir` dizinlerinin becerileri yüklenir; yerleşik alt ajanlar
    ve ek ajan kaynakları da kapalıdır.
    """
    from ..tools.capability_overrides import registry_from_config

    launch = replace(
        config.agent_launch,
        disable_builtin_agents=True,
        extra_agent_sources=False,
        managed_agent_roots=(),
    )
    return registry_from_config(
        replace(config, agent_launch=launch),
        _BARE_ROOT,
        _BARE_ROOT,
        extra_roots=extra_roots,
        session_agents=session_agents,
        headless=True,
    )
