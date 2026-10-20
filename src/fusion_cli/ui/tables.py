"""Tekrar kullanılan tablolar.

CLI ve REPL aynı bilgiyi aynı biçimde göstermelidir; tablo kurulumu tek yerdedir.
"""

from __future__ import annotations

from rich.table import Table

from ..observability.cost import CostTracker
from . import messages, theme


def cost_table(tracker: CostTracker) -> Table:
    """Rol bazında token ve maliyet tablosu."""
    table = Table(title=messages.COST_TITLE)
    table.add_column(messages.COST_TABLE_ROLE, style="bold")
    table.add_column(messages.COST_TABLE_CALLS, justify="right")
    table.add_column(messages.COST_TABLE_PROMPT, justify="right")
    table.add_column(messages.COST_TABLE_COMPLETION, justify="right")
    table.add_column(messages.COST_TABLE_COST, justify="right", style=theme.DIM)

    for role, calls, usage in tracker.by_role():
        table.add_row(
            role,
            str(calls),
            f"{usage.prompt_tokens:,}",
            f"{usage.completion_tokens:,}",
            f"${usage.cost_usd:.4f}",
        )
    return table


def cost_summary(tracker: CostTracker) -> str:
    """Tablonun altına yazılacak tek satırlık özet."""
    total = tracker.total
    return messages.COST_TOTAL.format(
        calls=tracker.calls, tokens=f"{total.total_tokens:,}", cost=total.cost_usd
    )
