"""Tekrar kullanılan tablolar.

CLI ve REPL aynı bilgiyi aynı biçimde göstermelidir; tablo kurulumu tek yerdedir.
"""

from __future__ import annotations

from rich.table import Table

from ..core.types import TokenUsage
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
    """Tablonun altına yazılacak tek satırlık özet.

    Ölçüldü (30 Ekim): web sağlayıcıda kullanım hiç ölçülmediği için "0 token · $0.0000"
    yazılıyordu; ölçülmemiş sıfır gerçek sıfır gibi görünüyordu. Ölçülmeyen alan "bilinmiyor"
    der; kısmen ölçülmüşse sayı "en az" olarak verilir.
    """
    total = tracker.total
    if tracker.calls == 0:
        tokens = messages.COST_TOKENS.format(tokens=f"{total.total_tokens:,}")
        cost = messages.COST_AMOUNT.format(cost=total.cost_usd)
    else:
        tokens = _tokens_text(total)
        cost = _cost_text(total)
    line = messages.COST_TOTAL.format(calls=tracker.calls, tokens=tokens, cost=cost)
    if tracker.abandoned_calls:
        line += messages.COST_TOTAL_UNCERTAIN.format(unknown=tracker.abandoned_calls)
    return line


def _tokens_text(total: TokenUsage) -> str:
    sayi = messages.COST_TOKENS.format(tokens=f"{total.total_tokens:,}")
    if total.completeness == "complete":
        return sayi
    return (
        messages.COST_AT_LEAST.format(value=sayi)
        if total.total_tokens
        else messages.COST_TOKENS_UNKNOWN
    )


def _cost_text(total: TokenUsage) -> str:
    tutar = messages.COST_AMOUNT.format(cost=total.cost_usd)
    if total.cost_known:
        return tutar
    return messages.COST_AT_LEAST.format(value=tutar) if total.cost_usd else messages.COST_UNKNOWN
