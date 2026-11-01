"""`/rewind` menüsünde Buradan itibaren / Buraya kadar özetle (#199)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl import rewind, rewind_summary
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture
def state(tmp_path: Path, monkeypatch) -> ReplState:
    root = tmp_path / "proje"
    root.mkdir()
    value = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=root,
        home=tmp_path / "ev",
    )
    for ad in ("bir", "iki", "üç"):
        value.checkpoints.begin(ad, value.history)
        value.history.extend([Message("user", ad), Message("assistant", f"{ad} yapıldı")])

    async def _sahte(_state, part, focus):
        from fusion_cli.engines.agent.history import root_anchor_length

        anchor = list(part[: root_anchor_length(part)])  # gerçek sıkıştırıcı gibi kök tur
        return [*anchor, Message("user", f"ÖZET({len(part)}:{focus})")]

    monkeypatch.setattr(rewind_summary, "_compress", _sahte)
    return value


def test_buradan_itibaren_sonrasini_ozetler_istemi_geri_koyar(state):
    sonuc = rewind.rewind_command(state, "2 ozet-buradan testlere odaklan")
    assert [m.content for m in state.history] == ["bir", "bir yapıldı", "ÖZET(4:testlere odaklan)"]
    assert state.take_pending_input() == "iki"
    assert "6 → 3" in sonuc


def test_buraya_kadar_oncesini_ozetler_sonrasi_kalir(state):
    rewind.rewind_command(state, "3 ozet-oncesi")
    assert [m.content for m in state.history] == ["ÖZET(4:)", "üç", "üç yapıldı"]
    assert state.take_pending_input() == ""


def test_secici_yolu_talimat_sorar(state, monkeypatch):
    secimler = iter(["2", "ozet-oncesi"])
    monkeypatch.setattr(rewind, "pick", lambda choices, title: next(secimler))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "kısa tut")
    rewind.rewind_command(state, "")
    assert [m.content for m in state.history][:2] == ["ÖZET(2:kısa tut)", "iki"]


def test_disable_compact_secenekleri_gizler(monkeypatch):
    monkeypatch.setenv("DISABLE_COMPACT", "1")
    assert rewind_summary.choices() == []
    assert "ozet-buradan" not in [c.value for c in rewind.scope_choices()]
