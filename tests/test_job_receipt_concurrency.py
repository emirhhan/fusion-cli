"""Tamamlanma kanıtının ilk sahibi transaction bitene kadar korunur."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from fusion_cli.tools import job_delivery


def test_receipt_writer_contention_is_explicit_and_first_receipt_immutable(tmp_path, monkeypatch):
    job_delivery.save_delivery(tmp_path, "12345678", "echo ok", None, ())
    entered, release = threading.Event(), threading.Event()
    snapshot = job_delivery.snapshot_delivery

    def blocked(*args):
        if args[-1] == 0:
            entered.set()
            assert release.wait(3)
        return snapshot(*args)

    monkeypatch.setattr(job_delivery, "snapshot_delivery", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(job_delivery.save_completion, tmp_path, tmp_path, "12345678", 0)
        try:
            assert entered.wait(3)
            with pytest.raises(ValueError, match="eşzamanlı"):
                job_delivery.save_completion(tmp_path, tmp_path, "12345678", 9)
        finally:
            release.set()
            first.result(timeout=3)
    original = (tmp_path / "12345678.receipt.json").read_bytes()
    job_delivery.save_completion(tmp_path, tmp_path, "12345678", 9)
    assert (tmp_path / "12345678.receipt.json").read_bytes() == original
