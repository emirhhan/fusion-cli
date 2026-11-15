"""Kök komut (`fusion`) izin bayrakları Claude gibi etkileşimli oturumu da başlatır (#49, #73)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from fusion_cli.cli import permission_flags
from fusion_cli.cli.launch_permissions import (
    launch_permissions,
    reset_launch_permissions,
    set_launch_permissions,
)
from fusion_cli.cli.repl.state import _apply_mode_availability, _initial_approval
from fusion_cli.engines.agent.approval import ApprovalMode


@pytest.fixture
def proje(tmp_path, monkeypatch):
    monkeypatch.setattr(permission_flags, "_warned", set())
    kok = tmp_path / "proje"
    kok.mkdir()
    reset_launch_permissions()
    yield kok
    reset_launch_permissions()


def _config():
    return SimpleNamespace(runtime=SimpleNamespace(approval_mode="auto"))


def test_bayraksiz_ayar_ve_kayit_gecerli(proje):
    set_launch_permissions(flag=None, skip_permissions=False, allow_bypass=False, root=proje)
    assert launch_permissions().mode is None
    assert _initial_approval(_config(), proje) is ApprovalMode.AUTO


def test_permission_mode_bayragi_ayari_ezer(proje):
    path = Path.home() / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"defaultMode": "acceptEdits"}}), encoding="utf-8")
    set_launch_permissions(flag="plan", skip_permissions=False, allow_bypass=False, root=proje)
    assert _initial_approval(_config(), proje) is ApprovalMode.PLAN


def test_dangerously_skip_bypass_ile_baslatir_ve_donguye_ekler(proje):
    set_launch_permissions(flag=None, skip_permissions=True, allow_bypass=False, root=proje)
    approval = _initial_approval(_config(), proje)
    assert approval is ApprovalMode.BYPASS
    state = SimpleNamespace(root=proje, approval_memory=None)
    _apply_mode_availability(state, approval)
    assert state.bypass_available is True


def test_allow_dangerously_skip_bypassi_donguye_ekler_baslatmaz(proje):
    set_launch_permissions(flag=None, skip_permissions=False, allow_bypass=True, root=proje)
    approval = _initial_approval(_config(), proje)
    assert approval is ApprovalMode.AUTO
    state = SimpleNamespace(root=proje, approval_memory=None)
    _apply_mode_availability(state, approval)
    assert state.bypass_available is True


def test_gecersiz_kip_adi_hata(proje):
    with pytest.raises(ValueError):
        set_launch_permissions(flag="yok", skip_permissions=False, allow_bypass=False, root=proje)


def test_kok_komut_bayraklari_tanir(proje, monkeypatch):
    from fusion_cli.cli import app as cli_app

    monkeypatch.chdir(proje)
    sonuc = CliRunner().invoke(cli_app.app, ["--permission-mode", "yok", "doctor", "--help"])
    assert sonuc.exit_code != 0
    assert "yok" in sonuc.output
    sonuc = CliRunner().invoke(
        cli_app.app, ["--allow-dangerously-skip-permissions", "doctor", "--help"]
    )
    assert sonuc.exit_code == 0, sonuc.output
    assert launch_permissions().allow_bypass is True


def test_satir_ici_giris_dongusu_bypass_ve_auto_kurallarina_uyar(tmp_path):
    from fusion_cli.cli.repl.input import ReplInput

    reader = ReplInput(tmp_path / "gecmis", [], mode=ApprovalMode.PLAN)
    assert reader.cycle_mode() is ApprovalMode.AUTO
    reader.mode = ApprovalMode.PLAN
    reader.bypass_available = True
    assert reader.cycle_mode() is ApprovalMode.BYPASS
    reader.mode = ApprovalMode.PLAN
    reader.bypass_available = False
    reader.auto_available = False
    assert reader.cycle_mode() is ApprovalMode.SECURITY
