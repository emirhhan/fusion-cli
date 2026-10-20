"""Onarım kanıtı çağrı kimliğine veya sohbet belleğine indirgenmez."""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.repair_ledger import (
    FailureEvidence,
    FailureOrigin,
    RepairAction,
    RepairLedger,
    SourceFingerprint,
)


def evidence(attempt: str = "render-1") -> FailureEvidence:
    return FailureEvidence(
        check_id="layout",
        family="overflow",
        attempt_id=attempt,
        sources=(SourceFingerprint("src/Scene.tsx", "sha256:one"),),
    )


def test_same_attempt_poll_is_deduplicated_even_when_budget_exhausted() -> None:
    ledger = RepairLedger()
    ledger.observe(evidence(), remaining_repairs=1)
    result = ledger.observe(evidence(), remaining_repairs=0)
    assert result.action is RepairAction.ALREADY_OBSERVED
    assert ledger.snapshot().failures == (evidence(),)


def test_new_attempt_same_family_and_sources_requires_changed_approach() -> None:
    ledger = RepairLedger()
    ledger.observe(evidence(), remaining_repairs=2)
    result = ledger.observe(evidence("render-2"), remaining_repairs=1)
    assert result.action is RepairAction.CHANGE_APPROACH
    assert not result.has_source_change


def test_unrelated_edit_cannot_reset_repair_evidence() -> None:
    ledger = RepairLedger()
    ledger.observe(evidence(), remaining_repairs=2)
    # İlgili kaynak parmak izi aynı; başka dosya veya no-op yazma ilerleme değildir.
    assert (
        ledger.observe(evidence("render-3"), remaining_repairs=1).action
        is RepairAction.CHANGE_APPROACH
    )


def test_changed_source_same_failed_family_requires_root_cause_revision() -> None:
    ledger = RepairLedger()
    ledger.observe(evidence(), remaining_repairs=2)
    changed = replace(
        evidence("render-2"), sources=(SourceFingerprint("src/Scene.tsx", "sha256:two"),)
    )
    result = ledger.observe(changed, remaining_repairs=1)
    assert result.action is RepairAction.CHANGE_APPROACH
    assert result.has_source_change
    assert "kök nedeni" in result.note


def test_different_family_or_check_is_not_same_failure() -> None:
    ledger = RepairLedger()
    ledger.observe(evidence(), remaining_repairs=2)
    assert (
        ledger.observe(replace(evidence("2"), family="overlap"), remaining_repairs=1).action
        is RepairAction.REPAIR
    )
    assert (
        ledger.observe(replace(evidence("3"), check_id="other"), remaining_repairs=1).action
        is RepairAction.REPAIR
    )


def test_infrastructure_and_provider_failures_do_not_pollute_product_history() -> None:
    ledger = RepairLedger()
    for origin in (FailureOrigin.INFRASTRUCTURE, FailureOrigin.PROVIDER):
        assert (
            ledger.observe(replace(evidence(), origin=origin), remaining_repairs=0).action
            is RepairAction.EXCLUDED
        )
    assert ledger.snapshot().failures == ()


def test_existing_budget_is_authority_and_snapshot_survives_context_reset() -> None:
    ledger = RepairLedger()
    ledger.observe(evidence(), remaining_repairs=1)
    restored = RepairLedger(ledger.snapshot())
    assert restored.observe(evidence("2"), remaining_repairs=0).action is RepairAction.EXHAUSTED
    assert restored.snapshot().failures[-1].attempt_id == "2"


def test_unknown_sources_preserve_family_recurrence_without_source_claim() -> None:
    ledger = RepairLedger()
    ledger.observe(replace(evidence(), sources=()), remaining_repairs=2)
    result = ledger.observe(replace(evidence("2"), sources=()), remaining_repairs=1)
    assert result.action is RepairAction.CHANGE_APPROACH
    assert not result.has_source_change
    assert "kaynak aynı" not in result.note


def test_source_order_is_irrelevant_and_note_contains_no_source_content() -> None:
    ledger = RepairLedger()
    sources = (SourceFingerprint("b.tsx", "hash-b"), SourceFingerprint("a.tsx", "hash-a"))
    ledger.observe(replace(evidence(), sources=sources), remaining_repairs=2)
    result = ledger.observe(
        replace(evidence("2"), sources=tuple(reversed(sources))), remaining_repairs=1
    )
    assert result.action is RepairAction.CHANGE_APPROACH
    assert "layout" in result.note and "overflow" in result.note
    assert "hash-a" not in result.note


def test_padding_changes_do_not_erase_repeated_family() -> None:
    ledger = RepairLedger()
    assert ledger.observe(evidence(), remaining_repairs=3).action is RepairAction.REPAIR
    for attempt, digest in (("2", "padding-one"), ("3", "padding-two")):
        changed = replace(evidence(attempt), sources=(SourceFingerprint("src/Scene.tsx", digest),))
        decision = ledger.observe(changed, remaining_repairs=1)
        assert decision.action is RepairAction.CHANGE_APPROACH
        assert decision.has_source_change
        assert "aynı hata ailesi" in decision.note
    assert ledger.observe(evidence("4"), remaining_repairs=0).action is RepairAction.EXHAUSTED
