"""`/status` ve `/context` — oturum durumu ve bağlam penceresi kırılımı (P-027).

Claude Code'un `/status` (sürüm, model, hesap, dizin, MCP, izin kipi, oturum) ve
`/context` (sistem istemi / mesajlar / araç sonuçları kırılımı) komutlarının
Fusion karşılığı. Hesaplama SAFTIR: `ReplState`'e bakar, model çağırmaz. Basma işi
`help_view` ile aynı biçimde (başlık aksan, satırlar hizalı, açıklama sönük) yapılır;
masaüstü aynı metni `render_command_text` üzerinden alır.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.console import Console
from rich.markup import escape

from ...config.paths import active_account
from ...engines.agent.context_budget import CHARS_PER_TOKEN_ESTIMATE, context_budget
from ...engines.agent.history import is_summary_message
from ...ui import messages, theme
from .state import ReplState

#: Satır etiketlerinin hizalama genişliği.
_LABEL_WIDTH = 16


@dataclass(frozen=True, slots=True)
class ContextReport:
    """Bağlam penceresinin kırılımı (karakter cinsinden; token tahmini ayrıca)."""

    system_chars: int
    user_chars: int
    assistant_chars: int
    tool_chars: int
    summary_chars: int
    message_count: int
    #: Sıkıştırma eşiği (karakter). Yüzde buna göre hesaplanır.
    threshold_chars: int
    #: Doğrulanmış model penceresi (token); bilinmiyorsa None.
    window_tokens: int | None
    model: str

    @property
    def total_chars(self) -> int:
        return (
            self.system_chars
            + self.user_chars
            + self.assistant_chars
            + self.tool_chars
            + self.summary_chars
        )

    @property
    def percent(self) -> int:
        if self.threshold_chars <= 0:
            return 0
        return min(100, round(self.total_chars * 100 / self.threshold_chars))

    @property
    def estimated_tokens(self) -> int:
        return self.total_chars // CHARS_PER_TOKEN_ESTIMATE


def context_report(state: ReplState) -> ContextReport:
    """Geçmişi rol rol topla. Özet mesajı (`/compact` ürünü) ayrı sayılır."""
    system = user = assistant = tool = summary = 0
    for message in state.history:
        size = len(message.content)
        if is_summary_message(message):
            summary += size
        elif message.role == "system":
            system += size
        elif message.role == "user":
            user += size
        elif message.role == "assistant":
            assistant += size
        elif message.role == "tool":
            tool += size
    budget = context_budget(state.config, state.config.agent)
    return ContextReport(
        system_chars=system,
        user_chars=user,
        assistant_chars=assistant,
        tool_chars=tool,
        summary_chars=summary,
        message_count=len(state.history),
        threshold_chars=budget.compression_chars,
        window_tokens=budget.window_tokens,
        model=budget.model,
    )


def context_percent(state: ReplState) -> int:
    """Durum çubuğundaki sayaç için tek sayı: eşiğe göre doluluk yüzdesi."""
    return context_report(state).percent


def context_label(state: ReplState) -> str:
    """Durum çubuğu etiketi: `bağlam %12 · ~3k tok`. Geçmiş boşsa boş metin."""
    report = context_report(state)
    if report.total_chars == 0:
        return ""
    return messages.STATUS_CONTEXT_LABEL.format(
        percent=report.percent, tokens=_short_number(report.estimated_tokens)
    )


def status_rows(state: ReplState) -> list[tuple[str, str]]:
    """`/status` satırları: (etiket, değer). Sır yok; yollar olduğu gibi gösterilir."""
    from ... import __version__

    config = state.config
    tier = _tier_name(state)
    model = config.agent.model if not tier else f"{config.agent.model} · {tier}"
    dirs = str(state.root)
    if state.extra_roots:
        dirs += " + " + ", ".join(str(path) for path in state.extra_roots)
    mcp = ", ".join(server.name for server in config.mcp_servers) or messages.STATUS_NONE
    rows = [
        (messages.STATUS_VERSION, __version__),
        (messages.STATUS_ENGINE, state.engine.value),
        (messages.STATUS_APPROVAL, state.approval.value),
        (messages.STATUS_MODEL, model),
        (messages.STATUS_EFFORT, config.runtime.reasoning_effort.value),
        (messages.STATUS_OUTPUT_STYLE, getattr(config.runtime, "output_style", "varsayilan")),
        (messages.STATUS_DIR, dirs),
        (messages.STATUS_MCP, mcp),
        (messages.STATUS_ACCOUNT, active_account()),
        (messages.STATUS_CONVERSATION, state.conversation_id),
        (
            messages.STATUS_CONFIG_FILE,
            str(config.source) if config.source else messages.STATUS_NONE,
        ),
    ]
    if state.memory.enabled:
        rows.append((messages.STATUS_LESSONS, str(state.memory.lessons.count())))
    return rows


def _tier_name(state: ReplState) -> str:
    """Etkin agent modeli hangi kademenin baş modeliyse onun adı; eşleşme yoksa boş."""
    for tier in state.config.tiers:
        if tier.agent.model == state.config.agent.model:
            return tier.name
    return ""


def context_rows(report: ContextReport) -> list[tuple[str, str]]:
    """`/context` tablo satırları: bölüm → karakter (~token, yüzde)."""
    rows: list[tuple[str, str]] = []
    for label, chars in (
        (messages.CONTEXT_SYSTEM, report.system_chars),
        (messages.CONTEXT_SUMMARY, report.summary_chars),
        (messages.CONTEXT_USER, report.user_chars),
        (messages.CONTEXT_ASSISTANT, report.assistant_chars),
        (messages.CONTEXT_TOOLS, report.tool_chars),
    ):
        if chars == 0 and label != messages.CONTEXT_SYSTEM:
            continue
        share = round(chars * 100 / report.total_chars) if report.total_chars else 0
        rows.append((label, f"{_short_number(chars // CHARS_PER_TOKEN_ESTIMATE)} tok · %{share}"))
    rows.append(
        (
            messages.CONTEXT_TOTAL,
            messages.CONTEXT_TOTAL_VALUE.format(
                tokens=_short_number(report.estimated_tokens),
                limit=_short_number(report.threshold_chars // CHARS_PER_TOKEN_ESTIMATE),
                percent=report.percent,
                count=report.message_count,
            ),
        )
    )
    if report.window_tokens:
        rows.append((messages.CONTEXT_WINDOW, f"{_short_number(report.window_tokens)} tok"))
    return rows


def _short_number(value: int) -> str:
    """12 345 → `12k`; küçük sayılar olduğu gibi."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return str(value)


def render_status(state: ReplState, console: Console) -> None:
    _print_rows(console, messages.STATUS_TITLE, status_rows(state))


def render_context(state: ReplState, console: Console) -> None:
    report = context_report(state)
    _print_rows(console, messages.CONTEXT_TITLE.format(model=report.model), context_rows(report))
    if report.total_chars == 0:
        console.print(f"[{theme.DIM}]{messages.CONTEXT_EMPTY}[/{theme.DIM}]", highlight=False)


def _print_rows(console: Console, title: str, rows: list[tuple[str, str]]) -> None:
    console.print()
    console.print(f"[bold {theme.ACCENT}]{escape(title)}[/bold {theme.ACCENT}]", highlight=False)
    for label, value in rows:
        pad = " " * max(0, _LABEL_WIDTH - len(label))
        console.print(
            f"  [bold]{escape(label)}[/bold]{pad}  [{theme.DIM}]{escape(value)}[/{theme.DIM}]",
            highlight=False,
        )
    console.print()
