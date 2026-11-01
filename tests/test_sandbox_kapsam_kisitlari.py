"""Sandbox anahtarlarının hangi ayar kapsamından okunduğu (#350, settings-reference › sandbox).

Claude Code:
- `bwrapPath` ve `socatPath` yalnız managed ayardan okunur; kullanıcı, proje, yerel dosya ya da
  `--settings` sandbox'ı başka bir ikiliye yönlendiremez.
- Sandbox "admin-required" iken (managed ya da `--settings` `allowUnsandboxedCommands: false`
  — managed `true` demedikçe — veya managed `allowManagedDomainsOnly: true`) yalıtımı
  gevşeten ayarlar yalnız managed, `--settings` ve kullanıcı ayarından alınır: deponun
  `.claude/settings*.json` dosyasındaki `excludedCommands`, `network.allowedDomains`,
  `filesystem.allowWrite`, `allowUnixSockets`, `allowAllUnixSockets: true`, proxy portları ve
  `enableWeakerNestedSandbox: true` yok sayılır (`false` yine uygulanır).
- `allowManagedDomainsOnly` açıkken proxy portları yalnız managed ayardan okunur.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from fusion_cli.config import (
    claude_sandbox_settings,
    claude_top_layers,
    sandbox_claude_keys,
    sandbox_scopes,
)
from fusion_cli.config.claude_sandbox_settings import read_claude_sandbox

_GEVSEK = {
    "excludedCommands": ["docker"],
    "enableWeakerNestedSandbox": True,
    "bwrapPath": "./kotu-bwrap",
    "socatPath": "./kotu-socat",
    "filesystem": {"allowWrite": ["/derleme"]},
    "network": {
        "allowedDomains": ["kotu.example"],
        "allowUnixSockets": ["/var/run/docker.sock"],
        "allowAllUnixSockets": True,
        "httpProxyPort": 9000,
        "socksProxyPort": 9001,
    },
}
_YONETICI_KILIDI = (
    "excluded_commands",
    "enable_weaker_nested_sandbox",
    "allow_write",
    "allowed_domains",
    "allow_unix_sockets",
    "allow_all_unix_sockets",
    "http_proxy_port",
    "socks_proxy_port",
)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_claude_keys, "_WARNED", set())
    monkeypatch.setattr(claude_sandbox_settings, "_WARNED", set())
    monkeypatch.setattr(sandbox_scopes, "_WARNED", set())
    managed = tmp_path / "managed"
    managed.mkdir()
    monkeypatch.setattr(claude_top_layers, "MANAGED_DIRS", {platform.system(): managed})
    monkeypatch.delenv(claude_top_layers.FLAG_SETTINGS_ENV, raising=False)
    trust = claude_sandbox_settings.trust
    monkeypatch.setattr(trust, "is_project_settings_trusted", lambda _root: True)
    monkeypatch.setattr(trust, "is_permissions_trusted", lambda _root: True)
    root, home = tmp_path / "proje", tmp_path / "ev"
    root.mkdir()
    home.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    return root, home / ".claude", managed


def _yaz(path: Path, veri: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(veri), encoding="utf-8")


def test_bwrap_ve_socat_yolu_yalniz_managed_ayardan(ortam, monkeypatch):
    root, user, managed = ortam
    _yaz(root / ".claude" / "settings.json", {"sandbox": _GEVSEK})
    _yaz(user / "settings.json", {"sandbox": {"bwrapPath": "/ev/bwrap", "socatPath": "/ev/s"}})
    monkeypatch.setenv(
        claude_top_layers.FLAG_SETTINGS_ENV, json.dumps({"sandbox": {"bwrapPath": "/bayrak"}})
    )

    section = read_claude_sandbox(root).section
    assert "bwrap_path" not in section and "socat_path" not in section

    _yaz(managed / "managed-settings.json", {"sandbox": {"bwrapPath": "/opt/bwrap"}})
    section = read_claude_sandbox(root).section
    assert section["bwrap_path"] == "/opt/bwrap" and "socat_path" not in section


def test_admin_required_degilken_proje_gevsetmeleri_okunur(ortam):
    root, _, _ = ortam
    _yaz(root / ".claude" / "settings.json", {"sandbox": _GEVSEK})

    section = read_claude_sandbox(root).section

    assert section["allow_all_unix_sockets"] is True and section["http_proxy_port"] == 9000
    assert section["allowed_domains"] == ["kotu.example"]
    assert section["enable_weaker_nested_sandbox"] is True


@pytest.mark.parametrize(
    ("katman", "veri"),
    [
        ("managed", {"sandbox": {"allowUnsandboxedCommands": False}}),
        ("bayrak", {"sandbox": {"allowUnsandboxedCommands": False}}),
        ("managed", {"sandbox": {"network": {"allowManagedDomainsOnly": True}}}),
    ],
)
def test_admin_required_iken_proje_yalitimi_gevsetemez(ortam, monkeypatch, katman, veri):
    root, user, managed = ortam
    _yaz(root / ".claude" / "settings.local.json", {"sandbox": _GEVSEK})
    _yaz(user / "settings.json", {"sandbox": {"filesystem": {"allowWrite": ["/ev-derleme"]}}})
    if katman == "managed":
        _yaz(managed / "managed-settings.json", veri)
    else:
        monkeypatch.setenv(claude_top_layers.FLAG_SETTINGS_ENV, json.dumps(veri))

    section = read_claude_sandbox(root).section

    for key in _YONETICI_KILIDI:
        if key == "allow_write":
            assert section[key] == ["/ev-derleme"]  # kullanıcı ayarı yine okunur
            continue
        assert key not in section, key


def test_admin_required_proje_false_degeri_yine_uygulanir(ortam):
    root, user, managed = ortam
    _yaz(managed / "managed-settings.json", {"sandbox": {"allowUnsandboxedCommands": False}})
    _yaz(user / "settings.json", {"sandbox": {"network": {"allowAllUnixSockets": True}}})
    _yaz(
        root / ".claude" / "settings.json",
        {"sandbox": {"network": {"allowAllUnixSockets": False}}},
    )

    assert read_claude_sandbox(root).section["allow_all_unix_sockets"] is False


def test_managed_true_bayragin_admin_required_kilidini_kaldirir(ortam, monkeypatch):
    root, _, managed = ortam
    _yaz(root / ".claude" / "settings.json", {"sandbox": _GEVSEK})
    _yaz(managed / "managed-settings.json", {"sandbox": {"allowUnsandboxedCommands": True}})
    monkeypatch.setenv(
        claude_top_layers.FLAG_SETTINGS_ENV,
        json.dumps({"sandbox": {"allowUnsandboxedCommands": False}}),
    )

    assert read_claude_sandbox(root).section["http_proxy_port"] == 9000


def test_managed_domains_only_proxy_portlarini_yalniz_managedden_alir(ortam):
    root, user, managed = ortam
    _yaz(user / "settings.json", {"sandbox": {"network": {"httpProxyPort": 8080}}})
    _yaz(
        managed / "managed-settings.json",
        {"sandbox": {"network": {"allowManagedDomainsOnly": True, "socksProxyPort": 1081}}},
    )

    section = read_claude_sandbox(root).section

    assert "http_proxy_port" not in section and section["socks_proxy_port"] == 1081
