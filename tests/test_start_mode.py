"""Başlangıç izin kipi: `--permission-mode` > `permissions.defaultMode` > varsayılan (#328)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config import start_mode
from fusion_cli.core.errors import ConfigError


def _yaz(path: Path, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"defaultMode": mode}}), encoding="utf-8")


@pytest.fixture
def dizinler(tmp_path, monkeypatch):
    monkeypatch.setattr(start_mode, "is_project_settings_trusted", lambda _root: True)
    monkeypatch.setattr(start_mode, "is_permissions_trusted", lambda _root: True)
    root, home = tmp_path / "proje", tmp_path / "ev"
    root.mkdir()
    home.mkdir()
    return root, home


def _coz(root, home, **kw):
    return start_mode.resolve_start_mode(root, home=home, is_root=lambda: False, **kw)


def test_ayar_yoksa_yerlesik_auto(dizinler):
    root, home = dizinler
    assert _coz(root, home).mode == "auto"


@pytest.mark.parametrize(
    ("deger", "beklenen"),
    [("default", "security"), ("acceptEdits", "edits"), ("plan", "plan"), ("dontAsk", "dontAsk")],
)
def test_kullanici_defaultmode(dizinler, deger, beklenen):
    root, home = dizinler
    _yaz(home / ".claude" / "settings.json", deger)
    assert _coz(root, home).mode == beklenen


def test_bayrak_her_seyin_ustunde(dizinler):
    root, home = dizinler
    _yaz(root / ".claude" / "settings.json", "plan")
    assert _coz(root, home, flag="acceptEdits").mode == "edits"
    assert _coz(root, home, flag="manual").mode == "security"
    with pytest.raises(ConfigError):
        _coz(root, home, flag="hepsi")


def test_proje_dosyasi_kullaniciyi_ezer_yerel_projeyi_ezer(dizinler):
    root, home = dizinler
    _yaz(home / ".claude" / "settings.json", "plan")
    _yaz(root / ".claude" / "settings.json", "acceptEdits")
    assert _coz(root, home).mode == "edits"
    _yaz(root / ".claude" / "settings.local.json", "default")
    assert _coz(root, home).mode == "security"


def test_projede_auto_yok_sayilir_kullaniciya_dusulmez(dizinler):
    root, home = dizinler
    _yaz(home / ".claude" / "settings.json", "plan")
    _yaz(root / ".claude" / "settings.json", "auto")
    assert _coz(root, home).mode == "auto"  # yerleşik varsayılan, kullanıcının plan'ı değil


def test_projede_bypass_yok_sayilir_manual_acilir(dizinler):
    root, home = dizinler
    _yaz(root / ".claude" / "settings.json", "bypassPermissions")
    sonuc = _coz(root, home)
    assert sonuc.mode == "security" and not sonuc.bypass_available


def test_kullanici_bypass_ile_baslar_root_ise_reddedilir(dizinler):
    root, home = dizinler
    _yaz(home / ".claude" / "settings.json", "bypassPermissions")
    sonuc = _coz(root, home)
    assert sonuc.mode == "bypass" and sonuc.bypass_available
    reddedilen = start_mode.resolve_start_mode(root, home=home, is_root=lambda: True)
    assert reddedilen.mode == "security" and reddedilen.note


def test_auto_kullanilamazsa_manual(dizinler):
    root, home = dizinler
    assert _coz(root, home, auto_available=False).mode == "security"


def test_eski_yaml_bypass_davranisi_korunur(dizinler):
    root, home = dizinler
    sonuc = _coz(root, home, legacy="bypass")
    assert sonuc.mode == "auto" and sonuc.bypass_available
    assert _coz(root, home, legacy="edits").mode == "edits"


# --- #328: fusion agent defaultMode ve skip-permissions bayrakları ------------------- #


def _baslik(root, home, **kw):
    return start_mode.headless_start_mode(root, home=home, is_root=lambda: False, **kw)


def test_headless_ayar_yoksa_manual(dizinler):
    root, home = dizinler
    assert _baslik(root, home).mode == "security"


def test_headless_kullanici_defaultmode_okunur_projede_auto_yok_sayilir(dizinler):
    root, home = dizinler
    _yaz(start_mode.claude_user_dir(home) / "settings.json", "acceptEdits")
    assert _baslik(root, home).mode == "edits"
    _yaz(root / ".claude" / "settings.json", "auto")
    assert _baslik(root, home).mode == "security"


def test_headless_bayrak_ayari_ezer_ve_root_bypass_reddedilir(dizinler):
    root, home = dizinler
    _yaz(start_mode.claude_user_dir(home) / "settings.json", "plan")
    assert _baslik(root, home, flag="dontAsk").mode == "dontAsk"
    reddedilen = start_mode.headless_start_mode(
        root, home=home, flag="bypassPermissions", is_root=lambda: True
    )
    assert reddedilen.mode == "security" and reddedilen.note


def test_dangerously_skip_permissions_bypass_bayragidir():
    assert start_mode.skip_permissions_flag("", True) == "bypassPermissions"
    assert start_mode.skip_permissions_flag("plan", True) == "plan"
    assert start_mode.skip_permissions_flag("", False) == ""


def test_allow_dangerously_skip_bypass_i_baslatmadan_donguye_ekler(dizinler):
    root, home = dizinler
    acik = _coz(root, home, allow_bypass=True)
    assert acik.mode == "auto" and acik.bypass_available
    root_ta = start_mode.resolve_start_mode(
        root, home=home, is_root=lambda: True, allow_bypass=True
    )
    assert not root_ta.bypass_available and root_ta.note
