"""Başlangıç izin kipi Claude Code ile birebir (#49, #50, #51, #70, #85).

Kaynak: https://code.claude.com/docs/en/permission-modes (Which mode a session starts in) ;
https://code.claude.com/docs/en/cli-reference (--permission-mode).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.cli import permission_flags
from fusion_cli.cli.permission_flags import cli_rules, resolve_start_mode, split_entries
from fusion_cli.config import trust
from fusion_cli.config.permission_rules import PermissionDecision
from fusion_cli.engines.agent.approval import ApprovalMode, parse_mode


@pytest.fixture
def proje(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    monkeypatch.setattr(permission_flags, "_warned", set())
    kok = tmp_path / "proje"
    kok.mkdir()
    return kok


def _yaz(yol: Path, veri: dict) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(veri), encoding="utf-8")


def _kip(kok, **kw):
    secenek = {"flag": None, "legacy": None, "skip_permissions": False, "headless": True}
    return resolve_start_mode(root=kok, **{**secenek, **kw})


@pytest.mark.parametrize(
    ("ad", "kip"),
    [
        ("default", ApprovalMode.SECURITY),
        ("manual", ApprovalMode.SECURITY),
        ("acceptEdits", ApprovalMode.ACCEPT_EDITS),
        ("plan", ApprovalMode.PLAN),
        ("auto", ApprovalMode.AUTO),
        ("dontAsk", ApprovalMode.DONT_ASK),
        ("bypassPermissions", ApprovalMode.BYPASS),
    ],
)
def test_claude_kip_adlari(ad, kip):
    assert parse_mode(ad) is kip


def test_headless_varsayilani_default(proje):
    assert _kip(proje) is ApprovalMode.SECURITY
    assert _kip(proje, headless=False) is ApprovalMode.AUTO


def test_bayrak_defaultmodeu_ezer_ve_skip_bypass(proje):
    _yaz(Path.home() / ".claude" / "settings.json", {"permissions": {"defaultMode": "plan"}})
    assert _kip(proje) is ApprovalMode.PLAN
    assert _kip(proje, flag="acceptEdits") is ApprovalMode.ACCEPT_EDITS
    assert _kip(proje, skip_permissions=True) is ApprovalMode.BYPASS


def test_eski_mode_bayragi_bir_kez_uyarir(proje, capsys):
    assert _kip(proje, legacy="edits") is ApprovalMode.ACCEPT_EDITS
    _kip(proje, legacy="edits")
    assert capsys.readouterr().err.count("kullanımdan kalktı") == 1


def test_proje_ayarindaki_auto_ve_bypass_yok_sayilir(proje):
    _yaz(proje / ".claude" / "settings.json", {"permissions": {"defaultMode": "bypassPermissions"}})
    assert _kip(proje) is ApprovalMode.SECURITY
    _yaz(proje / ".claude" / "settings.json", {"permissions": {"defaultMode": "acceptEdits"}})
    assert _kip(proje) is ApprovalMode.ACCEPT_EDITS
    _yaz(
        Path.home() / ".claude" / "settings.json",
        {"permissions": {"defaultMode": "bypassPermissions"}},
    )
    _yaz(proje / ".claude" / "settings.json", {})
    assert _kip(proje) is ApprovalMode.BYPASS


def test_disable_auto_mode_auto_yu_kapatir(proje):
    _yaz(proje / ".claude" / "settings.json", {"disableAutoMode": "disable"})
    assert _kip(proje, headless=False) is ApprovalMode.SECURITY
    assert _kip(proje, flag="auto") is ApprovalMode.SECURITY


def test_disable_bypass_bypass_i_kapatir(proje):
    _yaz(
        Path.home() / ".claude" / "settings.json",
        {"permissions": {"disableBypassPermissionsMode": "disable"}},
    )
    assert _kip(proje, skip_permissions=True) is ApprovalMode.SECURITY


def test_cli_kurallari_parantez_icindeki_virgulu_bolmez():
    assert split_entries(["Bash(a, b),Read", "Edit"]) == ("Bash(a, b)", "Read", "Edit")
    kurallar = cli_rules(["Bash(git log *)"], ["Edit"])
    assert [(k.pattern, k.decision, k.source) for k in kurallar] == [
        ("Bash(git log *)", PermissionDecision.ALLOW, "cli"),
        ("Edit", PermissionDecision.DENY, "cli"),
    ]


def test_repl_ve_masaustu_defaultmode_okur(proje):
    from types import SimpleNamespace

    from fusion_cli.cli.repl.state import _initial_approval

    config = SimpleNamespace(runtime=SimpleNamespace(approval_mode="auto"))
    assert _initial_approval(config, proje) is ApprovalMode.AUTO
    _yaz(Path.home() / ".claude" / "settings.json", {"permissions": {"defaultMode": "acceptEdits"}})
    assert _initial_approval(config, proje) is ApprovalMode.ACCEPT_EDITS
    _yaz(proje / ".claude" / "settings.json", {"permissions": {"disableAutoMode": "disable"}})
    _yaz(Path.home() / ".claude" / "settings.json", {})
    assert _initial_approval(config, proje) is ApprovalMode.SECURITY


def test_atlanan_mcp_kurali_uyari_uretir(proje):
    """Claude (#87): ayar dosyasındaki parantezli mcp__ kuralı atlanır ve bildirilir."""
    from fusion_cli.config.permission_warnings import skipped_rule_warnings

    assert skipped_rule_warnings(proje) == ()
    _yaz(proje / ".claude" / "settings.json", {"permissions": {"deny": ["mcp__s__x(y)"]}})
    uyarilar = skipped_rule_warnings(proje)
    assert len(uyarilar) == 1 and "mcp__s__x(y)" in uyarilar[0]
