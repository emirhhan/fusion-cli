"""`fusion -p` koşu ortamı: yapılandırma, onay davranışı ve sinyaller.

Claude'da `-p` hiçbir zaman terminalde onay sormaz (#292): onay gereken çağrı bir allow
kuralı ya da kip onaylamadıkça reddedilir ve `permission_denials` listesine düşer. Bu yüzden
`ConsolePrompter` yerine `PrintPrompter` kullanılır: her isteği "sorulamadı" sayar (tur
sürer, model başka yol dener). `--bare` (#300) kancaları, belleği, MCP'yi, proje talimatını
kapatır ve araç kümesini Bash + dosya okuma/düzenleme ile sınırlar.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any

from ..config.models import Config
from ..engines.agent.approval import ApprovalAnswer, ApprovalRequest
from ..engines.agent.child_runs import ChildRuns
from ..engines.agent.engine_tools import QuestionOption
from ..ui import messages
from ..ui import print_messages as texts

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
    if bare:
        runtime = replace(runtime, project_instructions=False, hooks_enabled=False)
        config = replace(config, mcp_servers=(), hosted_connectors=())
    return replace(config, runtime=runtime)


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


#: Arka plan işi beklenirken stderr bildirimi bu kadar sonra yazılır (Claude: 5 sn).
BG_NOTICE_DELAY_S = 5.0
#: Arka plan işi bekleme tavanı (ms); Claude ile aynı ortam değişkeni ve varsayılan (10 dk).
BG_WAIT_CEILING_ENV = "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"
BG_WAIT_CEILING_DEFAULT_MS = 600_000


def bg_wait_ceiling_s() -> float:
    raw = os.environ.get(BG_WAIT_CEILING_ENV, "").strip()
    try:
        value = int(raw) if raw else BG_WAIT_CEILING_DEFAULT_MS
    except ValueError:
        value = BG_WAIT_CEILING_DEFAULT_MS
    return max(0, value) / 1000


async def wait_background(
    child_runs: ChildRuns, notify: Callable[[str], None], *, delay_s: float = BG_NOTICE_DELAY_S
) -> None:
    """Tur bitince başlatılmış arka plan alt ajanlarını tavana kadar bekle (#316)."""
    if not child_runs.active_count:
        return
    drain = asyncio.ensure_future(child_runs.drain())
    ceiling = bg_wait_ceiling_s()
    done, _ = await asyncio.wait({drain}, timeout=min(delay_s, ceiling))
    if not done:
        notify(texts.PRINT_WAITING_BACKGROUND)
        await asyncio.wait({drain}, timeout=max(0.0, ceiling - delay_s))
    if not drain.done():
        drain.cancel()
        await child_runs.close()
        return
    if not drain.cancelled() and drain.exception() is not None:
        notify(str(drain.exception()))


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
