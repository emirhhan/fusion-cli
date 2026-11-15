"""`/usage` ve `fusion usage` tabloları (P-056): pencereler, model ve atıf kırılımı.

CLI ve REPL aynı bilgiyi aynı biçimde göstermelidir; tablo kurulumu tek yerdedir
(`ui/tables.py` ile aynı ilke).
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from ..observability.usage_log import UsageBucket, UsageSummary
from . import messages, theme


def _cost_text(bucket: UsageBucket) -> str:
    if bucket.calls == 0:
        return messages.COST_AMOUNT.format(cost=0.0)
    text = messages.COST_AMOUNT.format(cost=bucket.usage.cost_usd)
    return text if bucket.cost_complete else messages.COST_AT_LEAST.format(value=text)


def windows_table(summary: UsageSummary) -> Table:
    table = Table(title=messages.USAGE_WINDOWS_TITLE)
    table.add_column(messages.USAGE_COL_WINDOW, style="bold")
    table.add_column(messages.COST_TABLE_CALLS, justify="right")
    table.add_column(messages.COST_TABLE_PROMPT, justify="right")
    table.add_column(messages.COST_TABLE_COMPLETION, justify="right")
    table.add_column(messages.COST_TABLE_COST, justify="right", style=theme.DIM)
    for label, bucket in summary.windows:
        table.add_row(
            label,
            str(bucket.calls),
            f"{bucket.usage.prompt_tokens:,}",
            f"{bucket.usage.completion_tokens:,}",
            _cost_text(bucket),
        )
    return table


def attribution_table(summary: UsageSummary) -> Table:
    table = Table(title=messages.USAGE_ATTRIBUTION_TITLE.format(window=summary.window_label))
    table.add_column(messages.USAGE_COL_SOURCE, style="bold")
    table.add_column(messages.COST_TABLE_CALLS, justify="right")
    table.add_column(messages.USAGE_COL_TOKENS, justify="right")
    table.add_column(messages.COST_TABLE_COST, justify="right", style=theme.DIM)
    for row in summary.by_actor:
        table.add_row(
            row.label,
            str(row.calls),
            f"{row.tokens:,}",
            messages.COST_AMOUNT.format(cost=row.cost_usd),
        )
    for row in summary.by_model:
        table.add_row(
            messages.USAGE_MODEL_ROW.format(model=row.label),
            str(row.calls),
            f"{row.tokens:,}",
            messages.COST_AMOUNT.format(cost=row.cost_usd),
        )
    for server, count in summary.mcp_calls:
        table.add_row(messages.USAGE_MCP_ROW.format(server=server), str(count), "-", "-")
    for skill, count in summary.skills:
        table.add_row(messages.USAGE_SKILL_ROW.format(skill=skill), str(count), "-", "-")
    return table


def print_usage(console: Console, summary: UsageSummary, *, log_path: str | None) -> None:
    """Pencere tablosu + atıf tablosu + günlük konumu."""
    console.print(windows_table(summary))
    if summary.by_actor or summary.mcp_calls or summary.skills:
        console.print(attribution_table(summary))
    if log_path is None:
        console.print(f"[{theme.DIM}]{messages.USAGE_LOG_DISABLED}[/{theme.DIM}]")
    elif summary.record_count == 0:
        console.print(f"[{theme.DIM}]{messages.USAGE_EMPTY}[/{theme.DIM}]")
    else:
        console.print(f"[{theme.DIM}]{messages.USAGE_LOG_PATH.format(path=log_path)}[/{theme.DIM}]")
