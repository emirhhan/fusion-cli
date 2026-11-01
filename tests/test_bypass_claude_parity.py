"""Bypass kipinde de sorulanlar (#42): açık ask kuralı ve kritik yol rm/rmdir silmeleri.

Kaynak: https://code.claude.com/docs/en/permission-modes#actions-no-mode-auto-approves
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fusion_cli.engines.agent.approval import (
    ApprovalMode,
    ApprovalRequest,
    Decision,
    build_policy,
    build_request,
)
from fusion_cli.tools.critical_paths import SKIP_CRITICAL_PROMPT_ENV, critical_rm_reason


class _Soran:
    def __init__(self) -> None:
        self.sorulan: list[ApprovalRequest] = []

    async def confirm(self, request: ApprovalRequest) -> bool:
        self.sorulan.append(request)
        return False


class _Arac:
    name = "run_shell"
    effect = None
    effect_resolver = None
    scope_resolver = None
    mutating = True


@pytest.fixture
def ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.delenv(SKIP_CRITICAL_PROMPT_ENV, raising=False)
    return ev


@pytest.mark.parametrize(
    ("komut", "kritik"),
    [
        ("rm -rf /", True),
        ("rm -rf /usr", True),
        ("rm -rf ~", True),
        ("rm -rf .", True),
        ("rm -rf ..", True),
        ("sudo rm -rf /etc", True),
        ('rm -rf "$DIR"/*', True),
        ('rm -rf "$(pwd)"', True),
        ("rmdir /data", True),
        ("rm -rf build", False),
        ("rm -rf /tmp/proje/x", False),
        ("ls /", False),
    ],
)
def test_kritik_yol_tespiti(tmp_path, ev, komut, kritik):
    kok = tmp_path / "proje"
    kok.mkdir()
    assert (critical_rm_reason(komut, kok, home=ev) is not None) is kritik


def test_ek_dizin_yalniz_glob_silmede_kritik(tmp_path, ev):
    kok, ek = tmp_path / "proje", tmp_path / "ek"
    assert critical_rm_reason(f"rm -rf {ek}/*", kok, (ek,), home=ev) is not None
    assert critical_rm_reason(f"rm -rf {ek}", kok, (ek,), home=ev) is None


def _istek(komut: str, kok: Path, **degisim) -> ApprovalRequest:
    from dataclasses import replace

    from fusion_cli.core.tools import ToolEffect

    arac = _Arac()
    arac.effect = ToolEffect.LOCAL
    istek = build_request(arac, {"command": komut}, root=kok)  # type: ignore[arg-type]
    return replace(istek, **degisim)


def test_bypass_kritik_silmeyi_ve_ask_kuralini_sorar(tmp_path, ev):
    kok = tmp_path / "proje"
    kok.mkdir()
    soran = _Soran()
    politika = build_policy(ApprovalMode.BYPASS, soran)
    assert asyncio.run(politika.decide(_istek("rm -rf ~", kok))) is not Decision.ALLOW
    sorulan = _istek("git push", kok, pre_ask="ask kuralı", rule="Bash(git push *)")
    assert asyncio.run(politika.decide(sorulan)) is not Decision.ALLOW
    assert len(soran.sorulan) == 2
    assert asyncio.run(politika.decide(_istek("rm -rf build", kok))) is Decision.ALLOW


def test_bypass_kritik_istemi_ortam_degiskeniyle_kapanir(tmp_path, ev, monkeypatch):
    kok = tmp_path / "proje"
    kok.mkdir()
    monkeypatch.setenv(SKIP_CRITICAL_PROMPT_ENV, "1")
    politika = build_policy(ApprovalMode.BYPASS, _Soran())
    assert asyncio.run(politika.decide(_istek("rm -rf ~", kok))) is Decision.ALLOW


def test_kritik_silme_allow_kuraliyla_acilmaz(tmp_path, ev):
    kok = tmp_path / "proje"
    kok.mkdir()
    istek = _istek("rm -rf ~", kok, pre_allowed=True)
    assert istek.danger is not None
    politika = build_policy(ApprovalMode.ACCEPT_EDITS, _Soran())
    assert asyncio.run(politika.decide(istek)) is not Decision.ALLOW


@pytest.mark.parametrize(
    ("komut", "kritik"),
    [
        ("rm -rf /Volumes/USB", True),
        ("rm -rf /Volumes/USB/*", True),
        ("rm -rf /mnt/disk", True),
        ("rm -rf /media/ali/USB", True),
        ("rm -rf /run/media/ali/USB/", True),
        ("rm -rf 'C:\\'", True),
        ("rm -rf /Volumes/USB/proje/build", False),
        ("rm -rf /mnt/disk/tmp/x", False),
    ],
)
def test_bagli_surucu_koku_kritik(tmp_path, ev, komut, kritik):
    kok = tmp_path / "kok"
    kok.mkdir()
    assert (critical_rm_reason(komut, kok, home=ev) is not None) is kritik
