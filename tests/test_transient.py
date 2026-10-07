"""Geçici araç hatası tanıma (`transient`)."""

from __future__ import annotations

from fusion_cli.engines.agent.transient import is_transient_failure


def test_zaman_asimi_ve_ag_hatasi_gecicidir():
    """Ölçüldü (dalga24): clone_site 60 sn zaman aşımı; site sonra 0,5 sn'de açıldı."""
    assert is_transient_failure(
        "Araç çalışırken beklenmedik hata (clone_site): TimeoutError: Page.goto: "
        "Timeout 60000ms exceeded."
    )
    assert is_transient_failure("net::ERR_CONNECTION_RESET at https://x")


def test_kalici_hatalar_gecici_sayilmaz():
    assert not is_transient_failure("Dosya yok: src/app.py")
    assert not is_transient_failure("SyntaxError: Unexpected token '}'")
