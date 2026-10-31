"""TUI: boş girdide Esc Esc `/rewind` açar; tek Esc ve dolu girdi eski davranışı korur (P-004)."""

from __future__ import annotations

import pytest

from fusion_cli.cli.repl.tui import DOUBLE_ESCAPE_SECONDS, FusionTui


@pytest.fixture
def tui():
    calls: list[str] = []
    tui = FusionTui(
        on_submit=lambda text: calls.append(f"submit:{text}"),
        on_interrupt=lambda: calls.append("interrupt"),
        on_exit=lambda: calls.append("exit"),
        on_cycle_mode=lambda: calls.append("cycle"),
        on_rewind=lambda: calls.append("rewind"),
    )
    return tui, calls


def test_cift_esc_bos_girdide_rewind_acar(tui):
    app, _calls = tui
    assert app._rewind_requested(now=10.0) is False
    assert app._rewind_requested(now=10.0 + DOUBLE_ESCAPE_SECONDS / 2) is True
    # Üçüncü Esc yeni bir dizi başlatır; iki Esc arası pencere aşılırsa açılmaz.
    assert app._rewind_requested(now=11.0) is False
    assert app._rewind_requested(now=11.0 + DOUBLE_ESCAPE_SECONDS * 2) is False


def test_dolu_girdide_esc_rewind_acmaz(tui):
    app, _calls = tui
    app._input.text = "yarım mesaj"
    assert app._rewind_requested(now=1.0) is False
    assert app._rewind_requested(now=1.1) is False


def test_cancel_or_interrupt_ikinci_escte_geri_sarmayi_cagirir(tui, monkeypatch):
    app, calls = tui
    zaman = iter([5.0, 5.2])
    monkeypatch.setattr("fusion_cli.cli.repl.tui.time.monotonic", lambda: next(zaman))

    app._cancel_or_interrupt()
    app._cancel_or_interrupt()

    assert calls == ["interrupt", "rewind"]


def test_on_rewind_verilmezse_esc_yalniz_keser():
    calls: list[str] = []
    app = FusionTui(
        on_submit=lambda text: None,
        on_interrupt=lambda: calls.append("interrupt"),
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )
    app._cancel_or_interrupt()
    app._cancel_or_interrupt()
    assert calls == ["interrupt", "interrupt"]
