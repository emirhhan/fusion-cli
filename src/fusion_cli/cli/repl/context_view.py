"""`/context [all]` (#207): renkli ızgara, pencereye göre yüzde, öneriler, kapasite uyarısı.

Claude Code: bağlam kullanımı renkli bir ızgara olarak gösterilir; yüzde MODEL PENCERESİNE
göredir; araç çıktısı, bellek dosyası şişkinliği ve kapasite için öneriler verilir; pencere
aşılınca ne kadar aşıldığı ve hangi komutun yer açtığı yazılır. Kalem kırılımı her zaman
basılır (Claude Code'un tam ekran dışı görünümü); `all` en büyük kalemleri de listeler.
Token sayısı son API çağrısının ölçülen girdi token'ı varsa ondan, yoksa karakter/3
tahmininden gelir.
"""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape

from ...engines.agent.context_budget import CHARS_PER_TOKEN_ESTIMATE
from ...ui import messages, theme
from .state import ReplState
from .status_view import ContextReport, context_report, context_rows

GRID_CELLS = 100
GRID_COLUMNS = 20
#: Kategori → (etiket, renk). Sıra ızgaradaki sıradır.
_CATEGORIES = (
    ("system", messages.CONTEXT_SYSTEM, "bright_black"),
    ("schemas", messages.CONTEXT_TOOL_SCHEMAS, "magenta"),
    ("summary", messages.CONTEXT_SUMMARY, "cyan"),
    ("user", messages.CONTEXT_USER, "blue"),
    ("assistant", messages.CONTEXT_ASSISTANT, "green"),
    ("tools", messages.CONTEXT_TOOLS, "yellow"),
    ("pending", messages.CONTEXT_PENDING, "red"),
)
FILLED, FREE = "⛁", "⛶"
TOOL_HEAVY_SHARE = 40
CAPACITY_WARN_PERCENT = 80
MEMORY_HEAVY_CHARS = 40_000
TOP_ITEMS = 10


def _sizes(report: ContextReport) -> dict[str, int]:
    return {
        "system": report.system_chars,
        "schemas": report.tool_schema_chars,
        "summary": report.summary_chars,
        "user": report.user_chars,
        "assistant": report.assistant_chars,
        "tools": report.tool_chars,
        "pending": report.pending_chars,
    }


def window_chars_capacity(report: ContextReport) -> int:
    """Pencere karakter kapasitesi; pencere bilinmiyorsa sıkıştırma eşiği."""
    if report.window_tokens:
        return report.window_tokens * CHARS_PER_TOKEN_ESTIMATE
    return max(report.threshold_chars, 1)


def grid_lines(report: ContextReport) -> list[str]:
    """10×N hücrelik renkli ızgara (Rich biçim dizisi); her hücre pencerenin %1'i."""
    capacity = window_chars_capacity(report)
    cells: list[str] = []
    for key, _label, color in _CATEGORIES:
        count = round(_sizes(report)[key] * GRID_CELLS / capacity)
        cells.extend([f"[{color}]{FILLED}[/{color}]"] * count)
    cells = cells[:GRID_CELLS]
    cells.extend([f"[{theme.DIM}]{FREE}[/{theme.DIM}]"] * (GRID_CELLS - len(cells)))
    return [" ".join(cells[i : i + GRID_COLUMNS]) for i in range(0, GRID_CELLS, GRID_COLUMNS)]


