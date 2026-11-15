"""İlerleme ikili değil PUANLIDIR.

SWE-TRACE'in bulgusu: kötü dalı sonradan elemek yerine koşarken budamak daha
etkili; ama budama kararı ölçülebilir olmalı. Fusion'da karar ikiliydi ("bir şey
değişti mi"), bu yüzden hem gürültülü hem ayarlanamazdı: başarısız üç çağrı ile
hiç çağrı yapmamak aynı sayılıyordu.

Puan turun KENDİ sinyallerinden gelir; model yorumu değildir.
"""

from __future__ import annotations

from fusion_cli.core.progress import PROGRESS_THRESHOLD, RoundSignals, score_round


def test_basarili_degisiklik_tam_puan_alir():
    puan = score_round(RoundSignals(mutations=1, new_reads=0, failures=0, repeats=0))

    assert puan >= PROGRESS_THRESHOLD


def test_yeni_okuma_ilerleme_sayilir():
    """Keşif turu ilerlemedir.

    Ölçüldü (kilitlenme ağı): tek okumayı yarım saymak, "listele → oku → düzelt"
    akışındaki modeli düzeltmeye varmadan öldürdü.
    """
    puan = score_round(RoundSignals(mutations=0, new_reads=1, failures=0, repeats=0))

    assert puan >= PROGRESS_THRESHOLD


def test_degisiklik_okumadan_daha_guclu_sinyal():
    okuma = score_round(RoundSignals(new_reads=1))
    degisiklik = score_round(RoundSignals(mutations=1))

    assert degisiklik > okuma


def test_basarisiz_cagrilar_salt_okuma_turunda_puani_dusurur():
    temiz = score_round(RoundSignals(new_reads=2))
    hatali = score_round(RoundSignals(new_reads=2, failures=2))

    assert hatali < temiz


def test_hata_iceren_turda_gercek_yeni_okuma_yine_ilerlemedir():
    """Ölçüldü (28 Eylül): okuma + başarısız `list_dir` turu ilerleme sayılmıyordu
    ve büyük görev keşfin ortasında cevapsız kesildi."""
    assert score_round(RoundSignals(new_reads=1, failures=1)) >= PROGRESS_THRESHOLD
    assert score_round(RoundSignals(new_reads=1, failures=3)) >= PROGRESS_THRESHOLD


def test_yalniz_tekrar_ve_hata_ureten_tur_ilerleme_degildir():
    assert score_round(RoundSignals(new_reads=1, repeats=1, failures=1)) < PROGRESS_THRESHOLD
    assert score_round(RoundSignals(failures=2)) < PROGRESS_THRESHOLD


def test_gerceklesen_degisiklik_ceza_ile_silinmez():
    """Dosya değiştiyse tur ilerlemiştir; arada başarısız çağrı olması bunu geri almaz.

    Ölçüldü (kilitlenme ağı): ceza değişikliğin üstüne binince, gerçekten yazan ama
    arada bir çağrıyı tekrarlayan tur "ilerleme yok" sayılıp kesildi.
    """
    puan = score_round(RoundSignals(mutations=1, failures=2, repeats=2))

    assert puan >= PROGRESS_THRESHOLD


def test_tekrarlanan_cagri_ilerleme_sayilmaz():
    puan = score_round(RoundSignals(mutations=0, new_reads=0, failures=0, repeats=2))

    assert puan <= 0


def test_bos_tur_sifir_puan():
    assert score_round(RoundSignals()) == 0.0


def test_puan_sinirlar_icinde_kalir():
    yuksek = score_round(RoundSignals(mutations=9, new_reads=9))
    dusuk = score_round(RoundSignals(failures=9, repeats=9))

    assert 0.0 <= yuksek <= 1.0
    assert 0.0 <= dusuk <= 1.0


def _fingerprint(output):
    from fusion_cli.core.evidence import ToolUse
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.progress import progress_fingerprint
    from fusion_cli.engines.agent.step_verification import StepVerificationResult
    from tests.test_gate_cache import _adim

    outcome = AgentOutcome("", [], tool_uses=(ToolUse("run_shell", False, output=output),))
    return progress_fingerprint(_adim("check"), outcome, StepVerificationResult(False))


def test_numeric_assertion_change_is_new_progress():
    assert _fingerprint("AssertionError: expected 2 got 1") != _fingerprint(
        "AssertionError: expected 3 got 1"
    )


def test_timestamp_and_explicit_pid_change_is_not_new_progress():
    assert _fingerprint("2026-10-31 12:20:00 PID=123 expected 2") == _fingerprint(
        "2026-10-31 12:30:00 PID=456 expected 2"
    )


def test_typed_failure_source_change_and_new_criterion_change_progress():
    from dataclasses import replace

    from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
    from fusion_cli.core.execution_plan import VerificationCheckKind
    from fusion_cli.core.repair_ledger import FailureEvidence, SourceFingerprint
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.progress import progress_fingerprint
    from fusion_cli.engines.agent.step_verification import StepVerificationResult
    from tests.test_gate_cache import _adim

    step, outcome = _adim("check"), AgentOutcome("", [])
    failure = FailureEvidence(
        "test/layout", "AssertionError", "attempt-1", (SourceFingerprint("a.py", "hash-one"),)
    )
    original = StepVerificationResult(False, failure_evidence=(failure,))
    changed = replace(
        failure, attempt_id="attempt-2", sources=(SourceFingerprint("a.py", "hash-two"),)
    )
    assert progress_fingerprint(step, outcome, original) != progress_fingerprint(
        step, outcome, replace(original, failure_evidence=(changed,))
    )
    same = replace(failure, attempt_id="attempt-3")
    assert progress_fingerprint(step, outcome, original) == progress_fingerprint(
        step, outcome, replace(original, failure_evidence=(same,))
    )
    criterion = CriterionEvidence(
        "behavior", VerificationCheckKind.COMMAND, EvidenceStatus.PASSED, "gerçek kontrol geçti"
    )
    assert progress_fingerprint(step, outcome, original) != progress_fingerprint(
        step, outcome, replace(original, criteria=(criterion,))
    )


def test_large_numeric_expectations_are_not_mistaken_for_hex_identity():
    assert _fingerprint("expected 12345678 got 1") != _fingerprint("expected 12345679 got 1")
