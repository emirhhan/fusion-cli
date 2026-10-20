"""Makbuzun Türkçe wire alanlarına dönüştürülmesi."""

from __future__ import annotations

from ..core.submission import SubmissionReceipt


def receipt_payload(receipt: SubmissionReceipt) -> dict[str, object]:
    """İçeriksiz kabul metadata'sını eski protokole ekler."""
    return {
        "gonderim_id": receipt.key.request_id,
        "oturum_id": receipt.key.conversation_id,
        "tur_id": receipt.attempt_id,
        "durum": receipt.state.value,
        "hata_kodu": receipt.error_code,
    }
