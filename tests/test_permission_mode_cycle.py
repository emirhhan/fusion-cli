"""Shift+Tab döngüsü ve kip komutları Claude Code ile birebir (#51, #73, #74, #85).

Kaynak: https://code.claude.com/docs/en/permission-modes#switch-permission-modes
"""

from __future__ import annotations

from fusion_cli.cli.repl import mode_commands
from fusion_cli.engines.agent.approval import ApprovalMode, next_mode

D, E, P, B, A = (
    ApprovalMode.SECURITY,
    ApprovalMode.ACCEPT_EDITS,
    ApprovalMode.PLAN,
    ApprovalMode.BYPASS,
    ApprovalMode.AUTO,
)


def _tur(baslangic, **kw):
    sira, kip = [], baslangic
    for _ in range(6):
        kip = next_mode(kip, **kw)
        sira.append(kip)
    return sira


def test_varsayilan_dongu_auto_default_acceptedits_plan():
    assert _tur(A)[:4] == [D, E, P, A]


def test_bypass_etkin_oturumda_plandan_sonra_bypass_sonra_auto():
    assert _tur(A, bypass_available=True)[:5] == [D, E, P, B, A]


def test_auto_kapaliyken_donguden_cikar():
    assert A not in _tur(D, auto_available=False)
    assert _tur(B, bypass_available=True, auto_available=False)[:4] == [D, E, P, B]


def test_dontask_donguye_girmez():
    assert ApprovalMode.DONT_ASK not in _tur(A, bypass_available=True)


class _Durum:
    def __init__(self, bypass: bool = False) -> None:
        self.approval = A
        self.bypass_available = bypass
        self.auto_available = True


def test_bypass_komutu_bypass_siz_oturumda_gecmez(monkeypatch):
    monkeypatch.setattr(mode_commands, "_warned", set())
    durum = _Durum()
    cevap = mode_commands.legacy_mode("bypass", B)(durum, "")
    assert durum.approval is A and "kullanılamıyor" in cevap
    durum = _Durum(bypass=True)
    mode_commands.legacy_mode("bypass", B)(durum, "")
    assert durum.approval is B


def test_eski_kip_komutu_bir_kez_uyarir(monkeypatch):
    monkeypatch.setattr(mode_commands, "_warned", set())
    durum = _Durum()
    ilk = mode_commands.legacy_mode("edits", E)(durum, "")
    ikinci = mode_commands.legacy_mode("edits", E)(durum, "")
    assert durum.approval is E
    assert "Shift+Tab" in ilk and "Shift+Tab" not in ikinci
