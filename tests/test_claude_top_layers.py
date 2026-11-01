"""Claude ayar önceliğinin üst iki katmanı: `--settings` ve managed (#321, #328).

Claude Code (settings#settings-precedence): managed > komut satırı > yerel > proje > kullanıcı.
Sandbox bölümü ve `permissions.defaultMode` bu iki katmandan da okunur.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from fusion_cli.config import claude_top_layers, start_mode
from fusion_cli.config.claude_sandbox_settings import read_claude_sandbox


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    managed = tmp_path / "managed"
    managed.mkdir()
    monkeypatch.setattr(claude_top_layers, "MANAGED_DIRS", {platform.system(): managed})
    monkeypatch.delenv(claude_top_layers.FLAG_SETTINGS_ENV, raising=False)
    monkeypatch.delenv(claude_top_layers.FLAG_SETTINGS_DIR_ENV, raising=False)
    monkeypatch.setattr(start_mode, "is_project_settings_trusted", lambda _root: True)
    monkeypatch.setattr(start_mode, "is_permissions_trusted", lambda _root: True)
    root, home = tmp_path / "proje", tmp_path / "ev"
    root.mkdir()
    home.mkdir()
    yield root, home, managed
    claude_top_layers.set_flag_settings(None)


def _yaz(path: Path, veri: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(veri), encoding="utf-8")


def _kip(root, home):
    return start_mode.resolve_start_mode(root, home=home, is_root=lambda: False).mode


def test_managed_defaultmode_her_dosyanin_ustunde(ortam):
    root, home, managed = ortam
    _yaz(root / ".claude" / "settings.local.json", {"permissions": {"defaultMode": "plan"}})
    _yaz(managed / "managed-settings.json", {"permissions": {"defaultMode": "acceptEdits"}})
    assert _kip(root, home) == "edits"


def test_managed_dropin_alfabetik_son_kazanir(ortam):
    root, home, managed = ortam
    _yaz(managed / "managed-settings.json", {"permissions": {"defaultMode": "plan"}})
    _yaz(managed / "managed-settings.d" / "10-a.json", {"permissions": {"defaultMode": "default"}})
    _yaz(managed / "managed-settings.d" / "20-b.json", {"permissions": {"defaultMode": "dontAsk"}})
    assert _kip(root, home) == "dontAsk"


def test_settings_bayragi_dosyalari_ezer_managed_bayragi_ezer(ortam):
    root, home, managed = ortam
    _yaz(home / ".claude" / "settings.json", {"permissions": {"defaultMode": "plan"}})
    claude_top_layers.set_flag_settings({"permissions": {"defaultMode": "acceptEdits"}})
    assert _kip(root, home) == "edits"
    _yaz(managed / "managed-settings.json", {"permissions": {"defaultMode": "default"}})
    assert _kip(root, home) == "security"


def test_settings_bayragindaki_auto_projedeki_gibi_yok_sayilmaz(ortam):
    root, home, _ = ortam
    claude_top_layers.set_flag_settings({"permissions": {"defaultMode": "auto"}})
    headless = start_mode.headless_start_mode(root, home=home, is_root=lambda: False)
    assert headless.mode == "auto"


def test_sandbox_managed_ve_bayrak_katmani(ortam, tmp_path):
    root, home, managed = ortam
    _yaz(
        home / ".claude" / "settings.json",
        {"sandbox": {"enabled": False, "filesystem": {"allowWrite": ["/a"]}}},
    )
    ayar = tmp_path / "bayrak" / "ayar.json"
    ayar.parent.mkdir()
    claude_top_layers.set_flag_settings(
        {"sandbox": {"filesystem": {"allowWrite": ["./derleme"]}}, "model": "x"}, ayar
    )
    _yaz(managed / "managed-settings.json", {"sandbox": {"enabled": True}})
    birlesik = read_claude_sandbox(root, home=home)
    assert birlesik.enabled is True
    assert birlesik.section["allow_write"] == ["/a", str(ayar.parent.resolve() / "derleme")]
    assert managed / "managed-settings.json" in birlesik.sources


def test_bozuk_managed_dosyasi_atlanir(ortam):
    root, home, managed = ortam
    (managed / "managed-settings.json").write_text("{bozuk", encoding="utf-8")
    assert claude_top_layers.managed_layers() == []
    assert _kip(root, home) == "auto"


def test_ortam_degiskeni_managed_dizinini_degistiremez(ortam, monkeypatch, tmp_path):
    """Claude'da yönetici dosyasından kaçış yok: ortam değişkeni dizini ezemez (inceleme #2)."""
    root, home, managed = ortam
    _yaz(managed / "managed-settings.json", {"permissions": {"defaultMode": "plan"}})
    monkeypatch.setenv("FUSION_CLAUDE_MANAGED_DIR", str(tmp_path / "yok"))
    assert _kip(root, home) == "plan"


def test_allow_managed_read_paths_only_disaridaki_allow_read_yok_sayilir(ortam):
    root, home, managed = ortam
    _yaz(home / ".claude" / "settings.json", {"sandbox": {"filesystem": {"allowRead": ["/k"]}}})
    _yaz(
        managed / "managed-settings.json",
        {
            "sandbox": {
                "filesystem": {
                    "denyRead": ["/"],
                    "allowRead": ["/y"],
                    "allowManagedReadPathsOnly": True,
                }
            }
        },
    )
    birlesik = read_claude_sandbox(root, home=home)
    assert birlesik.section["allow_read"] == ["/y"]
    assert birlesik.section["deny_read"] == ["/"]


def test_allow_managed_domains_only_yalniz_managed_alan_adlari_ve_sorusuz(ortam):
    root, home, managed = ortam
    _yaz(
        home / ".claude" / "settings.json",
        {"sandbox": {"network": {"allowedDomains": ["kullanici.example"]}}},
    )
    _yaz(
        managed / "managed-settings.json",
        {
            "sandbox": {
                "network": {"allowedDomains": ["sirket.example"], "allowManagedDomainsOnly": True}
            }
        },
    )
    birlesik = read_claude_sandbox(root, home=home)
    assert birlesik.section["allowed_domains"] == ["sirket.example"]
    assert birlesik.section["strict_allowlist"] is True


def test_allow_managed_bayraklari_managed_disinda_etkisiz(ortam):
    root, home, _ = ortam
    _yaz(
        home / ".claude" / "settings.json",
        {
            "sandbox": {
                "filesystem": {"allowRead": ["/k"], "allowManagedReadPathsOnly": True},
                "network": {"allowedDomains": ["a.example"], "allowManagedDomainsOnly": True},
            }
        },
    )
    birlesik = read_claude_sandbox(root, home=home)
    assert birlesik.section["allow_read"] == ["/k"]
    assert birlesik.section["allowed_domains"] == ["a.example"]
    assert "strict_allowlist" not in birlesik.section
