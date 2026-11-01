"""`fusion -p` koşu ortamı: yapılandırma, onay davranışı ve sinyaller.

Claude'da `-p` hiçbir zaman terminalde onay sormaz (#292): onay gereken çağrı bir allow
kuralı ya da kip onaylamadıkça reddedilir ve `permission_denials` listesine düşer. Bu yüzden
`ConsolePrompter` yerine `PrintPrompter` kullanılır: her isteği "sorulamadı" sayar (tur
sürer, model başka yol dener). `--bare` (#300) kancaları, belleği, MCP'yi, proje talimatını
kapatır ve araç kümesini Bash + dosya okuma/düzenleme ile sınırlar.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from types import FrameType

from ..config.models import Config
from ..engines.agent.approval import ApprovalAnswer, ApprovalRequest
from ..engines.agent.engine_tools import QuestionOption
from ..ui import messages

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
