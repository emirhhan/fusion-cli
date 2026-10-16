"""Kullanım replay, eksik ölçüm ve gerçek sıfır sözleşmesi."""

from fusion_cli.core.types import TokenUsage
from fusion_cli.core.usage_ledger import UsageLedger


def test_duplicate_response_does_not_double_count_and_unknown_is_visible():
    ledger = UsageLedger()
    ledger.reserve(1)
    ledger.reserve(2)
    measured = TokenUsage(10, 5, prompt_measured=True, completion_measured=True)
    ledger.record(1, measured)
    ledger.record(1, measured)
    snapshot = ledger.snapshot()
    assert snapshot.prompt_tokens == 10
    assert snapshot.completion_tokens == 5
    assert snapshot.unknown_calls == 1
    assert snapshot.total_calls == 2
    assert not snapshot.cost_known


def test_measured_zero_is_complete_and_partial_counts_only_measured_part():
    ledger = UsageLedger()
    ledger.record(1, TokenUsage(prompt_measured=True, completion_measured=True, cost_known=True))
    assert ledger.snapshot().unknown_calls == 0
    ledger.record(2, TokenUsage(8, 20, prompt_measured=True))
    assert ledger.snapshot().prompt_tokens == 8
    assert ledger.snapshot().completion_tokens == 0
    assert ledger.snapshot().unknown_calls == 1
