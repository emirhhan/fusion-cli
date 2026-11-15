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


def test_buraya_kadar_sonrasi_sonraki_turlar_dogru_siniri_kullanir(state):
    # Ölçüldü (1 Kasım): önceki özetten sonra eski checkpoint uzunlukları kayıyor, yanlış
    # aralık özetleniyordu (#199).
    rewind.rewind_command(state, "3 ozet-oncesi")
    rewind.rewind_command(state, "3 ozet-buradan")
    assert [m.content for m in state.history][:1] == ["ÖZET(4:)"]
    assert state.take_pending_input() == "üç"
    assert "üç yapıldı" not in [m.content for m in state.history]


def test_ozetlenmis_tura_ozetleme_reddedilir_gecmis_bozulmaz(state):
    rewind.rewind_command(state, "3 ozet-oncesi")
    once = list(state.history)
    sonuc = rewind.rewind_command(state, "2 ozet-buradan")
    assert state.history == once
    assert state.take_pending_input() == ""
    assert "özet" in sonuc.lower()


def test_compact_sonrasi_eski_tur_ozetlenmez(state):
    state.history = [Message("user", "COMPACT ÖZETİ")]
    sonuc = rewind.rewind_command(state, "2 ozet-oncesi")
    assert [m.content for m in state.history] == ["COMPACT ÖZETİ"]
    assert "özet" in sonuc.lower()


def test_her_turda_degisen_sistem_istemi_siniri_bozmaz(state):
    # Motor her turda sistem istemini yeniden kurar; ilk mesajın metni değişse de sınır geçerli.
    sistemli = [Message("system", "sistem v1"), *state.history]
    state.history = list(sistemli)
    state.checkpoints.begin("dört", state.history)
    state.history = [Message("system", "sistem v2"), *sistemli[1:]]
    state.history.extend([Message("user", "dört"), Message("assistant", "dört yapıldı")])
    rewind.rewind_command(state, "4 ozet-buradan")
    assert state.take_pending_input() == "dört"
    assert "dört yapıldı" not in [m.content for m in state.history]


class _SahteTui:
    def __init__(self, secimler, numarayla):
        self._secimler = iter(secimler)
        self._numarayla = numarayla
        self.picked_by_number = False
        self.metin_soruldu = False

    async def await_choice(self, title, choices, **_kw):
        self.picked_by_number = self._numarayla
        return next(self._secimler)

    async def await_text(self):
        self.metin_soruldu = True
        return "kısa tut"


async def _tui_argumani(state, tui):
    from types import SimpleNamespace

    from fusion_cli.cli.repl.tui_loop import _TuiSession

    sahte = SimpleNamespace(_state=state, _tui=tui, _echo=lambda _text: None)
    return await _TuiSession._resolve_rewind_argument(sahte, "")


async def test_tui_numara_tusuyla_ozet_talimatsiz_hemen(state):
    tui = _SahteTui(["2", "ozet-oncesi"], numarayla=True)
    assert await _tui_argumani(state, tui) == "2 ozet-oncesi"
    assert tui.metin_soruldu is False


async def test_tui_enter_ile_ozet_talimat_sorar(state):
    tui = _SahteTui(["2", "ozet-oncesi"], numarayla=False)
    assert await _tui_argumani(state, tui) == "2 ozet-oncesi kısa tut"
    assert tui.metin_soruldu is True
