"""`/status` ve `/context` — oturum durumu ve bağlam penceresi kırılımı (P-027).

Claude Code'un `/status` (sürüm, model, hesap, dizin, MCP, izin kipi, oturum) ve
`/context` (sistem istemi / mesajlar / araç sonuçları kırılımı) komutlarının
Fusion karşılığı. Hesaplama SAFTIR: `ReplState`'e bakar, model çağırmaz. Basma işi
`help_view` ile aynı biçimde (başlık aksan, satırlar hizalı, açıklama sönük) yapılır;
masaüstü aynı metni `render_command_text` üzerinden alır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from ...config.models import Config
from ...config.paths import active_account
from ...engines import agent as _agent_package
from ...engines.agent.context_budget import CHARS_PER_TOKEN_ESTIMATE, context_budget
from ...engines.agent.history import is_summary_message
from ...engines.agent.output_style import style_prompt
from ...engines.agent.project_instructions import read_project_instructions
from ...ui import messages, theme
from .state import ReplState

#: Temel sistem istemi dosyası (`engines/agent/loop.py::SYSTEM_PROMPT` aynı dosyayı okur;
#: ağır modülü içe aktarmadan boyutu buradan tahmin edilir).
_SYSTEM_PROMPT_PATH = Path(_agent_package.__file__).parent / "prompts" / "system.md"

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
    #: Modele giden araç şemalarının JSON boyutu (tahmini; geçmişte görünmez).
    tool_schema_chars: int = 0
    #: Geçmişte sistem mesajı yokken (yeni oturum) istem tahminle sayıldı mı?
    system_estimated: bool = False
    #: Bir sonraki tura girecek `!`/`@` blokları ve devralma künyesi.
    pending_chars: int = 0

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

    @property
    def window_chars(self) -> int:
        """Pencereye gerçekten giden toplam: geçmiş + araç şemaları + bekleyen bağlam."""
        return self.total_chars + self.tool_schema_chars + self.pending_chars

    @property
    def window_percent(self) -> int | None:
        """Model penceresine göre doluluk; pencere bilinmiyorsa None."""
        if not self.window_tokens:
            return None
        return min(
            100, round(self.window_chars * 100 / (self.window_tokens * CHARS_PER_TOKEN_ESTIMATE))
        )


@lru_cache(maxsize=1)
def _tool_schema_chars() -> int:
    """Yerleşik araç şemalarının JSON boyutu (oturumda değişmez; bir kez hesaplanır)."""
    from ...tools.builtin import build_registry

    try:
        return len(json.dumps(build_registry().schemas(), ensure_ascii=False))
    except Exception:  # şema üretimi çökse sayaç yine çalışır
        return 0


def _system_estimate(state: ReplState) -> int:
    """Yeni oturumda sistem isteminin boyutu: temel istem + proje talimatı + çıktı stili."""
    try:
        base = len(_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"))
    except OSError:
        base = 0
    try:
        project = len(read_project_instructions(state.root))
    except Exception:
        project = 0
    style = len(style_prompt(state.config, home=state.home, root=state.root))
    return base + project + style


def context_report(state: ReplState) -> ContextReport:
    """Geçmişi rol rol topla. Özet mesajı (`/compact` ürünü) ayrı sayılır.

    Ölçüldü (31 Ekim): yeni oturumda 'Sistem 0 tok' görünüyor, araç şemaları ve bekleyen
    `!`/`@` bağlamı hiç sayılmıyordu. Geçmişte sistem mesajı yoksa istem tahminle sayılır;
    araç şemaları ve bekleyen bağlam ayrı satırdır.
    """
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
    estimated = system == 0 and not any(message.role == "system" for message in state.history)
    if estimated:
        system = _system_estimate(state)
    pending = sum(len(block) for block in state.pending_blocks) + len(state.pending_digest or "")
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
        tool_schema_chars=_tool_schema_chars(),
        system_estimated=estimated,
        pending_chars=pending,
    )


def context_percent(state: ReplState) -> int:
    """Durum çubuğundaki sayaç için tek sayı: eşiğe göre doluluk yüzdesi."""
    return context_report(state).percent


def context_label(state: ReplState) -> str:
    """Durum çubuğu etiketi: `bağlam %12 · ~3k tok` (konuşma / sıkıştırma eşiği).

    Geçmiş boşsa boş metin: açılışta tahmini sistem istemiyle dolu bir sayaç göstermek
    yanıltır; `/context` tahmini satırlarıyla ayrıntıyı verir.
    """
    report = context_report(state)
    if report.message_count == 0:
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
        (messages.STATUS_OUTPUT_STYLE, _style_name(state)),
        (messages.STATUS_DIR, dirs),
        (messages.STATUS_MCP, mcp),
        (messages.STATUS_ACCOUNT, active_account()),
        # Claude Code `/status` (#225): oturum türü ve bağlantı satırları.
        (messages.STATUS_SESSION_KIND, getattr(state, "session_kind", "") or "interactive"),
        (messages.STATUS_CONNECTIVITY, _connectivity(config)),
        (messages.STATUS_CONVERSATION, state.conversation_id),
        (
            messages.STATUS_CONFIG_FILE,
            str(config.source) if config.source else messages.STATUS_NONE,
        ),
    ]
    if state.memory.enabled:
        rows.append((messages.STATUS_LESSONS, str(state.memory.lessons.count())))
    return rows


def _style_name(state: ReplState) -> str:
    from ...engines.agent.output_style import selected_style

    style = selected_style(state.config, home=state.home, root=state.root)
    return "default" if style is None else (style.display or style.name)


def _connectivity(config: Config) -> str:
    """Sağlayıcı kurulumunun hazırlık durumu (anahtar/oturum var mı); ağ çağrısı yapmaz."""
    from ...config.keys import detect
    from ...config.readiness import evaluate

    try:
        state = evaluate(config, detect()).state.value
    except Exception as error:  # hazırlık okunamazsa satır yine basılır
        return f"{messages.STATUS_CONNECTIVITY_UNKNOWN} ({type(error).__name__})"
    return messages.STATUS_CONNECTIVITY_VALUES.get(state, state)


def _tier_name(state: ReplState) -> str:
    """Etkin agent modeli hangi kademenin baş modeliyse onun adı; eşleşme yoksa boş."""
    for tier in state.config.tiers:
        if tier.agent.model == state.config.agent.model:
            return tier.name
    return ""


def context_rows(report: ContextReport) -> list[tuple[str, str]]:
    """`/context` tablo satırları: bölüm → karakter (~token, yüzde)."""
    rows: list[tuple[str, str]] = []
    system_label = (
        messages.CONTEXT_SYSTEM_ESTIMATED if report.system_estimated else messages.CONTEXT_SYSTEM
    )
    for label, chars in (
        (system_label, report.system_chars),
        (messages.CONTEXT_SUMMARY, report.summary_chars),
        (messages.CONTEXT_USER, report.user_chars),
        (messages.CONTEXT_ASSISTANT, report.assistant_chars),
        (messages.CONTEXT_TOOLS, report.tool_chars),
    ):
        if chars == 0 and label != system_label:
            continue
        share = round(chars * 100 / report.total_chars) if report.total_chars else 0
        rows.append((label, f"{_short_number(chars // CHARS_PER_TOKEN_ESTIMATE)} tok · %{share}"))
    # Geçmişte görünmeyen ama pencereye giden kalemler (Claude Code `/context` gibi ayrı).
    rows.append(
        (
            messages.CONTEXT_TOOL_SCHEMAS,
            f"{_short_number(report.tool_schema_chars // CHARS_PER_TOKEN_ESTIMATE)} tok",
        )
    )
    if report.pending_chars:
        rows.append(
            (
                messages.CONTEXT_PENDING,
                f"{_short_number(report.pending_chars // CHARS_PER_TOKEN_ESTIMATE)} tok",
            )
        )
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
        rows.append(
            (
                messages.CONTEXT_WINDOW,
                messages.CONTEXT_WINDOW_VALUE.format(
                    window=_short_number(report.window_tokens),
                    tokens=_short_number(report.window_chars // CHARS_PER_TOKEN_ESTIMATE),
                    percent=report.window_percent or 0,
                ),
            )
        )
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
    if report.message_count == 0:
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