def legend_lines(report: ContextReport, measured_tokens: int | None) -> list[str]:
    capacity = window_chars_capacity(report)
    lines = []
    for key, label, color in _CATEGORIES:
        chars = _sizes(report)[key]
        if chars == 0:
            continue
        share = chars * 100 / capacity
        tokens = chars // CHARS_PER_TOKEN_ESTIMATE
        lines.append(f"[{color}]{FILLED}[/{color}] {escape(label)}: ~{tokens:,} tok ({share:.1f}%)")
    used = report.window_chars // CHARS_PER_TOKEN_ESTIMATE
    if measured_tokens:
        used = measured_tokens
    window = report.window_tokens or report.threshold_chars // CHARS_PER_TOKEN_ESTIMATE
    free = max(0, window - used)
    lines.append(f"[{theme.DIM}]{FREE}[/{theme.DIM}] {messages.CONTEXT_FREE}: {free:,} tok")
    source = messages.CONTEXT_MEASURED if measured_tokens else messages.CONTEXT_ESTIMATED
    lines.insert(
        0,
        messages.CONTEXT_HEADLINE.format(
            used=f"{used:,}",
            window=f"{window:,}",
            percent=round(used * 100 / max(window, 1)),
            source=source,
        ),
    )
    return lines


def suggestions(report: ContextReport, used_tokens: int) -> list[str]:
    """Optimizasyon önerileri ve kapasite uyarıları."""
    tips: list[str] = []
    window = report.window_tokens or report.threshold_chars // CHARS_PER_TOKEN_ESTIMATE
    if window and used_tokens > window:
        tips.append(messages.CONTEXT_EXCEEDED.format(over=f"{used_tokens - window:,}"))
    elif window and used_tokens * 100 >= window * CAPACITY_WARN_PERCENT:
        tips.append(messages.CONTEXT_NEAR_CAPACITY.format(percent=used_tokens * 100 // window))
    if report.total_chars and report.tool_chars * 100 >= report.total_chars * TOOL_HEAVY_SHARE:
        tips.append(
            messages.CONTEXT_TOOL_HEAVY.format(share=report.tool_chars * 100 // report.total_chars)
        )
    if report.system_chars >= MEMORY_HEAVY_CHARS:
        tips.append(messages.CONTEXT_MEMORY_HEAVY)
    return tips


def top_items(state: ReplState) -> list[str]:
    """`all`: en büyük mesajlar (rol, boyut, ilk satır)."""
    rows = sorted(
        ((len(m.content), m.role, m.content) for m in state.history if m.content),
        key=lambda row: row[0],
        reverse=True,
    )[:TOP_ITEMS]
    lines = []
    for size, role, content in rows:
        first = content.strip().splitlines()[0][:70] if content.strip() else ""
        lines.append(f"~{size // CHARS_PER_TOKEN_ESTIMATE:,} tok · {role} · {escape(first)}")
    return lines


def _measured(state: ReplState) -> int | None:
    cost = getattr(state, "cost", None)
    value = getattr(cost, "last_prompt_tokens", 0) if cost is not None else 0
    return value if isinstance(value, int) and value > 0 else None


def render(state: ReplState, console: Console, argument: str = "") -> None:
    report = context_report(state)
    measured = _measured(state)
    used = measured or report.window_chars // CHARS_PER_TOKEN_ESTIMATE
    console.print()
    title = messages.CONTEXT_TITLE.format(model=report.model)
    console.print(f"[bold {theme.ACCENT}]{escape(title)}[/bold {theme.ACCENT}]", highlight=False)
    grid = grid_lines(report)
    legend = legend_lines(report, measured)
    for index in range(max(len(grid), len(legend))):
        left = grid[index] if index < len(grid) else ""
        right = legend[index] if index < len(legend) else ""
        console.print(f"  {left}   {right}", highlight=False)
    for tip in suggestions(report, used):
        console.print(f"  [{theme.WARN}]{escape(tip)}[/{theme.WARN}]", highlight=False)
    console.print()
    for label, value in context_rows(report):
        console.print(f"  [bold]{escape(label)}[/bold]  {escape(value)}", highlight=False)
    if argument.strip().lower() == "all":
        console.print(f"  [bold]{messages.CONTEXT_TOP_ITEMS}[/bold]", highlight=False)
        for line in top_items(state):
            console.print(f"    [{theme.DIM}]{line}[/{theme.DIM}]", highlight=False)
    if report.message_count == 0:
        console.print(f"[{theme.DIM}]{messages.CONTEXT_EMPTY}[/{theme.DIM}]", highlight=False)
    console.print()
