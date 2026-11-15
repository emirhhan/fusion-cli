"""Klasör güveni Claude Code ile birebir (#67, #71).

Kaynak: https://code.claude.com/docs/en/permissions#project-allow-rules-and-workspace-trust
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config import trust
from fusion_cli.config.trust import is_permissions_trusted, is_project_settings_trusted


@pytest.fixture
def ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    return ev


def _yaz(yol: Path) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps({"permissions": {"allow": ["Bash(*)"]}}), encoding="utf-8")


def test_depoda_guven_git_kokune_baglanir_alt_dizini_kapsar(tmp_path, ev):
    depo = tmp_path / "depo"
    (depo / ".git").mkdir(parents=True)
    alt = depo / "paket"
    _yaz(alt / ".claude" / "settings.json")
    assert not is_project_settings_trusted(alt)
    trust.trust_project(depo)
    assert is_project_settings_trusted(alt)
    # İçerik değişince güven düşmez.
    (alt / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    assert is_project_settings_trusted(alt)


def test_ust_klasor_guveni_ic_ice_depoya_uzanmaz(tmp_path, ev):
    ust = tmp_path / "isler"
    klon = ust / "klon"
    (klon / ".git").mkdir(parents=True)
    duz = ust / "duz"
    _yaz(klon / ".claude" / "settings.json")
    _yaz(duz / ".claude" / "settings.json")
    trust.trust_project(ust)
    assert is_project_settings_trusted(duz)
    assert not is_project_settings_trusted(klon)


def test_ev_dizininde_yerel_dosya_guven_istemez(tmp_path, ev):
    _yaz(ev / ".claude" / "settings.local.json")
    assert is_permissions_trusted(ev)
    baska = tmp_path / "baska"
    _yaz(baska / ".claude" / "settings.local.json")
    assert not is_permissions_trusted(baska)
